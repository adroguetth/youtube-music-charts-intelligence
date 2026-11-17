"""
YouTube Charts Data Scraper - Download & Persistence Pipeline
============================================================================
Hybrid approach:
1. `ytmusicapi` to fetch the weekly Top 100 songs and video IDs.
2. Apify's YouTube Scraper (h7sDV53CddomktSi5) to enrich the data with 
   exact view counts.
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
# YOUTUBE CHARTS DOWNLOADER (Hybrid: ytmusicapi + Apify)
# ============================================================================
async def download_youtube_charts() -> Path | None:
    print("🎵 YouTube Charts - Downloading Exact Metrics")
    print("=" * 70)

    try:
        import httpx
        from ytmusicapi import YTMusic

        # ---------------------------------------------------------------------
        # STEP 1: Get list of songs via ytmusicapi
        # ---------------------------------------------------------------------
        print("1. 📡 Fetching base playlist via ytmusicapi...")
        yt = YTMusic()
        charts = yt.get_charts(country="ZZ")
        
        playlist_id = None
        if "videos" in charts and charts["videos"]:
            playlist_id = charts["videos"][0].get("playlistId")
            
        if not playlist_id:
            print("   ❌ No playlist found.")
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
        print(f"   ✅ Retrieved {len(yt_tracks)} tracks from ytmusicapi.")

        # ---------------------------------------------------------------------
        # STEP 2: Get exact views via Apify Actor
        # ---------------------------------------------------------------------
        print("2. 📊 Fetching exact metrics via Apify...")
        
        apify_token = os.environ.get("APIFY_TOKEN")
        if not apify_token:
            print("   ⚠️  APIFY_TOKEN not set. Skipping view count enrichment.")
            view_data = {}
        else:
            # Build list of URLs to send to Apify
            video_urls = [f"https://www.youtube.com/watch?v={t['video_id']}" for t in yt_tracks]
            
            # Use the Actor ID you provided
            url = f"https://api.apify.com/v2/acts/h7sDV53CddomktSi5/run-sync-get-dataset-items?token={apify_token}"
            
            # The 'YouTube Scraper' accepts 'directUrls' for specific video pages
            payload = {
                "directUrls": video_urls,
                "maxResults": 100
            }

            headers = {"Content-Type": "application/json"}
            
            async with httpx.AsyncClient(timeout=180.0) as client:
                try:
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code in (200, 201):
                        apify_data = response.json()
                        # Map video_id to view_count
                        view_data = {
                            item.get("url", "").split("v=")[-1]: item.get("viewCount", 0) 
                            for item in apify_data if item.get("url")
                        }
                        print(f"   ✅ Enriched {len(view_data)} tracks with views.")
                    else:
                        print(f"   ⚠️  Apify Error {response.status_code}. Proceeding without view counts.")
                        view_data = {}
                except Exception as e:
                    print(f"   ⚠️  Apify request failed: {e}. Proceeding without view counts.")
                    view_data = {}

        # ---------------------------------------------------------------------
        # STEP 3: Merge Data and Save
        # ---------------------------------------------------------------------
        print("3. 🛠️  Merging data...")
        songs = []
        for track in yt_tracks:
            vid = track["video_id"]
            views = view_data.get(vid, 0)
            
            songs.append({
                "Rank": track["rank"],
                "[Previous Rank]": "N/A",  # Not provided by ytmusicapi or Apify
                "[Track Name]": track["title"],
                "[Artist Names]": track["artists"],
                "[Periods on Chart]": "N/A", # Not provided
                "Views": views,
                "Growth": "N/A", # Not provided
                "[YouTube URL]": f"https://www.youtube.com/watch?v={vid}",
            })

        # Save to CSV
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
