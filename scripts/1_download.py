"""
YouTube Charts Data Scraper - Download & Persistence Pipeline
============================================================================
Top-level entry point for downloading the weekly YouTube Charts Top 100 songs
and persisting them into a localized SQLite database. This module acts as the
first stage in the broader intelligence pipeline.

This script orchestrates the extraction of chart data using direct HTTP requests
to the InnerTube API, circumventing the need for browser automation (Playwright)
and its associated anti-bot mitigations. It implements a strict "fail-hard" 
policy: if the extraction or persistence fails, the pipeline aborts immediately 
to prevent data pollution from fallback synthetic records.

Features
--------
- Downloads the complete weekly Top 100 songs from YouTube Charts with exact
  metrics (Rank, Previous Rank, Views, Growth, Periods on Chart, Video URL).
- Leverages direct HTTP requests to the InnerTube API, bypassing HTML parsing
  and browser CAPTCHAs.
- Stores historical data in SQLite with versioning based on ISO week format
  (`YYYY-WXX`).
- Implements an automatic backup system before database mutations.
- Enforces a strict no-fallback policy: pipeline aborts if extraction fails.

Dependencies
------------
- Internal: none (self-contained script).
- External: `httpx`, `ytmusicapi`, `pandas`, `sqlite3` (stdlib), `asyncio`, 
  `shutil`, `subprocess`.
- Downstream: Script 2.1 (Artist Metadata Enrichment) consumes the generated
  SQLite databases.

Requirements
------------
- Python 3.7+
- `httpx`, `ytmusicapi`, and `pandas` installed (auto-installed if missing).
- Write access to the `charts_archive/` directory structure.

Notes
-----
- **Directory structure**: Automatically creates `data/`,
  `charts_archive/1_download-chart/databases/`, and
  `charts_archive/1_download-chart/backup/` on import.
- **Week identifiers**: Follow ISO format `YYYY-WXX` (e.g., `2026-W47`).
- **Strict Mode**: The legacy fallback mode (generating 100 synthetic records)
  has been permanently removed. If the API fails, the script exits with code 1.
- **Backup retention**: Backups are retained for 7 days; databases are
  retained for 52 weeks.
- **API Stability**: Direct InnerTube requests require dynamic generation of
  the `clientVersion` to prevent HTTP 400 (Invalid Argument) errors.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

import asyncio
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================================
# CONSTANTS AND DIRECTORIES
# ============================================================================
OUTPUT_DIR = Path("data")
ARCHIVE_DIR = Path("charts_archive/1_download-chart")
DATABASE_DIR = ARCHIVE_DIR / "databases"
BACKUP_DIR = ARCHIVE_DIR / "backup"
DOWNLOAD_DIR = ARCHIVE_DIR / "downloads"

# Ensure all required directories exist before any file operations.
for dir_path in [OUTPUT_DIR, ARCHIVE_DIR, DATABASE_DIR, BACKUP_DIR, DOWNLOAD_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# ============================================================================
# DEPENDENCY MANAGEMENT
# ============================================================================
def install_dependencies() -> bool:
    """
    Check and install required external dependencies if needed.
    
    Uses `httpx` for direct API requests, `ytmusicapi` for context headers,
    and `pandas` for data manipulation.
    """
    print("🔧 Checking dependencies (httpx, ytmusicapi, pandas)...")
    try:
        import httpx
        from ytmusicapi import YTMusic
        import pandas
        print("   ✅ Dependencies are installed")
        return True
    except ImportError:
        print("   📦 Installing httpx, ytmusicapi, and pandas...")
        # Use sys.executable to ensure installation in the current virtual environment.
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "httpx", "ytmusicapi", "pandas"], 
            check=True
        )
        print("   ✅ Dependencies installed")
        return True

# ============================================================================
# YOUTUBE CHARTS DOWNLOADER (Custom HTTP API Request)
# ============================================================================
async def download_youtube_charts() -> Path | None:
    """
    Download YouTube Charts data using a direct HTTP request to the InnerTube API.
    Extracts exact fields required by the database schema.
    """
    print("🎵 YouTube Charts - Downloading Exact Metrics")
    print("=" * 70)

    try:
        import httpx
        from ytmusicapi import YTMusic

        print("1. 📡 Connecting to YouTube Music API...")
        # Initialize ytmusicapi to get the correct headers/cookies (if needed)
        # However, for charts.youtube.com, a direct WEB_REMIX request usually works.
        
        # We use a dynamic client version based on today's date to prevent HTTP 400.
        # YouTube rejects requests with outdated client versions.
        today_str = datetime.now().strftime("%Y%m%d")
        client_version = f"1.{today_str}.01.00"

        url = "https://charts.youtube.com/youtubei/v1/browse"
        
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB_REMIX",
                    "clientVersion": client_version,
                    "hl": "en",
                    "gl": "US",
                }
            },
            "browseId": "FEmusic_charts",
            "query": "chart_params_type=WEEK&perspective=CHART&flags=viral_video_chart&selected_chart=TRACKS",
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://charts.youtube.com/",
            "Origin": "https://charts.youtube.com",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            print("2. 📊 Fetching detailed charts data...")
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code != 200:
                print(f"   ❌ Error HTTP {response.status_code}: {response.text[:200]}")
                return None

            data = response.json()
            print("   ✅ Response received.")

            # Save raw JSON for debugging
            raw_debug_path = ARCHIVE_DIR / "raw_api_response.json"
            with open(raw_debug_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"   📄 Raw JSON saved to: {raw_debug_path}")

        # =====================================================================
        # PARSING THE JSON TO EXTRACT EXACT FIELDS
        # =====================================================================
        print("3. 🛠️  Parsing data...")
        songs = []
        
        def extract_tracks(obj):
            if isinstance(obj, dict):
                # Detect the chart entry object
                if "chartEntryData" in obj and "trackMetadata" in obj:
                    entry = obj["chartEntryData"]
                    meta = obj["trackMetadata"]
                    
                    # Extract Video ID for the URL
                    video_id = meta.get("videoId", "")
                    youtube_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
                    
                    # Extract metrics
                    current_rank = entry.get("currentRank", 0)
                    previous_rank = entry.get("previousRank", 0)
                    periods = entry.get("appearancesOnChart", 0)
                    
                    # Views and Growth are often nested inside 'rankingMetric'
                    ranking_metric = entry.get("rankingMetric", {})
                    views_str = ranking_metric.get("value", "0")
                    growth = ranking_metric.get("change", "0%") # e.g., "+5", "-2", "NEW"
                    
                    # Clean views string (remove commas) to convert to integer later
                    views_clean = int(''.join(filter(str.isdigit, str(views_str)))) if views_str else 0

                    songs.append({
                        "Rank": current_rank,
                        "[Previous Rank]": previous_rank,
                        "[Track Name]": meta.get("trackName", ""),
                        "[Artist Names]": ", ".join([a.get("name", "") for a in meta.get("artists", [])]),
                        "[Periods on Chart]": periods,
                        "Views": views_clean,
                        "Growth": growth,
                        "[YouTube URL]": youtube_url,
                    })
                    return
                
                for value in obj.values():
                    extract_tracks(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_tracks(item)

        extract_tracks(data)

        if not songs:
            print("   ❌ No chart entries found in the JSON response.")
            return None

        # Sort by Rank to ensure order
        songs.sort(key=lambda x: x["Rank"])
        
        # Keep only Top 100
        songs = songs[:100]
        print(f"   ✅ Extracted {len(songs)} tracks with exact metrics.")

        # =====================================================================
        # SAVE TO CSV
        # =====================================================================
        filename = DOWNLOAD_DIR / "latest_chart.csv"
        
        # Define exact headers
        fieldnames = [
            "Rank", "[Previous Rank]", "[Track Name]", "[Artist Names]",
            "[Periods on Chart]", "Views", "Growth", "[YouTube URL]"
        ]
        
        with open(filename, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(songs)

        print(f"   💾 CSV saved: {filename} ({filename.stat().st_size} bytes)")
        return filename

    except Exception as e:
        print(f"⚠️  Error extracting data: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# SQLITE PERSISTENCE
# ============================================================================
def update_sqlite_database(csv_path: Path, week_id: str) -> Path | None:
    """
    Update the SQLite database with the exact schema required.
    """
    print("   📊 Processing chart data into SQLite...")
    try:
        import sqlite3
        import pandas as pd

        df = pd.read_csv(csv_path, encoding="utf-8")
        
        # Add metadata columns required by the schema
        current_time = datetime.now()
        df["download_date"] = current_time.strftime("%Y-%m-%d")
        df["download_time"] = current_time.strftime("%H:%M:%S")
        df["week_id"] = week_id
        df["timestamp"] = current_time.strftime("%Y%m%d_%H%M%S")

        # Reorder columns to match the exact database schema requested
        columns_order = [
            "Rank", "[Previous Rank]", "[Track Name]", "[Artist Names]",
            "[Periods on Chart]", "Views", "Growth", "[YouTube URL]",
            "download_date", "download_time", "week_id", "timestamp"
        ]
        df = df[columns_order]

        db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
        
        if db_path.exists(): 
            create_backup_before_update(week_id)

        conn = sqlite3.connect(db_path)
        temp_table_name = f"temp_{current_time.strftime('%Y%m%d_%H%M%S')}"
        
        # We explicitly define the schema to ensure INTEGER types for Views/Rank
        # Instead of relying on pandas to_sql inference, we create the table manually.
        cursor = conn.cursor()
        
        cursor.execute(f"""
            CREATE TABLE {temp_table_name} (
                Rank               INTEGER,
                [Previous Rank]    REAL,
                [Track Name]       TEXT,
                [Artist Names]     TEXT,
                [Periods on Chart] INTEGER,
                Views              INTEGER,
                Growth             TEXT,
                [YouTube URL]      TEXT,
                download_date      TEXT,
                download_time      TEXT,
                week_id            TEXT,
                timestamp          TEXT
            )
        """)
        
        # Insert data row by row
        for _, row in df.iterrows():
            cursor.execute(f"""
                INSERT INTO {temp_table_name} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(row))

        # Now handle the main table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chart_data'")
        
        if cursor.fetchone():
            # Schema validation check
            cursor.execute("PRAGMA table_info(chart_data)")
            existing_cols = len(cursor.fetchall())
            
            if existing_cols != 12:
                print(f"   ⚠️  Schema mismatch. Rebuilding table...")
                cursor.execute("DROP TABLE chart_data")
                cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO chart_data")
            else:
                cursor.execute("DELETE FROM chart_data WHERE week_id = ?", (week_id,))
                cursor.execute(f"INSERT INTO chart_data SELECT * FROM {temp_table_name}")
                cursor.execute(f"DROP TABLE {temp_table_name}")
        else:
            cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO chart_data")

        conn.commit()
        conn.close()
        
        print(f"   ✅ Database updated: {db_path}")
        return db_path
        
    except Exception as e:
        print(f"⚠️  SQLite error: {e}")
        return None


# ============================================================================
# BACKUP & CLEANUP FUNCTIONS
# ============================================================================
def create_backup_before_update(week_id: str) -> None:
    db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
    if not db_path.exists(): return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"backup_{week_id}_{timestamp}.db"
    try:
        shutil.copy2(db_path, backup_path)
        print(f"   ✅ Backup created: {backup_path.name}")
    except Exception as e:
        print(f"   ⚠️  Error creating backup: {e}")

def cleanup_old_backups(days: int = 7) -> None:
    cutoff_date = datetime.now() - timedelta(days=days)
    for backup in BACKUP_DIR.glob("backup_*.db"):
        if backup.stat().st_mtime < cutoff_date.timestamp():
            backup.unlink()

def cleanup_old_databases(weeks: int = 52) -> None:
    cutoff_date = datetime.now() - timedelta(weeks=weeks)
    for db in DATABASE_DIR.glob("youtube_charts_*.db"):
        try:
            week_id = db.stem.replace("youtube_charts_", "")
            year, week = map(int, week_id.split("-W"))
            db_date = datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w")
            if db_date < cutoff_date:
                db.unlink()
        except Exception:
            pass

def get_week_identifier(date: datetime = None) -> str:
    if date is None:
        date = datetime.now()
    year, week_num, _ = date.isocalendar()
    return f"{year}-W{week_num:02d}"

def main() -> int:
    print("\n" + "=" * 70)
    print("🎵 YOUTUBE CHARTS - EXTRACTOR (No Fallback)")
    print("=" * 70)

    if not install_dependencies():
        print("❌ CRITICAL: Dependency installation failed. Aborting.")
        return 1

    week_id = get_week_identifier()
    print(f"\n📆 Current week: {week_id}")

    print("\n1. 📥 DOWNLOADING YOUTUBE CHARTS (Strict Mode)...")
    csv_path = asyncio.run(download_youtube_charts())

    if not csv_path or not csv_path.exists():
        print("\n❌ CRITICAL ERROR: Automatic download failed.")
        return 1

    print("\n2. 🗃️  STORING IN SQLITE DATABASE...")
    db_path = update_sqlite_database(csv_path, week_id)
    
    if not db_path:
        print("❌ CRITICAL: Database update failed. Aborting.")
        return 1

    print("\n3. 🧹 CLEANING OLD FILES...")
    cleanup_old_backups(7)
    cleanup_old_databases(52)

    print("\n" + "=" * 70)
    print("✅ PROCESS COMPLETED SUCCESSFULLY")
    print("=" * 70)
    return 0

if __name__ == "__main__":
    sys.exit(main())
