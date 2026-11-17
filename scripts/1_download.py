"""
YouTube Charts Data Scraper - Download & Persistence Pipeline
============================================================================
Top-level entry point for downloading the weekly YouTube Charts Top 100 songs
and persisting them into a localized SQLite database. This module acts as the
first stage in the broader intelligence pipeline.

This script orchestrates the extraction of chart data using the `ytmusicapi`
library, circumventing the need for browser automation and its
associated anti-bot mitigations. It implements a strict "fail-hard" policy: if
the extraction or persistence fails, the pipeline aborts immediately to prevent
data pollution from fallback synthetic records.

Features
--------
- Downloads the complete weekly Top 100 songs CSV from YouTube Charts.
- Leverages `ytmusicapi` for direct API access, bypassing HTML parsing and
  browser CAPTCHAs.
- Stores historical data in SQLite with versioning based on ISO week format
  (`YYYY-WXX`).
- Implements an automatic backup system before database mutations.
- Enforces a strict no-fallback policy: pipeline aborts if extraction fails.

Dependencies
------------
- Internal: none (self-contained script).
- External: `ytmusicapi`, `pandas`, `sqlite3` (stdlib), `asyncio`, `shutil`,
  `subprocess`.
- Downstream: Script 2.1 (Artist Metadata Enrichment) consumes the generated
  SQLite databases.

Requirements
------------
- Python 3.7+
- `ytmusicapi` and `pandas` installed (auto-installed if missing).
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
- **API Stability**: `ytmusicapi` is used over raw InnerTube requests to
  automatically handle dynamic `clientVersion` generation and token rotation.

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
    
    Uses `ytmusicapi` for API access and `pandas` for data manipulation.
    """
    print("🔧 Checking dependencies (ytmusicapi, pandas)...")
    try:
        from ytmusicapi import YTMusic
        import pandas
        print("   ✅ Dependencies are installed")
        return True
    except ImportError:
        print("   📦 Installing ytmusicapi and pandas...")
        # Use sys.executable to ensure installation in the current virtual environment.
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "ytmusicapi", "pandas"], 
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
    
    Args:
        date (datetime, optional): The date to extract the week from. 
                                   Defaults to current datetime.
    
    Returns:
        str: Formatted ISO week string.
    """
    if date is None:
        date = datetime.now()
    year, week_num, _ = date.isocalendar()
    return f"{year}-W{week_num:02d}"

# ============================================================================
# YOUTUBE CHARTS DOWNLOADER (ytmusicapi)
# ============================================================================
async def download_youtube_charts() -> Path | None:
    """
    Download YouTube Charts data using `ytmusicapi`.
    
    This function bypasses browser automation entirely. It queries the YouTube
    Music API for the global weekly charts, extracts the Top 100 tracks, and
    serializes them into a CSV file.
    
    Returns:
        Path | None: The path to the generated CSV file if successful, 
                     None otherwise.
    """
    print("🎵 YouTube Charts - Downloading via ytmusicapi")
    print("=" * 70)

    try:
        from ytmusicapi import YTMusic
        import pandas as pd

        print("1. 📡 Connecting to YouTube Music API...")
        # Initialize unauthenticated client for public chart data.
        yt = YTMusic()

        print("2. 📊 Fetching global weekly charts...")
        # 'ZZ' is the country code for Global charts.
        charts = yt.get_charts(country="ZZ")

        # Persist raw JSON for debugging and downstream auditing.
        raw_debug_path = ARCHIVE_DIR / "raw_ytmusicapi_response.json"
        with open(raw_debug_path, "w", encoding="utf-8") as f:
            json.dump(charts, f, indent=2)
        print(f"   📄 Raw JSON saved to: {raw_debug_path}")

        # Extract the playlist ID for Top Songs.
        # The structure typically maps to 'videos' for Top Music Videos.
        playlist_id = None
        if "videos" in charts and charts["videos"]:
            playlist_id = charts["videos"][0].get("playlistId")
            print(f"   🎯 Playlist ID found: {playlist_id}")
        
        if not playlist_id:
            print("   ❌ No playlist found in charts response.")
            return None

        print("3. 📥 Fetching tracks from playlist...")
        # Limit to 100 to match the official Top 100 chart scope.
        playlist = yt.get_playlist(playlist_id, limit=100)
        
        songs = []
        for idx, track in enumerate(playlist.get("tracks", []), start=1):
            songs.append({
                "Rank": idx,
                "Track Name": track.get("title", ""),
                "Artist Names": ", ".join([a.get("name", "") for a in track.get("artists", [])]),
                "Views": track.get("views", ""),
                "Duration": track.get("duration", ""),
            })

        if not songs:
            print("   ❌ No tracks found in playlist.")
            return None

        print(f"   ✅ Extracted {len(songs)} tracks.")

        # Serialize to CSV using pandas for consistent formatting.
        filename = DOWNLOAD_DIR / "latest_chart.csv"
        df = pd.DataFrame(songs)
        df.to_csv(filename, index=False, encoding="utf-8")

        print(f"   💾 CSV saved: {filename} ({filename.stat().st_size} bytes)")
        return filename

    except Exception as e:
        print(f"⚠️  Error with ytmusicapi: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============================================================================
# DATABASE MANAGEMENT
# ============================================================================
def create_backup_before_update(week_id: str) -> None:
    """
    Create a timestamped backup of the existing SQLite database before update.
    
    Args:
        week_id (str): The ISO week identifier.
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
    
    Args:
        days (int): Retention period in days.
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
    
    Args:
        weeks (int): Retention period in weeks.
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
# SQLITE PERSISTENCE
# ============================================================================
def update_sqlite_database(csv_path: Path, week_id: str) -> Path | None:
    """
    Update the SQLite database with the new chart data.
    
    Implements an atomic update strategy: inserts data into a temp table,
    then replaces the target table/rows within a transaction.
    
    Args:
        csv_path (Path): Path to the downloaded CSV file.
        week_id (str): The ISO week identifier.
        
    Returns:
        Path | None: The path to the updated database, or None on failure.
    """
    print("   📊 Processing chart data...")
    try:
        import sqlite3
        import pandas as pd

        df = pd.read_csv(csv_path, encoding="utf-8")
        
        # Enrich dataframe with metadata for historical tracking.
        current_time = datetime.now()
        df["download_date"] = current_time.strftime("%Y-%m-%d")
        df["week_id"] = week_id

        db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
        if db_path.exists(): 
            create_backup_before_update(week_id)

        conn = sqlite3.connect(db_path)
        temp_table_name = f"temp_{current_time.strftime('%Y%m%d_%H%M%S')}"
        
        # 1. Write to a temporary table to avoid partial writes.
        df.to_sql(temp_table_name, conn, if_exists="replace", index=False)

        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chart_data'")
        
        if cursor.fetchone():
            # 2a. If table exists, delete old records for this week and append.
            cursor.execute("DELETE FROM chart_data WHERE week_id = ?", (week_id,))
            cursor.execute(f"INSERT INTO chart_data SELECT * FROM {temp_table_name}")
            cursor.execute(f"DROP TABLE {temp_table_name}")
        else:
            # 2b. If table doesn't exist, promote the temp table.
            cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO chart_data")

        conn.commit()
        conn.close()
        
        print(f"   ✅ Database updated: {db_path}")
        return db_path
        
    except Exception as e:
        print(f"⚠️  SQLite error: {e}")
        return None

# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================
def main() -> int:
    """
    Entry point for the download and persistence pipeline.
    
    Returns:
        int: Exit code (0 for success, 1 for failure).
    """
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

    # Strict mode: Abort if download fails. No synthetic data allowed.
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
