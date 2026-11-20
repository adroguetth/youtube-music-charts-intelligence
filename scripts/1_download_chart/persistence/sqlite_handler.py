"""
SQLite Persistence
============================================================================
One database per ISO week, with idempotent per-week writes.

The schema is explicit because the extractor's column set has changed over
time. Rows for the target week are deleted and re-inserted inside a single
transaction, so a failed run never leaves a half-written week behind.

Features
--------
- Explicit schema with a soft migration for the ``is_synthetic`` column.
- Single-transaction delete-and-insert per week.
- Indexes for date, week, rank and artist queries.
- Inventory helper used by the final summary.

Dependencies
------------
- Internal: config, persistence.backup, persistence.csv_handler.
- External: sqlite3, logging, datetime, pathlib (stdlib).
- Downstream: __main__.

Requirements
------------
- Python 3.10+

Notes
-----
- ``count_real_rows`` ignores synthetic rows, which is what the idempotency
  guard needs to decide whether a week is already complete.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import CANONICAL_COLUMNS, DATABASE_DIR, ensure_directories
from .backup import create_backup_before_update
from .csv_handler import read_csv_normalized

log = logging.getLogger("youtube_charts")


# ============================================================================
# SCHEMA
# ============================================================================
METADATA_COLUMNS = ["download_date", "download_time", "week_id", "timestamp", "is_synthetic"]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chart_data (
    "Rank" INTEGER,
    "Previous Rank" INTEGER,
    "Track Name" TEXT,
    "Artist Names" TEXT,
    "Periods on Chart" INTEGER,
    "Views" INTEGER,
    "Views Raw" TEXT,
    "Growth" TEXT,
    "YouTube URL" TEXT,
    download_date TEXT,
    download_time TEXT,
    week_id TEXT,
    timestamp TEXT,
    is_synthetic INTEGER DEFAULT 0
)
"""

INDEXES = (
    ("idx_date", "chart_data(download_date)"),
    ("idx_week", "chart_data(week_id)"),
    ("idx_rank", 'chart_data("Rank")'),
    ("idx_artist", 'chart_data("Artist Names")'),
)


# ============================================================================
# WRITES
# ============================================================================
def update_sqlite_database(
    csv_path: Path, week_id: str, is_synthetic: bool = False
) -> Optional[Path]:
    """Replace the target week's rows with the contents of ``csv_path``.

    Parameters
    ----------
    csv_path : Path
        CSV produced by the extractor or by the official download button.
    week_id : str
        ISO week identifier, e.g. ``2026-W47``.
    is_synthetic : bool, optional
        Mark every row as synthetic, by default ``False``.

    Returns
    -------
    Path or None
        Path to the updated database, or ``None`` on failure.

    Notes
    -----
    A backup of the previous database is taken before the delete-and-insert
    transaction. The transaction is atomic: a crash cannot leave a half-written
    week behind.
    """
    log.info("Loading chart data from %s", csv_path)
    chart = read_csv_normalized(Path(csv_path))
    if not chart.entries:
        log.error("CSV is empty or has no valid rows: %s", csv_path)
        return None
    if not chart.has_synthetic_flag:
        for entry in chart.entries:
            entry.is_synthetic = 1 if is_synthetic else 0

    log.info("Songs loaded: %d", len(chart.entries))
    for index, entry in enumerate(chart.entries[:5], start=1):
        log.info("  %d. %s - %s", index, entry.track_name[:40], entry.artist_names[:40])

    db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
    ensure_directories()
    if db_path.exists():
        log.info("Creating backup before update")
        create_backup_before_update(week_id)

    now = datetime.now()
    metadata = [
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M:%S"),
        week_id,
        now.strftime("%Y%m%d_%H%M%S"),
    ]
    all_columns = CANONICAL_COLUMNS + METADATA_COLUMNS

    try:
        connection = sqlite3.connect(db_path)
        try:
            cursor = connection.cursor()
            cursor.execute(SCHEMA_SQL)

            # Soft migration for databases created before the flag existed.
            cursor.execute("PRAGMA table_info(chart_data)")
            existing = {row[1] for row in cursor.fetchall()}
            if "is_synthetic" not in existing:
                try:
                    cursor.execute(
                        "ALTER TABLE chart_data ADD COLUMN is_synthetic INTEGER DEFAULT 0"
                    )
                except sqlite3.OperationalError:
                    pass

            cursor.execute("DELETE FROM chart_data WHERE week_id = ?", (week_id,))
            deleted = cursor.rowcount
            if deleted:
                log.info("Deleted %d stale rows for %s", deleted, week_id)

            placeholders = ", ".join(["?"] * len(all_columns))
            quoted = ", ".join(f'"{column}"' for column in all_columns)
            statement = (
                f"INSERT INTO chart_data ({quoted}) VALUES ({placeholders})"
            )
            payload = [
                tuple(
                    entry.to_db_values()
                    + metadata
                    + [int(entry.is_synthetic)]
                )
                for entry in chart.entries
            ]
            cursor.executemany(statement, payload)

            for name, target in INDEXES:
                try:
                    cursor.execute(
                        f"CREATE INDEX IF NOT EXISTS {name} ON {target}"
                    )
                except sqlite3.OperationalError as exc:
                    log.warning("Could not create index %s: %s", name, exc)

            connection.commit()

            cursor.execute("SELECT COUNT(*) FROM chart_data")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT download_date) FROM chart_data")
            distinct_dates = cursor.fetchone()[0]
            log.info(
                "Database updated: total=%d distinct_dates=%d path=%s",
                total,
                distinct_dates,
                db_path,
            )
            return db_path
        finally:
            connection.close()
    except Exception as exc:
        log.error("SQLite update failed: %s", exc, exc_info=True)
        return None


# ============================================================================
# QUERIES AND INVENTORY
# ============================================================================
def count_real_rows(db_path: Path, week_id: str) -> int:
    """Count non-synthetic rows for a week; used by the idempotency guard."""
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM chart_data WHERE week_id = ? AND is_synthetic = 0",
            (week_id,),
        )
        return int(cursor.fetchone()[0])
    finally:
        connection.close()


def list_available_databases() -> List[Dict[str, Any]]:
    """Log per-database statistics and return them as structured data."""
    databases = sorted(DATABASE_DIR.glob("youtube_charts_*.db"))
    if not databases:
        log.info("No databases available yet")
        return []

    log.info("Available databases (%d):", len(databases))
    total = 0
    inventory: List[Dict[str, Any]] = []

    for db_path in databases:
        try:
            connection = sqlite3.connect(db_path)
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT COUNT(*) FROM chart_data")
                count = cursor.fetchone()[0]
                try:
                    cursor.execute(
                        "SELECT COUNT(*) FROM chart_data WHERE is_synthetic = 1"
                    )
                    synthetic = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    synthetic = 0
                cursor.execute(
                    "SELECT MIN(download_date), MAX(download_date) FROM chart_data"
                )
                first_date, last_date = cursor.fetchone()
            finally:
                connection.close()

            week_id = db_path.stem.replace("youtube_charts_", "")
            size_kb = db_path.stat().st_size / 1024
            total += count
            log.info(
                "  %s: %d rows (%d synthetic), %.1f KB, %s to %s",
                week_id,
                count,
                synthetic,
                size_kb,
                first_date,
                last_date,
            )
            inventory.append(
                {
                    "week_id": week_id,
                    "count": count,
                    "synthetic": synthetic,
                    "size_kb": size_kb,
                }
            )
        except Exception as exc:
            log.warning("Could not read %s: %s", db_path.name, exc)

    log.info("TOTAL: %d rows across %d databases", total, len(databases))
    return inventory
