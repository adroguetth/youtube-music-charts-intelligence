"""
Main - Entry Point for Chart Enrichment Pipeline
============================================================================
Command-line entry point for the `3_enrich_chart_data` package.

This module acts as a thin orchestrator. It coordinates the enrichment
pipeline by calling the appropriate utility and metadata modules, without
containing any business logic itself.

Workflow:
    1. Locate the latest weekly chart database.
    2. Load the song catalog for ID, country, genre, and artists_found.
    3. Ensure yt-dlp is available (install if missing).
    4. Load chart songs from SQLite.
    5. Create the output enriched database.
    6. For each song: fetch YouTube metadata, look up catalog data, write row.
    7. Print summary statistics.

Features
--------
- Executable as a module (`python -m scripts.3_enrich_chart_data`).
- Proper exit codes for CI/CD integration.
- Interactive prompt (only when running locally without an API key).

Dependencies
------------
- Internal: `.config` (paths, logger), `.utils.db_utils`
  (find_latest_chart_db, load_chart_songs, load_song_catalog_lookup,
  create_output_table, insert_enriched_row), `.metadata`
  (fetch_video_metadata).
- External: sqlite3, subprocess, sys, time (stdlib).

Requirements
------------
- Python 3.7+

Notes
-----
- This module is deliberately kept minimal. Any new logic should be added
  to the respective submodules.
- The interactive prompt block is skipped when `GITHUB_ACTIONS` is set.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import sqlite3
import subprocess
import sys
import time
from datetime import datetime

from .config import (
    IN_GITHUB_ACTIONS,
    OUTPUT_DIR,
    YOUTUBE_API_KEY,
    logger,
)
from .metadata import fetch_video_metadata
from .utils.db_utils import (
    create_output_table,
    find_latest_chart_db,
    insert_enriched_row,
    load_chart_songs,
    load_song_catalog_lookup,
)


def _ensure_ytdlp() -> None:
    """
    Ensure the `yt-dlp` package is available, installing it if missing.

    This is a lightweight check that runs at the start of the pipeline.
    The heavier dependency checks (Selenium, google-api-python-client) are
    handled lazily inside their respective layers.

    Returns
    -------
    None
    """
    try:
        import yt_dlp  # noqa: F401
        logger.info("   ✅ yt-dlp available")
    except ImportError:
        logger.info("   📦 Installing yt-dlp...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
        logger.info("   ✅ yt-dlp installed")


def _format_status_badges(metadata: dict, artist_country: str, song_id: int | None) -> str:
    """
    Build a compact inline status string for console feedback.

    Parameters
    ----------
    metadata : dict
        Metadata dict returned by `fetch_video_metadata`.
    artist_country : str
        Resolved country from the catalog lookup.
    song_id : int or None
        Catalog ID, if the song was matched.

    Returns
    -------
    str
        Compact badge string, or an error snippet if no data was retrieved.
    """
    badges = []
    if metadata["Duration (s)"] > 0:
        badges.append(f"⏱️{metadata['duration (m:s)']}")
    if metadata["is_official_video"]:
        badges.append("📀")
    if metadata["is_lyric_video"]:
        badges.append("📝")
    if metadata["is_live_performance"]:
        badges.append("🎤")
    if metadata["is_collaboration"]:
        badges.append(f"👥{metadata['artist_count']}")
    if artist_country not in ["Unknown", "Multi-country"]:
        badges.append(f"🌍{artist_country[:2]}")
    elif artist_country == "Multi-country":
        badges.append("🌐")
    if song_id is not None:
        badges.append(f"🆔{song_id}")

    if badges:
        return f"({' '.join(badges)}) → {artist_country[:15]}, {metadata.get('_macro_genre', 'N/A')[:15]}"

    error_display = metadata["error"][:20] if metadata["error"] else "No data"
    return f"({error_display})"


def main() -> int:
    """
    Execute the chart enrichment pipeline.

    Returns
    -------
    int
        Exit code (0 = success, 1 = critical error).
    """
    logger.info("\n" + "=" * 70)
    logger.info("🎵 CHART ENRICHMENT PIPELINE (API → Selenium → yt-dlp)")
    logger.info("   METADATA EXTRACTION + CATALOG INTEGRATION")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    # -------------------------------------------------------------------------
    # Phase 1: Locate latest chart database
    # -------------------------------------------------------------------------
    logger.info("\n1. 📂 LOCATING LATEST CHART DATABASE...")
    try:
        chart_db_path = find_latest_chart_db()
        logger.info(f"   ✅ Found: {chart_db_path.name}")
    except Exception as e:
        logger.error(f"   ❌ {e}")
        return 1

    # -------------------------------------------------------------------------
    # Phase 2: Load song catalog
    # -------------------------------------------------------------------------
    logger.info("\n2. 📀 LOADING SONG CATALOG...")
    song_catalog_lookup = load_song_catalog_lookup()

    # -------------------------------------------------------------------------
    # Phase 3: Ensure yt-dlp is available
    # -------------------------------------------------------------------------
    logger.info("\n3. 🔧 CHECKING DEPENDENCIES...")
    _ensure_ytdlp()

    # -------------------------------------------------------------------------
    # Phase 4: Load chart songs
    # -------------------------------------------------------------------------
    logger.info(f"\n4. 📖 READING CHART DATA FROM {chart_db_path.name}...")
    try:
        songs = load_chart_songs(chart_db_path)
        logger.info(f"   ✅ {len(songs)} songs loaded")
    except Exception as e:
        logger.error(f"   ❌ Error reading chart database: {e}")
        return 1

    # -------------------------------------------------------------------------
    # Phase 5: Prepare output database
    # -------------------------------------------------------------------------
    logger.info("\n5. 🗃️  PREPARING OUTPUT DATABASE...")
    output_db_path = OUTPUT_DIR / f"{chart_db_path.stem}_enriched.db"
    conn_out = sqlite3.connect(output_db_path)
    create_output_table(conn_out)
    logger.info(f"   ✅ Output path: {output_db_path}")

    # -------------------------------------------------------------------------
    # Phase 6: Process each song
    # -------------------------------------------------------------------------
    logger.info(f"\n6. 🎬 ENRICHING {len(songs)} SONGS...")
    logger.info("   ⏱️  This may take several minutes depending on the retrieval layer used...")

    for i, song in enumerate(songs, 1):
        url = song["YouTube URL"]
        track = song["Track Name"][:30]
        artists_csv = song.get("Artist Names", "")

        # Inline progress prefix (no newline — status appended after metadata)
        print(f"   [{i:2d}/{len(songs)}] {track:30}... ", end="", flush=True)

        # Fetch YouTube metadata (three-layer fallback)
        metadata = fetch_video_metadata(url, artists_csv, YOUTUBE_API_KEY)

        # Look up catalog data
        catalog_entry = song_catalog_lookup.get((artists_csv, song["Track Name"]))
        if catalog_entry:
            song_id, artist_country, macro_genre, artists_found = catalog_entry
        else:
            song_id, artist_country, macro_genre, artists_found = None, "Unknown", "Pop", "0/0"

        # Build output row
        row = {
            "rank": song.get("Rank"),
            "id": song_id,
            "artist_names": artists_csv,
            "track_name": song.get("Track Name"),
            "periods_on_chart": song.get("Periods on Chart"),
            "views": song.get("Views"),
            "youtube_url": url,
            "duration_s": metadata["Duration (s)"],
            "duration_ms": metadata["duration (m:s)"],
            "upload_date": metadata["upload_date"],
            "likes": metadata["likes"],
            "comment_count": metadata["comment_count"],
            "audio_language": metadata["audio_language"],
            "is_official_video": metadata["is_official_video"],
            "is_lyric_video": metadata["is_lyric_video"],
            "is_live_performance": metadata["is_live_performance"],
            "upload_season": metadata["upload_season"],
            "channel_type": metadata["channel_type"],
            "is_collaboration": metadata["is_collaboration"],
            "artist_count": metadata["artist_count"],
            "region_restricted": metadata["region_restricted"],
            "artist_country": artist_country,
            "macro_genre": macro_genre,
            "artists_found": artists_found,
            "error": metadata["error"],
        }

        insert_enriched_row(conn_out, row)

        # Inline status suffix (completes the line started above)
        metadata_for_display = {**metadata, "_macro_genre": macro_genre}
        print(_format_status_badges(metadata_for_display, artist_country, song_id))

        # Brief pause to avoid hammering endpoints when API is not used
        time.sleep(0.1)

    conn_out.close()

    # -------------------------------------------------------------------------
    # Phase 7: Summary statistics
    # -------------------------------------------------------------------------
    logger.info("\n7. 📊 FINAL SUMMARY:")
    conn_stats = sqlite3.connect(output_db_path)
    cur = conn_stats.cursor()

    cur.execute("SELECT COUNT(*) FROM enriched_songs")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM enriched_songs WHERE artist_country = 'Multi-country'")
    multi_country = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(DISTINCT artist_country) FROM enriched_songs "
        "WHERE artist_country NOT IN ('Unknown', 'Multi-country')"
    )
    unique_countries = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(DISTINCT macro_genre) FROM enriched_songs "
        "WHERE macro_genre != 'Multi-genre' AND macro_genre IS NOT NULL"
    )
    unique_genres = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM enriched_songs WHERE artist_country = 'Unknown'")
    unknown_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM enriched_songs WHERE error != ''")
    error_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM enriched_songs WHERE id IS NOT NULL")
    songs_with_id = cur.fetchone()[0]

    conn_stats.close()

    logger.info(f"   💾 Output database: {output_db_path}")
    logger.info(f"      📊 Total songs:              {total}")
    logger.info(f"      🌐 Multi-country collabs:    {multi_country} ({multi_country / total * 100:.1f}%)")
    logger.info(f"      🗺️  Distinct countries:       {unique_countries}")
    logger.info(f"      🎵 Distinct genres:           {unique_genres}")
    logger.info(f"      ❓ Songs with unknown country: {unknown_count} ({unknown_count / total * 100:.1f}%)")
    logger.info(f"      ⚠️  Songs with metadata errors: {error_count} ({error_count / total * 100:.1f}%)")
    logger.info(f"      🆔 Songs with catalog ID:      {songs_with_id} ({songs_with_id / total * 100:.1f}%)")

    logger.info("\n" + "=" * 70)
    logger.info("✅ ENRICHMENT PIPELINE COMPLETED SUCCESSFULLY")
    logger.info("=" * 70)

    return 0


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    # Interactive warning only when running locally without an API key.
    # In CI/CD (GitHub Actions) this block is skipped entirely.
    if not IN_GITHUB_ACTIONS and not YOUTUBE_API_KEY:
        logger.warning("\n⚠️  YOUTUBE_API_KEY environment variable is not set.")
        logger.warning("   Metadata will be fetched via Selenium and yt-dlp (slower).")
        answer = input("Continue anyway? (y/n): ").strip().lower()
        if answer not in ["y", "yes"]:
            logger.info("Process cancelled.")
            sys.exit(0)

    sys.exit(main())
