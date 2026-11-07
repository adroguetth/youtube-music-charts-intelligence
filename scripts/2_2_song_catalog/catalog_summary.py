"""
Catalog Summary - Reporting Module
============================================================================
Generates and prints a summary of the song catalog statistics.

This module is responsible for all read-only reporting of the catalog.
It does not modify the database; it only queries it to provide insights
into the current state of the catalog.

Features
--------
- Displays total unique songs and highest ID.
- Displays database file size.
- Displays the top 5 artists by number of unique songs.
- Displays the 10 most recent additions (for verification).
- Gracefully handles missing catalog or missing tables.

Dependencies
------------
- Internal: `.config` (paths, logger), `.utils.db_utils` (get_catalog_statistics).
- External: sqlite3 (stdlib).

Requirements
------------
- Python 3.7+

Notes
-----
- This function is idempotent and safe to call even if the catalog does not
  exist yet.
- All errors are caught and logged as warnings to ensure that a reporting
  failure does not crash the main pipeline.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import sqlite3
from .config import TARGET_DIR, TARGET_DB_NAME, logger
from .utils.db_utils import get_catalog_statistics


def list_catalog_summary() -> None:
    """
    Display summary statistics of the song catalog.

    Shows:
    - Total unique songs
    - Most recent additions (last 5)
    - Top artists by unique song count
    - Database file information

    This function is idempotent and safe to call even if catalog doesn't exist.
    """
    target_path = TARGET_DIR / TARGET_DB_NAME

    if not target_path.exists():
        logger.info("   ℹ️  Song catalog does not exist yet")
        logger.info("   💡 Run with migration first to create catalog")
        return

    try:
        conn = sqlite3.connect(target_path)
        cursor = conn.cursor()

        # Check if table exists (handles empty/partial databases)
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='artist_track'"
        )
        if not cursor.fetchone():
            logger.info("   ℹ️  artist_track table not found in catalog")
            conn.close()
            return

        # Get global statistics using the shared helper
        total_records, latest_id = get_catalog_statistics(conn)

        # Get most recent additions (for verification)
        cursor.execute("""
            SELECT id, artist_names, track_name, artist_country, macro_genre
            FROM artist_track
            ORDER BY id DESC
            LIMIT 5
        """)
        recent = cursor.fetchall()

        # Get top artists by song count (for analytics insights)
        cursor.execute("""
            SELECT artist_names, COUNT(*) as song_count
            FROM artist_track
            GROUP BY artist_names
            ORDER BY song_count DESC
            LIMIT 5
        """)
        top_artists = cursor.fetchall()

        conn.close()

        logger.info(f"\n📀 SONG CATALOG SUMMARY:")
        logger.info(f"   📊 Total unique songs: {total_records:,}")
        logger.info(f"   🔑 Highest ID: {latest_id}")
        logger.info(f"   💾 File size: {target_path.stat().st_size / 1024:.1f} KB")

        if top_artists:
            logger.info(f"\n   🏆 Top artists by unique songs:")
            for artist, count in top_artists:
                artist_display = artist[:50] + "..." if len(artist) > 50 else artist
                logger.info(f"      • {artist_display}: {count} songs")

        if recent:
            logger.info(f"\n   🆕 Most recent additions:")
            for entry_id, artist, track, country, genre in recent:
                artist_display = artist[:40] + "..." if len(artist) > 40 else artist
                track_display = track[:40] + "..." if len(track) > 40 else track
                logger.info(f"      [{entry_id:4d}] {artist_display} — {track_display}")
                logger.info(f"            🌍 {country} | 🎵 {genre}")

    except sqlite3.Error as e:
        logger.warning(f"   ⚠️  Error reading catalog: {e}")
