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
- External: `httpx`, `ytmusicapi`, `pandas`, `sqlite3` (stdlib).

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
        # charts.youtube.com uses the standard "WEB" client, NOT "WEB_REMIX"
        client_version = f"2.{today_str}.01.00"

        url = "https://charts.youtube.com/youtubei/v1/browse"
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB",  # Correct client for charts.youtube.com
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
                if response.status_code == 200:
                    data = response.json()
                    
                    # Save raw JSON for debugging
                    with open(ARCHIVE_DIR / "raw_api_response.json", "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)

                    # Recursively search for chart entries
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
                    print(f"   ⚠️  API returned HTTP {response.status_code}. Falling back to ytmusicapi data.")
        except Exception as e:
            print(f"   ⚠️  Error querying charts API: {e}. Falling back.")

        # ---------------------------------------------------------------------
        # STEP 3: Merge Data
        # ---------------------------------------------------------------------
        print("3. 🛠️  Merging data...")
        songs = []
        for idx, (vid, yt_data) in enumerate(yt_tracks.items(), start=1):
            # Check if we have exact metrics for this video ID
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

        # Sort by Rank (in case ytmusicapi returned them out of order)
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
async def download_youtube_charts() -> Path | None:
    print("🎵 YouTube Charts - Downloading Exact Metrics")
    print("=" * 70)

    try:
        from ytmusicapi import YTMusic
        import pandas as pd
        import json

        print("1. 📡 Connecting to YouTube Music API...")
        yt = YTMusic()

        print("2. 📊 Fetching global weekly charts...")
        charts = yt.get_charts(country="ZZ")

        # Save raw JSON for debugging
        raw_debug_path = ARCHIVE_DIR / "raw_ytmusicapi_response.json"
        with open(raw_debug_path, "w", encoding="utf-8") as f:
            json.dump(charts, f, indent=2)
        print(f"   📄 Raw JSON saved to: {raw_debug_path}")

        # Extract the playlist ID for Top Songs
        playlist_id = None
        if "videos" in charts and charts["videos"]:
            playlist_id = charts["videos"][0].get("playlistId")
            print(f"   🎯 Playlist ID found: {playlist_id}")
        
        if not playlist_id:
            print("   ❌ No playlist found in charts response.")
            return None

        print("3. 📥 Fetching detailed chart data...")
        # Instead of get_playlist, we need to use the raw JSON from get_charts.
        # The get_charts function returns a list of playlists, but the actual tracks
        # might be embedded in the JSON. Let's search for the tracks directly.
        
        songs = []
        
        # Recursive search for chart entries in the JSON
        def extract_tracks(obj):
            if isinstance(obj, dict):
                # Look for objects that have 'chartEntryData' and 'trackMetadata'
                if "chartEntryData" in obj and "trackMetadata" in obj:
                    entry = obj["chartEntryData"]
                    meta = obj["trackMetadata"]
                    
                    video_id = meta.get("videoId", "")
                    youtube_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
                    
                    # Extract metrics
                    current_rank = entry.get("currentRank", 0)
                    previous_rank = entry.get("previousRank", "N/A")
                    periods = entry.get("appearancesOnChart", "N/A")
                    
                    ranking_metric = entry.get("rankingMetric", {})
                    views_str = ranking_metric.get("value", "0")
                    growth = ranking_metric.get("change", "N/A")
                    
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

        extract_tracks(charts)

        # If no tracks found via chartEntryData, fall back to get_playlist
        if not songs:
            print("   ⚠️  No chartEntryData found in get_charts response. Falling back to get_playlist...")
            playlist = yt.get_playlist(playlist_id, limit=100)
            
            for idx, track in enumerate(playlist.get("tracks", []), start=1):
                video_id = track.get("videoId", "")
                youtube_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
                
                songs.append({
                    "Rank": idx,
                    "[Previous Rank]": "N/A",
                    "[Track Name]": track.get("title", ""),
                    "[Artist Names]": ", ".join([a.get("name", "") for a in track.get("artists", [])]),
                    "[Periods on Chart]": "N/A",
                    "Views": 0,
                    "Growth": "N/A",
                    "[YouTube URL]": youtube_url,
                })

        if not songs:
            print("   ❌ No tracks found.")
            return None

        # Sort by Rank
        songs.sort(key=lambda x: x["Rank"])
        songs = songs[:100]
        
        print(f"   ✅ Extracted {len(songs)} tracks with metrics.")

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
