"""
YouTube Charts Data Scraper - Download & Persistence Pipeline
============================================================================
Top-level entry point for downloading the weekly YouTube Charts Top 100 songs
and persisting them into a localized SQLite database. This module acts as the
first stage in the broader intelligence pipeline.

This script leverages Apify's YouTube Charts Scraper to bypass anti-bot 
mitigations and IP blocking. Apify handles proxy rotation and CAPTCHA 
solving internally, returning a clean JSON payload with exact metrics 
(Views, Growth, Previous Rank, Periods on Chart).

Dependencies
------------
- Internal: none (self-contained script).
- External: `httpx`, `pandas`, `sqlite3` (stdlib), `asyncio`, `shutil`.
- Downstream: Script 2.1 (Artist Metadata Enrichment) consumes the SQLite DBs.

Requirements
------------
- Python 3.7+
- `httpx` and `pandas` installed (auto-installed if missing).
- Environment variable `APIFY_TOKEN` must be set.

Notes
-----
- **Strict Mode**: The legacy fallback mode has been permanently removed.
- **API Stability**: Apify ensures reliable data extraction even if YouTube
  changes its frontend or API structure.

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
    """
    print("🔧 Checking dependencies (httpx, pandas)...")
    try:
        import httpx
        import pandas
        print("   ✅ Dependencies are installed")
        return True
    except ImportError:
        print("   📦 Installing httpx and pandas...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "httpx", "pandas"], 
            check=True
        )
        print("   ✅ Dependencies installed")
        return True

# ============================================================================
# WEEK IDENTIFIER
# ============================================================================
def get_week_identifier(date: datetime = None) -> str:
    """
    Generate ISO week identifier string (e.g., '2026-W47').
    """
    if date is None:
        date = datetime.now()
    year, week_num, _ = date.isocalendar()
    return f"{year}-W{week_num:02d}"

# ============================================================================
# YOUTUBE CHARTS DOWNLOADER (Apify API)
# ============================================================================
async def download_youtube_charts() -> Path | None:
    """
    Download YouTube Charts data using the Apify API.
    
    Returns:
        Path | None: The path to the generated CSV file if successful, 
                     None otherwise.
    """
    print("🎵 YouTube Charts - Downloading Exact Metrics via Apify")
    print("=" * 70)

    try:
        import httpx

        # Retrieve the API token from environment variables
        apify_token = os.environ.get("APIFY_TOKEN")
        if not apify_token:
            print("   ❌ ERROR: APIFY_TOKEN environment variable is not set.")
            print("   Please configure it in your environment or GitHub Secrets.")
            return None

        print("1. 📡 Triggering Apify Actor...")
        
        # Apify actor endpoint (websift/youtube-charts-scraper)
        # We use 'run-sync-get-dataset-items' to execute and get results in one step.
        url = f"https://api.apify.com/v2/acts/websift~youtube-charts-scraper/run-sync-get-dataset-items?token={apify_token}"
        
        # Payload configuration for Global Top Songs Weekly
        payload = {
            "charts": ["top-songs"],
            "regions": ["global"],
            "periods": ["weekly"],
            "maxItems": 100
        }

        headers = {
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code not in (200, 201):
                print(f"   ❌ Apify API Error {response.status_code}: {response.text[:500]}")
                return None

            data = response.json()
            print("   ✅ Response received from Apify.")

            if not data:
                print("   ❌ Apify returned empty data.")
                return None

            # Map Apify's JSON response to our exact database schema.
            # Apify provides clean fields, so we map them directly.
            songs = []
            for idx, item in enumerate(data[:100], start=1):
                songs.append({
                    "Rank": item.get("position", idx),
                    "[Previous Rank]": item.get("previousPosition", "N/A"),
                    "[Track Name]": item.get("title", ""),
                    "[Artist Names]": item.get("artists", ""),
                    "[Periods on Chart]": item.get("weeksOnChart", "N/A"),
                    "Views": item.get("views", 0),
                    "Growth": item.get("trend", "N/A"),
                    "[YouTube URL]": item.get("url", ""),
                })

            # Save raw JSON for auditing and debugging purposes.
            raw_debug_path = ARCHIVE_DIR / "raw_apify_response.json"
            with open(raw_debug_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"   📄 Raw JSON saved to: {raw_debug_path}")

        # Serialize mapped data to CSV
        filename = DOWNLOAD_DIR / "latest_chart.csv"
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
    Update the SQLite database with the new chart data.
    
    Implements an atomic update strategy: inserts data into a temp table,
    then replaces the target table/rows within a transaction. Includes schema
    validation to handle structural changes gracefully.
    """
    print("   📊 Processing chart data into SQLite...")
    try:
        import sqlite3
        import pandas as pd

        df = pd.read_csv(csv_path, encoding="utf-8")
        
        # Enrich dataframe with metadata columns for historical tracking.
        current_time = datetime.now()
        df["download_date"] = current_time.strftime("%Y-%m-%d")
        df["download_time"] = current_time.strftime("%H:%M:%S")
        df["week_id"] = week_id
        df["timestamp"] = current_time.strftime("%Y%m%d_%H%M%S")

        # Enforce exact column order for the database schema.
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
        
        # Create the temporary table with explicit type definitions.
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
        
        # Insert data row by row.
        for _, row in df.iterrows():
            cursor.execute(f"""
                INSERT INTO {temp_table_name} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(row))

        # Handle the main table (chart_data).
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chart_data'")
        
        if cursor.fetchone():
            # Validate schema: if column count differs, drop and recreate.
            cursor.execute("PRAGMA table_info(chart_data)")
            existing_cols = len(cursor.fetchall())
            
            if existing_cols != 12:
                print(f"   ⚠️  Schema mismatch: existing table has {existing_cols} columns. Rebuilding...")
                cursor.execute("DROP TABLE chart_data")
                cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO chart_data")
            else:
                # Schema matches: delete old records for this week and insert new ones.
                cursor.execute("DELETE FROM chart_data WHERE week_id = ?", (week_id,))
                cursor.execute(f"INSERT INTO chart_data SELECT * FROM {temp_table_name}")
                cursor.execute(f"DROP TABLE {temp_table_name}")
        else:
            # Table doesn't exist: promote the temp table.
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
    """
    Create a timestamped backup of the existing SQLite database.
    """
    db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
    if not db_path.exists(): 
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"backup_{week_id}_{timestamp}.db"
    
    try:
        shutil.copy2(db_path, backup_path)
        print(f"   ✅ Backup created: {backup_path.name}")
    except Exception as e:
        print(f"   ⚠️  Error creating backup: {e}")

def cleanup_old_backups(days: int = 7) -> None:
    """
    Remove backup files older than the specified retention period.
    """
    print(f"   🧹 Cleaning backups older than {days} days...")
    cutoff_date = datetime.now() - timedelta(days=days)
    deleted_count = 0
    
    for backup in BACKUP_DIR.glob("backup_*.db"):
        if backup.stat().st_mtime < cutoff_date.timestamp():
            try:
                backup.unlink()
                deleted_count += 1
            except Exception as e:
                print(f"   ⚠️  Error deleting {backup.name}: {e}")
                
    if deleted_count > 0:
        print(f"   ✅ Deleted {deleted_count} old backup(s)")
    else:
        print("   ℹ️  No old backups to delete")

def cleanup_old_databases(weeks: int = 52) -> None:
    """
    Remove database files older than the specified retention period.
    """
    print(f"   🧹 Cleaning databases older than {weeks} weeks...")
    cutoff_date = datetime.now() - timedelta(weeks=weeks)
    deleted_count = 0
    
    for db in DATABASE_DIR.glob("youtube_charts_*.db"):
        try:
            week_id = db.stem.replace("youtube_charts_", "")
            year, week = map(int, week_id.split("-W"))
            db_date = datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w")
            
            if db_date < cutoff_date:
                db.unlink()
                deleted_count += 1
                print(f"      ✅ Deleted: {db.name}")
        except Exception as e:
            print(f"   ⚠️  Error processing {db.name}: {e}")
            
    if deleted_count > 0:
        print(f"   ✅ Deleted {deleted_count} old database(s)")
    else:
        print("   ℹ️  No old databases to delete")

# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================
def main() -> int:
    """
    Entry point for the download and persistence pipeline.
    """
    print("\n" + "=" * 70)
    print("🎵 YOUTUBE CHARTS - EXTRACTOR (No Fallback)")
    print("=" * 70)

    if not install_dependencies():
        print("❌ CRITICAL: Dependency installation failed. Aborting.")
        return 1

    week_id = get_week_identifier()
    print(f"\n📆 Current week: {week_id}")

    print("\n1. 📥 DOWNLOADING YOUTUBE CHARTS (Apify)...")
    csv_path = asyncio.run(download_youtube_charts())

    # Strict mode: Abort if download fails.
    if not csv_path or not csv_path.exists():
        print("\n❌ CRITICAL ERROR: Automatic download failed.")
        print("🛑 Fallback mode disabled. Aborting execution to prevent data pollution.")
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

# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    sys.exit(main())
