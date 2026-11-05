"""
DB Utils - SQLite Database Operations for the Artist Database
============================================================================
Utility module for all SQLite database operations used by the artist
database builder. Handles creation of the artist database, insertion and
update of artist records, lookup of existing artists, and reading of
artist names from the YouTube chart database produced by the scraper
pipeline.

The module manages two distinct databases:

1. **Artist database** (`ARTIST_DB_PATH`) — the persistent store of
   resolved artist metadata, with columns `name` (PK), `country`, and
   `macro_genre`. Written by `insert_artist()` and read by
   `artist_in_database()`.
2. **Chart databases** (`CHARTS_DB_DIR/youtube_charts_YYYY-WW.db`) — the
   weekly scraped chart snapshots. Read by
   `get_artists_from_chart_db()` to enumerate artists that need metadata
   resolution.

Features
--------
- Idempotent schema creation (`create_database()`) with automatic
  migration for the `macro_genre` column on pre-existing tables.
- Partial-update semantics on insert (`insert_artist()`): an existing
  artist's `country` or `macro_genre` is only overwritten when the new
  value is non-placeholder (`!= "Unknown"`), preserving previously
  resolved data.
- Safe artist-name extraction from chart databases
  (`get_artists_from_chart_db()`) with tolerant column-name detection
  (`"Artist Names"`, `"Artist"`, `"Artists"`, `"artist"`, `"Artista"`).
- Collaborator-aware parsing: raw artist strings are split via
  `split_artists()` before being added to the result set.
- Chart-database discovery (`get_latest_chart_database()`) by parsing the
  ISO week from the filename (`youtube_charts_YYYY-WW.db`) with a
  fallback to file modification time.

Dependencies
------------
- Internal: `..config` (ARTIST_DB_PATH, CHARTS_DB_DIR, logger),
  `.artist_parser` (split_artists).
- External: sqlite3, re, pathlib, typing (stdlib).

Requirements
------------
- Python 3.7+
- `ARTIST_DB_PATH` and `CHARTS_DB_DIR` must be configured in `config.py`.
- The chart databases must follow the naming convention
  `youtube_charts_YYYY-WW.db` (ISO week identifier).

Notes
-----
- **Error handling philosophy**: `create_database()` **raises** on error
  because a missing schema is a hard failure that must abort the pipeline.
  All other functions **log and return a safe default** (`(False, None,
  None)`, `0`, `None`, `set()`) so a single bad record or missing file
  does not crash the whole run.
- **Idempotency**: `create_database()` can be called repeatedly. On an
  existing table, it inspects `PRAGMA table_info(artist)` and adds the
  `macro_genre` column only if missing (schema migration for databases
  created before the genre feature was introduced).
- **Partial-update contract**: `insert_artist()` does not blindly
  overwrite. An existing non-placeholder `country` or `macro_genre` is
  preserved; only missing or `"Unknown"` values are filled. This is what
  makes re-runs safe: previously resolved metadata is never lost to a
  later failure.
- **Column-name tolerance**: chart databases are produced by the scraper
  and may carry the artist column under different names depending on the
  source (`"Artist Names"`, `"Artist"`, `"Artists"`, `"artist"`,
  `"Artista"`). `get_artists_from_chart_db()` probes all of them before
  giving up. Column names containing spaces are quoted to avoid SQL syntax
  errors.
- **SQL injection posture**: all user-supplied values are passed as
  parameters (`?` placeholders). The only f-string interpolations are for
  trusted identifiers (the `safe_column` derived from `PRAGMA table_info`,
  and the `set_clauses` composed of fixed strings). No raw artist, country,
  or genre string is ever interpolated into SQL.
- **Filename parsing**: `get_latest_chart_database()` extracts `(year,
  week)` from `youtube_charts_YYYY-WW.db` for deterministic sorting. If a
  file does not match the pattern, it falls back to `(0, mtime)` so it
  sorts **before** any properly named file — malformed names never shadow
  valid ones.
- **Connection lifecycle**: every function opens and closes its own
  connection. No connection is kept as a module-level singleton, which
  avoids cross-thread `sqlite3` issues and stale-lock errors. The small
  overhead of reconnecting per operation is acceptable given the
  pipeline's call volume.
- **Logger conventions**: success paths log at `info` with emoji prefixes
  (`✅`, `➕`, `🔄`, `📊`, `📁`) consistent with the scraper's output
  style; recoverable errors log at `debug` to avoid noise when a lookup
  simply misses; unrecoverable errors log at `error` with `❌`.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import re
import sqlite3
from pathlib import Path
from typing import Optional, Set, Tuple

from ..config import ARTIST_DB_PATH, CHARTS_DB_DIR, logger
from .artist_parser import split_artists

# ============================================================================
# CONSTANTS
# ============================================================================
_CHART_DB_GLOB = "youtube_charts_*.db"
_CHART_DB_FILENAME_PATTERN = re.compile(
    r"youtube_charts_(\d{4})-W(\d{1,2})\.db"
)

_ARTIST_TABLE_NAME = "artist"
_CHART_TABLE_NAME = "chart_data"

_ARTIST_COLUMN_CANDIDATES = [
    "Artist Names",
    "Artist",
    "Artists",
    "artist",
    "Artista",
]

_PLACEHOLDER_UNKNOWN = "Unknown"


# ============================================================================
# ARTIST DATABASE — SCHEMA
# ============================================================================
def create_database() -> None:
    """
    Create the artist database schema, or migrate an existing one.

    Creates the `artist` table with columns `name` (TEXT PRIMARY KEY),
    `country` (TEXT), and `macro_genre` (TEXT) if the table does not
    exist. If the table exists but is missing the `macro_genre` column
    (i.e., created by an older version of the pipeline), it is added via
    `ALTER TABLE`.

    Returns
    -------
    None

    Raises
    ------
    Exception
        Any SQLite error propagates after being logged at `error` level.
        Schema failures are hard failures: the pipeline cannot proceed
        without the artist table.

    Notes
    -----
    - Idempotent: safe to call on every pipeline run.
    - Uses `PRAGMA table_info(artist)` for migration detection rather than
      attempting `ALTER TABLE` unconditionally (which would fail on
      repeated runs).
    """
    try:
        conn = sqlite3.connect(str(ARTIST_DB_PATH))
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name=?",
            (_ARTIST_TABLE_NAME,),
        )
        exists = cursor.fetchone()

        if not exists:
            # --- Fresh schema ---
            cursor.execute(
                f"""
                CREATE TABLE {_ARTIST_TABLE_NAME} (
                    name TEXT PRIMARY KEY,
                    country TEXT,
                    macro_genre TEXT
                )
                """
            )
            conn.commit()
            logger.info(
                "✅ Table 'artist' created (name, country, macro_genre)"
            )
        else:
            # --- Migration check for the macro_genre column ---
            cursor.execute(f"PRAGMA table_info({_ARTIST_TABLE_NAME})")
            columns = [col[1] for col in cursor.fetchall()]

            if "macro_genre" not in columns:
                cursor.execute(
                    f"ALTER TABLE {_ARTIST_TABLE_NAME} "
                    "ADD COLUMN macro_genre TEXT"
                )
                conn.commit()
                logger.info(
                    "✅ Added 'macro_genre' column to existing table"
                )
            else:
                logger.info("✅ Table 'artist' exists with all columns")

        conn.close()

    except Exception as e:
        logger.error(f"❌ Database error: {e}")
        raise


# ============================================================================
# ARTIST DATABASE — LOOKUP
# ============================================================================
def artist_in_database(
    artist: str,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check whether an artist exists in the database and return stored data.

    Parameters
    ----------
    artist : str
        Artist name (exact match, case-sensitive as stored).

    Returns
    -------
    tuple of (bool, str or None, str or None)
        A tuple `(exists, country, macro_genre)` where:
        - `exists` is True if the artist row exists.
        - `country` is the stored country, or None.
        - `macro_genre` is the stored genre, or None.
        On any DB error, returns `(False, None, None)`.

    Notes
    -----
    - Lookup is by primary key (`name`), so it is O(log n) and exact.
    - Errors are logged at `debug` and swallowed: a failed lookup is
      treated as "not found" so the caller will attempt resolution and
      then call `insert_artist()`.
    """
    try:
        conn = sqlite3.connect(str(ARTIST_DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT country, macro_genre FROM {_ARTIST_TABLE_NAME} "
            "WHERE name = ?",
            (artist,),
        )
        res = cursor.fetchone()
        conn.close()

        if res:
            return True, res[0], res[1]
        return False, None, None

    except Exception as e:
        logger.debug(f"Database query error: {e}")
        return False, None, None


# ============================================================================
# ARTIST DATABASE — INSERT / UPDATE
# ============================================================================
def insert_artist(
    artist: str,
    country: str,
    genre: Optional[str] = None,
    source: str = "",
) -> None:
    """
    Insert a new artist or fill missing fields for an existing one.

    Performs a selective upsert: if the artist already exists, only the
    fields that are missing or hold the placeholder `"Unknown"` are
    updated. Previously resolved non-placeholder values are preserved.

    Parameters
    ----------
    artist : str
        Artist name (primary key).
    country : str
        Country name, or `"Unknown"` if unresolved.
    genre : str, optional
        Macro-genre name, or `"Unknown"`/None if unresolved.
    source : str, optional
        Human-readable description of the source that produced the data,
        used only for logging (e.g., `"MusicBrainz"`, `"Groq"`).

    Returns
    -------
    None

    Notes
    -----
    - **Partial-update semantics** (the core contract of this function):
      - `country` is written only if `country != "Unknown"` **and** the
        existing value is falsy or `"Unknown"`.
      - `macro_genre` is written only if `genre` is truthy **and**
        `!= "Unknown"` **and** the existing value is falsy or `"Unknown"`.
      - If neither field qualifies for update, the row is left untouched
        and no `COMMIT` occurs.
    - Successful inserts log with `➕`; successful updates log with `🔄`;
      non-placeholder inserts via the fallback path log with `✅`.
    - Errors are logged at `error` and swallowed: a single bad record does
      not abort the pipeline.
    """
    try:
        conn = sqlite3.connect(str(ARTIST_DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT country, macro_genre FROM {_ARTIST_TABLE_NAME} "
            "WHERE name = ?",
            (artist,),
        )
        existing = cursor.fetchone()

        if existing:
            # --- Existing row: selective update ---
            existing_country, existing_genre = existing

            update_country = (
                country != _PLACEHOLDER_UNKNOWN
                and (not existing_country or existing_country == _PLACEHOLDER_UNKNOWN)
            )
            update_genre = (
                genre
                and genre != _PLACEHOLDER_UNKNOWN
                and (
                    not existing_genre
                    or existing_genre == _PLACEHOLDER_UNKNOWN
                    or existing_genre is None
                )
            )

            if update_country or update_genre:
                set_clauses = []
                params = []

                if update_country:
                    set_clauses.append("country = ?")
                    params.append(country)
                if update_genre:
                    set_clauses.append("macro_genre = ?")
                    params.append(genre)

                params.append(artist)
                cursor.execute(
                    f"UPDATE {_ARTIST_TABLE_NAME} "
                    f"SET {', '.join(set_clauses)} "
                    "WHERE name = ?",
                    params,
                )
                conn.commit()

                if source:
                    logger.info(
                        f"  🔄 {artist} → "
                        f"Country: "
                        f"{country if update_country else existing_country} | "
                        f"Genre: "
                        f"{genre if update_genre else existing_genre} "
                        f"({source})"
                    )
        else:
            # --- New row: plain insert ---
            cursor.execute(
                f"INSERT INTO {_ARTIST_TABLE_NAME} "
                "(name, country, macro_genre) VALUES (?, ?, ?)",
                (artist, country, genre),
            )
            conn.commit()

            if source:
                logger.info(
                    f"  ➕ {artist} → Country: {country} | "
                    f"Genre: {genre or 'N/A'} ({source})"
                )
            else:
                logger.info(
                    f"  ✅ {artist} → Country: {country} | "
                    f"Genre: {genre or 'N/A'}"
                )

        conn.close()

    except Exception as e:
        logger.error(f"Error inserting {artist}: {e}")


# ============================================================================
# ARTIST DATABASE — STATS
# ============================================================================
def count_artists_in_database() -> int:
    """
    Return the total number of artists stored in the database.

    Returns
    -------
    int
        Row count of the `artist` table, or `0` on any DB error.

    Notes
    -----
    Errors are silently swallowed (returning `0`) because this function is
    used for logging and summary output, not for critical decisions.
    """
    try:
        conn = sqlite3.connect(str(ARTIST_DB_PATH))
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {_ARTIST_TABLE_NAME}")
        total = cursor.fetchone()[0]
        conn.close()
        return total
    except Exception:
        return 0


# ============================================================================
# CHART DATABASE — DISCOVERY
# ============================================================================
def get_latest_chart_database() -> Optional[Path]:
    """
    Find the most recent YouTube chart database in the charts directory.

    Databases are expected to follow the naming pattern
    `youtube_charts_YYYY-WW.db`, where `YYYY` is the ISO year and `WW` the
    ISO week number.

    Returns
    -------
    Path or None
        Path to the latest database (by parsed year/week), or None if the
        directory is missing, empty, or an error occurs.

    Notes
    -----
    - Sorting key is `(year, week)` parsed from the filename. Files whose
      name does not match the expected pattern fall back to `(0, mtime)`,
      which sorts **before** any valid file — malformed names never
      shadow valid ones.
    - The directory is checked via `CHARTS_DB_DIR.exists()` before globbing
      to produce a clear error message when the pipeline has not run yet.
    """
    if not CHARTS_DB_DIR.exists():
        logger.error(f"❌ Directory not found: {CHARTS_DB_DIR}")
        return None

    db_files = list(CHARTS_DB_DIR.glob(_CHART_DB_GLOB))
    if not db_files:
        logger.error("❌ No chart databases found")
        return None

    def week_key(file_path: Path) -> tuple:
        """
        Build a sort key `(year, week)` from the chart database filename.

        Parameters
        ----------
        file_path : Path
            Path to a chart database file.

        Returns
        -------
        tuple
            `(year, week)` when the filename matches the expected pattern;
            `(0, mtime)` otherwise, so malformed names sort before valid
            ones.
        """
        match = _CHART_DB_FILENAME_PATTERN.search(file_path.name)
        if match:
            year = int(match.group(1))
            week = int(match.group(2))
            return (year, week)
        return (0, file_path.stat().st_mtime)

    latest = max(db_files, key=week_key)
    logger.info(f"📁 Using database: {latest.name}")
    return latest


# ============================================================================
# CHART DATABASE — ARTIST EXTRACTION
# ============================================================================
def get_artists_from_chart_db(db_path: Path) -> Set[str]:
    """
    Extract all unique artist names from a YouTube chart database.

    Reads the `chart_data` table, detects the artist column, and splits
    collaborator strings (via `split_artists`) before deduplicating.

    Parameters
    ----------
    db_path : Path
        Path to the chart SQLite database (typically obtained from
        `get_latest_chart_database()`).

    Returns
    -------
    set of str
        Unique artist names found in the chart. Empty set on any error or
        when no artist column can be identified.

    Notes
    -----
    - The artist column may appear under different names depending on the
      scraper version: `"Artist Names"`, `"Artist"`, `"Artists"`,
      `"artist"`, `"Artista"`. The first match in that priority order is
      used.
    - Column names containing spaces are quoted (`"Artist Names"`) to
      avoid SQL syntax errors.
    - Each row's value is passed through `split_artists()` so
      collaborations (`"A feat. B"`) contribute both artists to the set.
    - On error, the connection is closed if it was opened, and an empty
      set is returned to keep the pipeline resilient.
    """
    if not db_path.exists():
        logger.error(f"❌ File not found: {db_path}")
        return set()

    artists: Set[str] = set()

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute(f"PRAGMA table_info({_CHART_TABLE_NAME})")
        columns = [col[1] for col in cursor.fetchall()]

        # --- Detect artist column among known candidates ---
        artist_column = None
        for col in _ARTIST_COLUMN_CANDIDATES:
            if col in columns:
                artist_column = col
                break

        if not artist_column:
            logger.error("❌ No artist column found in chart_data")
            conn.close()
            return set()

        # --- Quote column name if it contains spaces ---
        safe_column = (
            f'"{artist_column}"' if " " in artist_column else artist_column
        )

        cursor.execute(
            f"SELECT {safe_column} FROM {_CHART_TABLE_NAME} "
            f"WHERE {safe_column} IS NOT NULL"
        )
        rows = cursor.fetchall()

        for row in rows:
            if row[0]:
                artists.update(split_artists(str(row[0])))

        conn.close()
        logger.info(
            f"📊 {len(artists)} unique artists in the chart database"
        )
        return artists

    except Exception as e:
        logger.error(f"❌ Error reading database: {e}")
        if "conn" in locals():
            conn.close()
        return set()
