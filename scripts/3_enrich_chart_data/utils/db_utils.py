"""
DB Utils - SQLite Operations for Chart Enrichment
============================================================================
Database utilities for the chart enrichment pipeline. Handles reading the
latest chart database, loading the song catalog (from Script 2.2), and
writing the enriched output database.

This module contains NO metadata retrieval logic. It is solely responsible
for talking to SQLite: reading chart data, building in-memory lookups, and
managing the output schema.

Features
--------
- Latest chart detection: lexicographic sort of `youtube_charts_YYYY-WXX.db`
  filenames to identify the most recent week.
- Robust reading: handles duplicate ranks via `rowid`-based deduplication.
- In-memory catalog lookup: loads the entire `artist_track` table from the
  Script 2.2 output into a dict for O(1) resolution.
- Idempotent output table: `DROP + CREATE` on every run to guarantee exactly
  one enriched row per chart entry.

Dependencies
------------
- Internal: `..config` (paths, logger).
- External: sqlite3, pathlib (stdlib).

Requirements
------------
- Python 3.7+

Notes
-----
- If the song catalog file (from Script 2.2) is missing, the function logs a
  warning and returns an empty dict. The pipeline continues with `id = NULL`
  and `Unknown` country/genre, so no data is lost.
- The output table (`enriched_songs`) is fully derived: dropping it on every
  run is intentional and ensures idempotency.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import sqlite3
from pathlib import Path

from ..config import INPUT_DB_DIR, SONG_CATALOG_DB_PATH, logger


# ============================================================================
# INPUT READING
# ============================================================================
def find_latest_chart_db() -> Path:
    """
    Locate the most recent chart database file by lexicographic sort.

    Filenames follow the pattern `youtube_charts_YYYY-WXX.db`, so
    lexicographic order is equivalent to chronological order.

    Returns
    -------
    Path
        Path to the latest `.db` file.

    Raises
    ------
    FileNotFoundError
        If the input directory or any `.db` files are absent.
    """
    if not INPUT_DB_DIR.exists():
        raise FileNotFoundError(f"Input directory not found: {INPUT_DB_DIR}")

    db_files = list(INPUT_DB_DIR.glob("*.db"))
    if not db_files:
        raise FileNotFoundError(f"No .db files found in {INPUT_DB_DIR}")

    db_files.sort(key=lambda p: p.name, reverse=True)
    return db_files[0]


def load_chart_songs(db_path: Path) -> list:
    """
    Read all rows from the `chart_data` table into a list of dicts.

    Validates that the required columns (Rank, Artist Names, Track Name,
    YouTube URL) are present before returning data. Duplicate ranks (which
    can occur if Script 1 ran twice for the same week) are deduplicated by
    keeping the first occurrence of each Rank.

    Parameters
    ----------
    db_path : Path
        Path to the SQLite chart database.

    Returns
    -------
    list of dict
        One dict per chart row.

    Raises
    ------
    Exception
        If the table is missing or required columns are absent.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chart_data'"
    )
    if not cursor.fetchone():
        conn.close()
        raise Exception(f"Table 'chart_data' not found in {db_path}")

    # Use ROW_NUMBER()-like deduplication via MIN(rowid) per Rank. This guards
    # against duplicate weekly runs that may have written the same chart twice.
    cursor.execute("""
        SELECT * FROM chart_data
        WHERE rowid IN (
            SELECT MIN(rowid) FROM chart_data GROUP BY Rank
        )
        ORDER BY Rank
    """)
    rows = cursor.fetchall()
    conn.close()

    songs = [dict(row) for row in rows]

    required_columns = {"Rank", "Artist Names", "Track Name", "YouTube URL"}
    if songs:
        actual_columns = set(songs[0].keys())
        missing = required_columns - actual_columns
        if missing:
            raise Exception(f"Missing columns in chart_data: {missing}")

    return songs


# ============================================================================
# CATALOG LOOKUP
# ============================================================================
def load_song_catalog_lookup() -> dict:
    """
    Load the song catalog (`artist_track` table) into an in-memory dict.

    The key is a tuple of `(artist_names, track_name)` exactly as stored in
    the catalog. The value is a tuple of
    `(id, artist_country, macro_genre, artists_found)`.

    Returns
    -------
    dict
        Mapping of `{(artist_names, track_name): (id, country, genre, artists_found)}`.

    Notes
    -----
    If the catalog file does not exist, an empty dict is returned and the
    pipeline continues with `id = NULL` and `Unknown` country/genre.
    """
    catalog_lookup = {}

    if not SONG_CATALOG_DB_PATH.exists():
        logger.warning(f"⚠️  Song catalog not found at {SONG_CATALOG_DB_PATH}.")
        logger.warning("   Please run 2_2.build_song_catalog first to create the catalog.")
        logger.warning("   Continuing with id = NULL and empty country/genre for all records.")
        return catalog_lookup

    logger.info(f"📀 Loading song catalog for ID mapping from: {SONG_CATALOG_DB_PATH}")

    try:
        conn = sqlite3.connect(SONG_CATALOG_DB_PATH)
        cursor = conn.cursor()

        # Verify that the expected table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='artist_track'"
        )
        if not cursor.fetchone():
            logger.error("   ❌ Table 'artist_track' not found in catalog database.")
            logger.error("      Please ensure 2_2.build_song_catalog has been run successfully.")
            conn.close()
            return catalog_lookup

        cursor.execute("""
            SELECT artist_names, track_name, id, artist_country, macro_genre, artists_found
            FROM artist_track
        """)
        rows = cursor.fetchall()
        conn.close()

        for artist_names, track_name, song_id, country, genre, found in rows:
            catalog_lookup[(artist_names, track_name)] = (song_id, country, genre, found)

        logger.info(f"   ✅ Loaded {len(catalog_lookup)} songs from catalog.")

        # Show first 5 entries for verification
        if rows:
            logger.info("   📋 Sample entries from catalog (first 5):")
            for i, (art, trk, sid, country, genre, found) in enumerate(rows[:5], 1):
                art_short = art[:30] + "..." if len(art) > 30 else art
                trk_short = trk[:30] + "..." if len(trk) > 30 else trk
                logger.info(f"      {i}. ID {sid:4d} | {art_short} - {trk_short}")
                logger.info(f"         🌍 {country} | 🎵 {genre} | 👥 {found}")

        return catalog_lookup

    except sqlite3.Error as e:
        logger.error(f"   ❌ Error reading song catalog: {e}")
        return catalog_lookup


# ============================================================================
# OUTPUT WRITING
# ============================================================================
def create_output_table(conn: sqlite3.Connection) -> None:
    """
    (Re)create the `enriched_songs` table from scratch on every pipeline run.

    `DROP + CREATE` is intentional: this is a fully derived table. Re-running
    the pipeline should always produce exactly one enriched row per chart
    entry, never append on top of a previous run.

    The column `id` is a foreign key referencing `artist_track.id`. It is
    defined as `UNIQUE` rather than `PRIMARY KEY` so the implicit `rowid`
    preserves the insertion order (by rank) as the default physical ordering.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open SQLite connection to the output database.
    """
    cursor = conn.cursor()

    # Wipe any previous run — idempotent by design
    cursor.execute("DROP TABLE IF EXISTS enriched_songs")
    cursor.execute("""
        CREATE TABLE enriched_songs (
            rank INTEGER,
            id INTEGER UNIQUE,
            artist_names TEXT,
            track_name TEXT,
            periods_on_chart INTEGER,
            views INTEGER,
            youtube_url TEXT,
            duration_s INTEGER,
            duration_ms TEXT,
            upload_date TEXT,
            likes INTEGER,
            comment_count INTEGER,
            audio_language TEXT,
            is_official_video BOOLEAN,
            is_lyric_video BOOLEAN,
            is_live_performance BOOLEAN,
            upload_season TEXT,
            channel_type TEXT,
            is_collaboration BOOLEAN,
            artist_count INTEGER,
            region_restricted BOOLEAN,
            artist_country TEXT,
            macro_genre TEXT,
            artists_found TEXT,
            error TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (id) REFERENCES artist_track(id)
        )
    """)
    cursor.execute("CREATE INDEX idx_country ON enriched_songs(artist_country)")
    cursor.execute("CREATE INDEX idx_genre ON enriched_songs(macro_genre)")
    cursor.execute("CREATE INDEX idx_upload_date ON enriched_songs(upload_date)")
    cursor.execute("CREATE INDEX idx_error ON enriched_songs(error)")
    conn.commit()


def insert_enriched_row(conn: sqlite3.Connection, row: dict) -> None:
    """
    Insert a single enriched song record into the output table.

    The INSERT statement explicitly lists all columns except `processed_at`
    (which has a DEFAULT value). Exactly 25 values are provided.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open SQLite connection.
    row : dict
        Dict with keys matching the `enriched_songs` schema.
    """
    cursor = conn.cursor()
    # Column count: 25 columns (rank, id, ... error)
    cursor.execute("""
        INSERT INTO enriched_songs (
            rank, id, artist_names, track_name, periods_on_chart, views, youtube_url,
            duration_s, duration_ms, upload_date, likes, comment_count,
            audio_language, is_official_video, is_lyric_video, is_live_performance,
            upload_season, channel_type, is_collaboration, artist_count,
            region_restricted, artist_country, macro_genre,
            artists_found, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row["rank"], row["id"], row["artist_names"], row["track_name"],
        row["periods_on_chart"], row["views"], row["youtube_url"],
        row["duration_s"], row["duration_ms"], row["upload_date"],
        row["likes"], row["comment_count"], row["audio_language"],
        row["is_official_video"], row["is_lyric_video"], row["is_live_performance"],
        row["upload_season"], row["channel_type"], row["is_collaboration"],
        row["artist_count"], row["region_restricted"], row["artist_country"],
        row["macro_genre"], row["artists_found"], row["error"]
    ))
    conn.commit()
