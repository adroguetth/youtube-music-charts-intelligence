"""
Migrate - ETL Pipeline for Song Catalog
============================================================================
Core ETL pipeline for the song catalog builder. Orchestrates the full
enrichment workflow:

1. Locate the most recent YouTube chart database.
2. Load the artist metadata dictionary (from Script 2.1).
3. Establish read-only (source) and read-write (target) connections.
4. Initialize/migrate the target schema.
5. Repair existing records with missing/invalid country or genre.
6. Extract new (artist, track) pairs from the current chart.
7. Resolve country/genre for each new track and INSERT it.
8. Verify integrity and report statistics.

The pipeline is idempotent: re-running it will not duplicate records, and
it will only repair records that actually need repair.

Features
--------
- Read-only source connection prevents accidental modification of chart data.
- Atomic transactions with explicit `connection.commit()` after each phase.
- Two-phase resolution: historical repair (Phase 5) + new insert (Phase 7).
- Progress reporting every 25% of the batch.
- Graceful degradation: if a single record fails, the pipeline logs it and
  continues, instead of aborting the whole run.

Dependencies
------------
- Internal: `.config` (paths, logger), `.utils.db_utils`
  (initialize_target_schema, get_catalog_statistics, load_artist_lookup),
  `.utils.artist_parser` (parse_artist_list), `.resolver`
  (resolve_country_and_genre, get_artist_info).
- External: sqlite3, datetime, pathlib, typing (stdlib).

Requirements
------------
- Python 3.7+
- Source database at `charts_archive/1_download-chart/databases/`.
- Artist database at `charts_archive/2_1.countries-genres-artist/`.

Notes
-----
- Phase 5 (repair) and Phase 7 (insert) are separated by design. This
  ensures that historical records are fixed even if the current chart has
  no new data, and vice versa.
- The `artists_found` column is populated with a `"matched/total"` string
  (e.g., `"2/3"`) to make collaboration resolution transparent.
- Errors during INSERT or UPDATE are logged but do not abort the pipeline.
  At the end, the total error count is reported.
- The pipeline uses `sqlite3.Row` as the row factory for the source
  connection, enabling column access by name.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .config import (
    SOURCE_DIR,
    TARGET_DB_NAME,
    TARGET_DIR,
    logger,
)
from .resolver import get_artist_info, resolve_country_and_genre
from .utils.artist_parser import parse_artist_list
from .utils.db_utils import (
    get_catalog_statistics,
    initialize_target_schema,
    load_artist_lookup,
)


# ============================================================================
# SOURCE DATABASE HELPERS
# ============================================================================
def _get_week_identifier_from_filename(filename: str) -> Optional[str]:
    """
    Extract the ISO week identifier from a database filename.

    Expected format: `youtube_charts_YYYY-Www.db`.

    Parameters
    ----------
    filename : str
        Database filename (e.g., `'youtube_charts_2026-W15.db'`).

    Returns
    -------
    str or None
        Week identifier in `YYYY-Www` format, or None if the filename does
        not match the expected pattern.
    """
    import re

    match = re.search(r"youtube_charts_(\d{4}-W\d{1,2})\.db", filename)
    return match.group(1) if match else None


def _get_most_recent_database(directory: Path) -> Optional[Path]:
    """
    Identify the most recent YouTube Charts database file in a directory.

    Selection algorithm:
    1. Filter files matching the pattern `youtube_charts_20YY-Www.db`.
    2. Extract ISO week identifiers.
    3. Sort by year (descending), then by week number (descending).
    4. Return the most recent valid database.

    This approach correctly handles year boundaries (e.g., `2025-W52` vs
    `2026-W01`). Lexicographic sorting works because ISO format
    `YYYY-Www` is naturally ordered.

    Parameters
    ----------
    directory : Path
        Directory containing weekly databases.

    Returns
    -------
    Path or None
        Absolute path to the most recent database file, or None if no
        matching file was found.
    """
    matching_files: List[Tuple[str, Path]] = []

    for file_path in directory.glob("youtube_charts_*.db"):
        week_id = _get_week_identifier_from_filename(file_path.name)
        if week_id:
            matching_files.append((week_id, file_path))

    if not matching_files:
        return None

    matching_files.sort(key=lambda x: x[0], reverse=True)
    return matching_files[0][1]


# ============================================================================
# MAIN ETL PIPELINE
# ============================================================================
def migrate_data() -> int:
    """
    Execute the ETL pipeline to update the song catalog.

    Process flow:
    1. Validate source directory and locate most recent database.
    2. Load artist metadata for country/genre resolution.
    3. Establish read-only connection to source database.
    4. Establish read-write connection to target catalog.
    5. Initialize/migrate target schema.
    6. Extract distinct artist-track pairs from source.
    7. For each pair:
       a. If record does not exist, resolve country/genre and INSERT.
       b. If record exists but has NULL/Unknown country or genre, resolve
          and UPDATE.
       c. Otherwise, skip (already has valid data).
    8. Commit transaction and report statistics.
    9. Handle errors gracefully with appropriate exit codes.

    Returns
    -------
    int
        Exit code (0 = success, 1 = failure).
    """
    print("\n" + "=" * 70)
    print("🎵 YOUTUBE CHARTS - SONG CATALOG BUILDER")
    print("   IDEMPOTENT ETL PIPELINE FOR ARTIST-TRACK CATALOG")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # Phase 1: Source database selection
    # -------------------------------------------------------------------------
    logger.info("\n1. 🔍 LOCATING MOST RECENT SOURCE DATABASE...")

    if not SOURCE_DIR.exists():
        logger.error(f"   ❌ Source directory does not exist: {SOURCE_DIR}")
        logger.error("   ℹ️  Please run Script 1 first to populate chart databases.")
        return 1

    source_path = _get_most_recent_database(SOURCE_DIR)

    if not source_path:
        logger.error("   ❌ No database files found matching pattern youtube_charts_20XX-WXX.db")
        logger.error(f"   📁 Directory: {SOURCE_DIR}")
        return 1

    source_week_id = _get_week_identifier_from_filename(source_path.name)
    source_size_kb = source_path.stat().st_size / 1024

    logger.info(f"   ✅ Source identified: {source_path.name}")
    logger.info(f"   📆 Week identifier: {source_week_id}")
    logger.info(f"   📊 File size: {source_size_kb:.1f} KB")

    # -------------------------------------------------------------------------
    # Phase 2: Load artist metadata
    # -------------------------------------------------------------------------
    logger.info("\n2. 🌍 LOADING ARTIST METADATA DATABASE...")
    artist_lookup = load_artist_lookup()

    # -------------------------------------------------------------------------
    # Phase 3: Database connections
    # -------------------------------------------------------------------------
    logger.info("\n3. 🔗 ESTABLISHING DATABASE CONNECTIONS...")

    target_path = TARGET_DIR / TARGET_DB_NAME
    target_exists = target_path.exists()

    # Source connection: read-only mode
    source_uri = f"file:{source_path}?mode=ro"

    try:
        source_conn = sqlite3.connect(source_uri, uri=True)
        source_conn.row_factory = sqlite3.Row
        source_cursor = source_conn.cursor()

        # Verify source has the expected table
        source_cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chart_data'"
        )
        if not source_cursor.fetchone():
            logger.error("   ❌ Source database missing 'chart_data' table.")
            source_conn.close()
            return 1

        logger.info("   ✅ Source connection established (read-only mode).")

        target_conn = sqlite3.connect(target_path)
        target_cursor = target_conn.cursor()

        if target_exists:
            target_size_kb = target_path.stat().st_size / 1024
            logger.info(
                f"   ✅ Target connection established "
                f"(existing: {target_size_kb:.1f} KB)."
            )
        else:
            logger.info("   ✅ Target connection established (new database).")

    except sqlite3.Error as e:
        logger.error(f"   ❌ Database connection error: {e}")
        return 1

    # -------------------------------------------------------------------------
    # Phase 4: Schema initialization / migration
    # -------------------------------------------------------------------------
    logger.info("\n4. 📋 INITIALIZING TARGET SCHEMA...")

    try:
        initialize_target_schema(target_conn)
        initial_count, initial_max_id = get_catalog_statistics(target_conn)
        logger.info(f"   📊 Current catalog size: {initial_count:,} records")
    except sqlite3.Error as e:
        logger.error(f"   ❌ Schema initialization failed: {e}")
        source_conn.close()
        target_conn.close()
        return 1

    # -------------------------------------------------------------------------
    # Phase 5: Repair historical incomplete records
    # -------------------------------------------------------------------------
    logger.info("\n5. 🔧 REPAIRING HISTORICAL INCOMPLETE RECORDS...")

    incomplete_query = """
        SELECT artist_names, track_name
        FROM artist_track
        WHERE artist_country IS NULL
           OR artist_country = ''
           OR artist_country = 'Unknown'
           OR macro_genre IS NULL
           OR macro_genre = ''
           OR macro_genre = 'Unknown'
    """
    target_cursor.execute(incomplete_query)
    incomplete_rows = target_cursor.fetchall()
    total_incomplete = len(incomplete_rows)
    logger.info(f"   📋 Found {total_incomplete:,} records with incomplete data.")

    update_stmt = """
        UPDATE artist_track
        SET artist_country = ?, macro_genre = ?, artists_found = ?
        WHERE artist_names = ? AND track_name = ?
    """
    repaired_count = 0
    error_repair_count = 0

    if total_incomplete > 0:
        progress_interval = max(1, total_incomplete // 4)
        for idx, (artist_names, track_name) in enumerate(incomplete_rows, 1):
            try:
                artists_info = get_artist_info(artist_names, artist_lookup)
                final_country, final_genre = resolve_country_and_genre(artists_info)
                matched = sum(1 for a in artists_info if a["country"] is not None)
                total_arts = len(artists_info) if artists_info else 1
                artists_found_str = f"{matched}/{total_arts}"

                target_cursor.execute(
                    update_stmt,
                    (
                        final_country,
                        final_genre,
                        artists_found_str,
                        artist_names,
                        track_name,
                    ),
                )
                repaired_count += 1
            except sqlite3.Error as e:
                error_repair_count += 1
                if error_repair_count <= 5:
                    logger.warning(
                        f"   ⚠️  Error repairing: {artist_names[:30]}... - "
                        f"{track_name[:30]}... : {e}"
                    )

            if idx % progress_interval == 0 or idx == total_incomplete:
                pct = (idx / total_incomplete) * 100
                logger.info(
                    f"   📈 Repair progress: {idx:,}/{total_incomplete:,} "
                    f"({pct:.1f}%) - Repaired: {repaired_count:,}"
                )

        target_conn.commit()
        logger.info("\n   ✅ Phase 5 completed:")
        logger.info(f"      🔧 Records repaired: {repaired_count:,}")
        if error_repair_count > 0:
            logger.warning(f"      ⚠️  Repair errors: {error_repair_count}")
    else:
        logger.info("   ✅ No incomplete records found. Skipping repair phase.")

    # -------------------------------------------------------------------------
    # Phase 6: Extract artist-track pairs from current chart
    # -------------------------------------------------------------------------
    logger.info("\n6. 📤 EXTRACTING ARTIST-TRACK PAIRS FROM CURRENT CHART...")

    extract_query = """
        SELECT DISTINCT
            "Artist Names" AS artist_names,
            "Track Name"   AS track_name
        FROM chart_data
        WHERE "Artist Names" IS NOT NULL
          AND "Track Name" IS NOT NULL
          AND TRIM("Artist Names") != ''
          AND TRIM("Track Name") != ''
        ORDER BY "Artist Names", "Track Name"
    """

    try:
        source_cursor.execute(extract_query)
        all_rows = source_cursor.fetchall()
        total_extracted = len(all_rows)
        logger.info(
            f"   ✅ Extracted {total_extracted:,} distinct artist-track pairs "
            f"from chart."
        )
        if total_extracted == 0:
            logger.warning("   ⚠️  No valid records found in source database.")
            source_conn.close()
            target_conn.close()
            return 0
    except sqlite3.Error as e:
        logger.error(f"   ❌ Data extraction error: {e}")
        source_conn.close()
        target_conn.close()
        return 1

    # -------------------------------------------------------------------------
    # Phase 7: Idempotent insertion (new songs only)
    # -------------------------------------------------------------------------
    logger.info("\n7. 💾 PROCESSING CURRENT CHART (INSERT NEW SONGS ONLY)...")

    insert_statement = """
        INSERT INTO artist_track (
            artist_names, track_name, artist_country, macro_genre, artists_found
        ) VALUES (?, ?, ?, ?, ?)
    """
    check_exist_query = """
        SELECT 1 FROM artist_track
        WHERE artist_names = ? AND track_name = ?
        LIMIT 1
    """

    inserted_count = 0
    skipped_count = 0
    error_insert_count = 0
    progress_interval = max(1, total_extracted // 4)

    for idx, row in enumerate(all_rows, 1):
        artist_names = row["artist_names"]
        track_name = row["track_name"]

        try:
            target_cursor.execute(check_exist_query, (artist_names, track_name))
            exists = target_cursor.fetchone() is not None

            if not exists:
                artists_info = get_artist_info(artist_names, artist_lookup)
                final_country, final_genre = resolve_country_and_genre(artists_info)
                matched = sum(1 for a in artists_info if a["country"] is not None)
                total_arts = len(artists_info) if artists_info else 1
                artists_found_str = f"{matched}/{total_arts}"

                target_cursor.execute(
                    insert_statement,
                    (
                        artist_names,
                        track_name,
                        final_country,
                        final_genre,
                        artists_found_str,
                    ),
                )
                inserted_count += 1
            else:
                skipped_count += 1
        except sqlite3.Error as e:
            error_insert_count += 1
            if error_insert_count <= 5:
                logger.warning(
                    f"   ⚠️  Error inserting: {artist_names[:30]}... - "
                    f"{track_name[:30]}... : {e}"
                )

        if idx % progress_interval == 0 or idx == total_extracted:
            pct = (idx / total_extracted) * 100
            logger.info(
                f"   📈 Chart progress: {idx:,}/{total_extracted:,} ({pct:.1f}%) "
                f"- Inserted: {inserted_count:,}, Skipped: {skipped_count:,}"
            )

    target_conn.commit()
    logger.info("\n   ✅ Phase 7 completed:")
    logger.info(f"      🆕 New songs inserted: {inserted_count:,}")
    logger.info(f"      ⏭️  Already in catalog: {skipped_count:,}")
    if error_insert_count > 0:
        logger.warning(f"      ⚠️  Insert errors: {error_insert_count}")

    # -------------------------------------------------------------------------
    # Phase 8: Verification and statistics
    # -------------------------------------------------------------------------
    logger.info("\n8. 📊 VERIFICATION AND STATISTICS...")

    final_count, final_max_id = get_catalog_statistics(target_conn)
    expected_final = initial_count + inserted_count

    if final_count == expected_final:
        logger.info(f"   ✅ Integrity check passed: {final_count:,} total records")
    else:
        logger.warning(
            f"   ⚠️  Count mismatch: Expected {expected_final:,}, "
            f"Found {final_count:,}"
        )

    if initial_count > 0:
        growth_pct = ((final_count - initial_count) / initial_count) * 100
        logger.info(f"   📈 Catalog growth: +{growth_pct:.2f}%")

    logger.info(f"   🔑 Latest ID: {final_max_id}")
    logger.info(f"   💾 Database location: {target_path}")
    logger.info(f"   📀 Database size: {target_path.stat().st_size / 1024:.1f} KB")

    logger.info("\n   📋 Sample of recent catalog entries:")
    target_cursor.execute(
        """
        SELECT id, artist_names, track_name, artist_country, macro_genre, artists_found
        FROM artist_track
        ORDER BY id DESC
        LIMIT 5
        """
    )
    for entry in target_cursor.fetchall():
        entry_id, artist, track, country, genre, found = entry
        artist_display = artist[:30] + "..." if len(artist) > 30 else artist
        track_display = track[:30] + "..." if len(track) > 30 else track
        logger.info(f"      [{entry_id:4d}] {artist_display} — {track_display}")
        logger.info(f"            🌍 {country} | 🎵 {genre} | 👥 {found}")

    # -------------------------------------------------------------------------
    # Phase 9: Cleanup
    # -------------------------------------------------------------------------
    source_conn.close()
    target_conn.close()

    print("\n" + "=" * 70)
    print(
        f"✅ CATALOG UPDATE COMPLETE: "
        f"Repaired {repaired_count:,} records, "
        f"Inserted {inserted_count:,} new songs"
    )
    print("=" * 70)

    return 0
