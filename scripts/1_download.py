"""
YouTube Charts Data Scraper - Download & Persistence Pipeline
============================================================================
Top-level entry point for downloading the weekly YouTube Charts Top 100 songs
and persisting them into a localized SQLite database. This module acts as the
first stage in the broader intelligence pipeline.

This script uses a hybrid approach:
1. `ytmusicapi` to fetch the base playlist and video IDs reliably.
2. `httpx` to query the `charts.youtube.com` InnerTube API (using the "WEB" 
   client) to extract exact weekly metrics (Views, Growth, Previous Rank, 
   Periods on Chart).

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
- **Strict Mode**: The legacy fallback mode (generating 100 synthetic records)
  has been permanently removed. If the API fails, the script exits with code 1.
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

for dir_path in [OUTPUT_DIR, ARCHIVE_DIR, DATABASE_DIR, BACKUP_DIR, DOWNLOAD_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# ============================================================================
# DEPENDENCY MANAGEMENT
# ============================================================================
def install_dependencies() -> bool:
    print("🔧 Checking dependencies (httpx, ytmusicapi, pandas)...")
    try:
        import httpx
        from ytmusicapi import YTMusic
        import pandas
        print("   ✅ Dependencies are installed")
        return True
    except ImportError:
        print("   📦 Installing dependencies...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "httpx", "ytmusicapi", "pandas"], 
            check=True
        )
        print("   ✅ Dependencies installed")
        return True

# ============================================================================
# WEEK IDENTIFIER
# ============================================================================
def get_week_identifier(date: datetime = None) -> str:
    if date is None:
        date = datetime.now()
    year, week_num, _ = date.isocalendar()
    return f"{year}-W{week_num:02d}"

# ============================================================================
# YOUTUBE CHARTS DOWNLOADER (Hybrid Approach)
# ============================================================================
async def download_youtube_charts() -> Path | None:
    print("🎵 YouTube Charts - Downloading Exact Metrics")
    print("=" * 70)

    try:
        import httpx
        from ytmusicapi import YTMusic
        import pandas as pd

        # ---------------------------------------------------------------------
        # STEP 1: Use ytmusicapi to get the reliable list of video IDs
        # ---------------------------------------------------------------------
        print("1. 📡 Fetching base playlist via ytmusicapi...")
        yt = YTMusic()
        charts = yt.get_charts(country="ZZ")
        
        playlist_id = None
        if "videos" in charts and charts["videos"]:
            playlist_id = charts["videos"][0].get("playlistId")
            
        if not playlist_id:
            print("   ❌ No playlist found in ytmusicapi response.")
            return None

        playlist = yt.get_playlist(playlist_id, limit=100)
        yt_tracks = {}
        for track in playlist.get("tracks", []):
            vid = track.get("videoId")
            if vid:
                yt_tracks[vid] = {
                    "title": track.get("title", ""),
                    "artists": ", ".join([a.get("name", "") for a in track.get("artists", [])])
                }
        print(f"   ✅ ytmusicapi retrieved {len(yt_tracks)} tracks.")

        # ---------------------------------------------------------------------
        # STEP 2: Use httpx to query charts.youtube.com for exact metrics
        # ---------------------------------------------------------------------
        print("2. 📊 Fetching exact metrics from charts.youtube.com API...")
        
        today_str = datetime.now().strftime("%Y%m%d")
        client_version = f"2.{today_str}.01.00"

        url = "https://charts.youtube.com/youtubei/v1/browse"
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB",
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

        exact_metrics = {}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                print(f"   📡 API Response Status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    with open(ARCHIVE_DIR / "raw_api_response.json", "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)

                    def extract_metrics(obj):
                        if isinstance(obj, dict):
                            if "chartEntryData" in obj and "trackMetadata" in obj:
                                meta = obj["trackMetadata"]
                                entry = obj["chartEntryData"]
                                vid = meta.get("videoId")
                                if vid:
                                    metric = entry.get("rankingMetric", {})
                                    exact_metrics[vid] = {
                                        "rank": entry.get("currentRank", 0),
                                        "prev_rank": entry.get("previousRank", "N/A"),
                                        "periods": entry.get("appearancesOnChart", "N/A"),
                                        "views": int(''.join(filter(str.isdigit, str(metric.get("value", "0"))))),
                                        "growth": metric.get("change", "N/A"),
                                    }
                                return
                            for v in obj.values():
                                extract_metrics(v)
                        elif isinstance(obj, list):
                            for item in obj:
                                extract_metrics(item)
                    
                    extract_metrics(data)
                    print(f"   ✅ Extracted exact metrics for {len(exact_metrics)} tracks.")
                else:
                    print(f"   ❌ API Error {response.status_code}. Check the response preview.")
        except Exception as e:
            print(f"   ⚠️  Error querying charts API: {e}")

        # ---------------------------------------------------------------------
        # STEP 3: Merge Data
        # ---------------------------------------------------------------------
        print("3. 🛠️  Merging data...")
        songs = []
        for idx, (vid, yt_data) in enumerate(yt_tracks.items(), start=1):
            metrics = exact_metrics.get(vid, {})
            
            songs.append({
                "Rank": metrics.get("rank", idx),
                "[Previous Rank]": metrics.get("prev_rank", "N/A"),
                "[Track Name]": yt_data["title"],
                "[Artist Names]": yt_data["artists"],
                "[Periods on Chart]": metrics.get("periods", "N/A"),
                "Views": metrics.get("views", 0),
                "Growth": metrics.get("growth", "N/A"),
                "[YouTube URL]": f"https://www.youtube.com/watch?v={vid}",
            })

        songs.sort(key=lambda x: x["Rank"])

        if not songs:
            print("   ❌ No tracks found.")
            return None

        # ---------------------------------------------------------------------
        # STEP 4: Save to CSV
        # ---------------------------------------------------------------------
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
        print(f"⚠️  Error: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============================================================================
# SQLITE PERSISTENCE
# ============================================================================
def update_sqlite_database(csv_path: Path, week_id: str) -> Path | None:
    print("   📊 Processing chart data into SQLite...")
    try:
        import sqlite3
        import pandas as pd

        df = pd.read_csv(csv_path, encoding="utf-8")
        
        current_time = datetime.now()
        df["download_date"] = current_time.strftime("%Y-%m-%d")
        df["download_time"] = current_time.strftime("%H:%M:%S")
        df["week_id"] = week_id
        df["timestamp"] = current_time.strftime("%Y%m%d_%H%M%S")

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
        
        for _, row in df.iterrows():
            cursor.execute(f"""
                INSERT INTO {temp_table_name} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(row))

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chart_data'")
        
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(chart_data)")
            existing_cols = len(cursor.fetchall())
            if existing_cols != 12:
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
# BACKUP & CLEANUP
# ============================================================================
def create_backup_before_update(week_id: str) -> None:
    db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
    if not db_path.exists(): return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"backup_{week_id}_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    print(f"   ✅ Backup created: {backup_path.name}")

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

# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("\n" + "=" * 70)
    print("🎵 YOUTUBE CHARTS - HYBRID EXTRACTOR (No Fallback)")
    print("=" * 70)

    if not install_dependencies():
        return 1

    week_id = get_week_identifier()
    print(f"\n📆 Current week: {week_id}")

    print("\n1. 📥 DOWNLOADING YOUTUBE CHARTS...")
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
