"""
DB Utils - SQLite Operations for Song Catalog
============================================================================
Database utilities for the song catalog builder. Handles schema
initialization/migration, statistics retrieval, and artist lookup loading
from the artist metadata database (produced by Script 2.1).

This module contains NO business logic. It is solely responsible for
talking to SQLite: creating tables, running migrations, and reading data.
All resolution logic (country/genre inference) lives in `resolver.py`.

Features
--------
- Idempotent schema creation: creates the `artist_track` table only if it
  does not already exist.
- Safe schema migration: adds missing columns (`artist_country`,
  `macro_genre`, `artists_found`) to existing tables without data loss.
- In-memory artist lookup: loads all artists from Script 2.1's database
  into a dict for O(1) lookups during resolution.
- Catalog statistics: returns total record count and highest ID for
  progress tracking and verification.

Dependencies
------------
- Internal: `.config` (paths, logger), `.artist_parser` (normalize_name).
- External: sqlite3, typing (stdlib).

Requirements
------------
- Python 3.7+
- sqlite3 (included in Python standard library).

Notes
-----
- The target table uses a composite natural key `(artist_names, track_name)`
  for deduplication, plus an auto-incremented surrogate `id` for stable
  references.
- The `artists_found` column stores a `"matched/total"` string (e.g.,
  `"2/3"`) for transparency about collaboration resolution.
- Schema migration uses `ALTER TABLE ADD COLUMN` with default values, so
  existing records are preserved and immediately queryable.
- If the artist database (from Script 2.1) is missing, the function exits
  with a clear error message. The ETL pipeline should not proceed without
  artist metadata.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import sqlite3
import sys
from typing import Dict, Optional, Tuple

from ..config import ARTIST_DB_PATH, logger
from .artist_parser import normalize_name


# ============================================================================
# SCHEMA MANAGEMENT
# ============================================================================
def initialize_target_schema(connection: sqlite3.Connection) -> None:
    """
    Ensure the target catalog table exists with the correct schema.

    Creates the `artist_track` table if it doesn't exist with the following
    structure:

        id             : INTEGER PRIMARY KEY AUTOINCREMENT
        artist_names   : VARCHAR(200) NOT NULL
        track_name     : VARCHAR(200) NOT NULL
        artist_country : TEXT NOT NULL
        macro_genre    : TEXT NOT NULL
        artists_found  : TEXT

    If the table already exists but lacks any of the columns added after the
    initial version (`artist_country`, `macro_genre`, `artists_found`), they
    are added via `ALTER TABLE` with safe defaults.

    Parameters
    ----------
    connection : sqlite3.Connection
        Active connection to the target database.

    Returns
    -------
    None

    Raises
    ------
    sqlite3.Error
        If schema creation or migration fails.
    """
    cursor = connection.cursor()

    # Check if table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='artist_track'"
    )
    table_exists = cursor.fetchone() is not None

    if not table_exists:
        ddl_statement = """
            CREATE TABLE artist_track (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                artist_names   VARCHAR(200) NOT NULL,
                track_name     VARCHAR(200) NOT NULL,
                artist_country TEXT NOT NULL,
                macro_genre    TEXT NOT NULL,
                artists_found  TEXT
            )
        """
        try:
            with connection:
                connection.execute(ddl_statement)
            logger.info("   ✅ Created artist_track table with extended schema.")
        except sqlite3.Error as e:
            logger.error(f"   ❌ Schema initialization error: {e}")
            raise
        return

    # Table exists: check for missing columns and add them
    cursor.execute("PRAGMA table_info(artist_track)")
    columns = {row[1] for row in cursor.fetchall()}

    new_columns = []
    if "artist_country" not in columns:
        new_columns.append(("artist_country", 'TEXT NOT NULL DEFAULT "Unknown"'))
    if "macro_genre" not in columns:
        new_columns.append(("macro_genre", 'TEXT NOT NULL DEFAULT "Pop"'))
    if "artists_found" not in columns:
        new_columns.append(("artists_found", "TEXT"))

    for col_name, col_def in new_columns:
        try:
            with connection:
                connection.execute(
                    f"ALTER TABLE artist_track ADD COLUMN {col_name} {col_def}"
                )
            logger.info(
                f"   ✅ Added column {col_name} to existing artist_track table."
            )
        except sqlite3.Error as e:
            logger.warning(f"   ⚠️  Could not add column {col_name}: {e}")

    if new_columns:
        logger.info("   ✅ Schema migration completed.")
    else:
        logger.info("   ✅ Schema already up to date.")


# ============================================================================
# STATISTICS
# ============================================================================
def get_catalog_statistics(
    connection: sqlite3.Connection,
) -> Tuple[int, int]:
    """
    Retrieve current catalog statistics.

    Parameters
    ----------
    connection : sqlite3.Connection
        Active connection to the target database.

    Returns
    -------
    tuple of (int, int)
        `(total_records, latest_id)` where:
        - `total_records` is the total number of unique songs in the catalog.
        - `latest_id` is the highest auto-generated ID (0 if table is empty).
    """
    cursor = connection.cursor()
    cursor.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM artist_track"
    )
    total_records, latest_id = cursor.fetchone()
    return total_records, latest_id


# ============================================================================
# ARTIST LOOKUP
# ============================================================================
def load_artist_lookup() -> Dict[str, Tuple[str, str]]:
    """
    Load all artist records from the Script 2.1 database into memory.

    The database is expected at the path defined by `ARTIST_DB_PATH` in
    `config.py` (i.e., `charts_archive/2_1.countries-genres-artist/
    artist_countries_genres.db`).

    Artist names are normalized via `normalize_name` so that lookups during
    resolution are O(1) regardless of casing, punctuation, or whitespace
    differences.

    Returns
    -------
    dict
        Mapping of `{normalized_name: (country, macro_genre)}`.

    Raises
    ------
    SystemExit
        If the artist database file does not exist.
    sqlite3.Error
        If the database cannot be read.
    """
    if not ARTIST_DB_PATH.exists():
        logger.error(f"   ❌ Artist database not found at: {ARTIST_DB_PATH}")
        logger.error("      Please ensure Script 2.1 has run successfully.")
        sys.exit(1)

    logger.info("   🌍 Loading artist metadata database from local path...")

    try:
        conn = sqlite3.connect(ARTIST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name, country, macro_genre FROM artist")
        rows = cursor.fetchall()
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"   ❌ Error reading artist database: {e}")
        sys.exit(1)

    artist_lookup: Dict[str, Tuple[str, str]] = {}
    for raw_name, country, genre in rows:
        key = normalize_name(raw_name)
        artist_lookup[key] = (country, genre)

    logger.info(f"   ✅ Loaded {len(artist_lookup):,} artists from local DB.")
    return artist_lookup
