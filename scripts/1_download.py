"""
YouTube Charts Data Scraper - Download & Persistence Pipeline
============================================================================
Top-level entry point for downloading the weekly YouTube Charts Top 100 songs
and persisting them into a localized SQLite database. This module acts as the
first stage in the broader intelligence pipeline.

This script uses a robust hybrid approach:
1. `ytmusicapi` to fetch the base playlist and video IDs reliably.
2. `yt-dlp` to extract exact view counts and video metadata for each track,
   bypassing the blocked charts.youtube.com API.

Dependencies
------------
- Internal: none (self-contained script).
- External: `ytmusicapi`, `yt-dlp`, `pandas`, `sqlite3` (stdlib).
- Downstream: Script 2.1 (Artist Metadata Enrichment) consumes the SQLite DBs.

Requirements
------------
- Python 3.7+
- `ytmusicapi`, `yt-dlp`, and `pandas` installed (auto-installed if missing).

Notes
-----
- **Strict Mode**: The legacy fallback mode has been removed.
- **API Stability**: `yt-dlp` handles YouTube's dynamic API changes automatically.
- **Performance**: Fetching metadata for 100 videos takes ~1-2 minutes.

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
    print("🔧 Checking dependencies (ytmusicapi, yt-dlp, pandas)...")
    try:
        from ytmusicapi import YTMusic
        import yt_dlp
        import pandas
        print("   ✅ Dependencies are installed")
        return True
    except ImportError:
        print("   📦 Installing dependencies...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "ytmusicapi", "yt-dlp", "pandas"], 
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
# YOUTUBE CHARTS DOWNLOADER (ytmusicapi + yt-dlp)
# ============================================================================
async def download_youtube_charts() -> Path | None:
    print("🎵 YouTube Charts - Downloading Exact Metrics")
    print("=" * 70)

    try:
        from ytmusicapi import YTMusic
        import yt_dlp
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
        yt_tracks = []
        for idx, track in enumerate(playlist.get("tracks", []), start=1):
            vid = track.get("videoId")
            if vid:
                yt_tracks.append({
                    "rank": idx,
                    "video_id": vid,
                    "title": track.get("title", ""),
                    "artists": ", ".join([a.get("name", "") for a in track.get("artists", [])])
                })
        print(f"   ✅ ytmusicapi retrieved {len(yt_tracks)} tracks.")

        # ---------------------------------------------------------------------
        # STEP 2: Use yt-dlp to get exact views and metadata for each video
        # ---------------------------------------------------------------------
        print("2. 📊 Fetching exact metrics via yt-dlp (this may take a minute)...")
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
        }

        songs = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for idx, track in enumerate(yt_tracks, start=1):
                vid = track["video_id"]
                url = f"https://www.youtube.com/watch?v={vid}"
                
                try:
                    # Extract metadata without downloading the video
                    info = ydl.extract_info(url, download=False)
                    
                    views = info.get("view_count", 0)
                    # Growth and Previous Rank are not available via yt-dlp
                    # We set them to N/A as they require historical context
                    growth = "N/A"
                    prev_rank = "N/A"
                    periods = "N/A"
                    
                    songs.append({
                        "Rank": track["rank"],
                        "[Previous Rank]": prev_rank,
                        "[Track Name]": track["title"],
                        "[Artist Names]": track["artists"],
                        "[Periods on Chart]": periods,
                        "Views": views,
                        "Growth": growth,
                        "[YouTube URL]": url,
                    })
                    
                    if idx % 10 == 0:
                        print(f"   ⏳ Processed {idx}/100 videos...")
                        
                except Exception as e:
                    print(f"   ⚠️  Failed to extract {vid}: {e}")
                    # Still add the track with default values
                    songs.append({
                        "Rank": track["rank"],
                        "[Previous Rank]": "N/A",
                        "[Track Name]": track["title"],
                        "[Artist Names]": track["artists"],
                        "[Periods on Chart]": "N/A",
                        "Views": 0,
                        "Growth": "N/A",
                        "[YouTube URL]": url,
                    })

        if not songs:
            print("   ❌ No tracks found.")
            return None

        print(f"   ✅ Extracted {len(songs)} tracks with view counts.")

        # ---------------------------------------------------------------------
        # STEP 3: Save to CSV
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
    print("🎵 YOUTUBE CHARTS - YT-DLP EXTRACTOR (No Fallback)")
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
