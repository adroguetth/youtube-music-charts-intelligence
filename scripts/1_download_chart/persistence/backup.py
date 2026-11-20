"""
Backup and Retention
============================================================================
Backup creation before every database rewrite, plus time-based retention for
backup files and weekly databases.

Features
--------
- Microsecond-precision backup names: two runs in the same second cannot
  overwrite each other's backup.
- Backup retention measured in days.
- Database retention measured in ISO weeks.
- Corrupt or unrelated files are skipped, never deleted blindly.

Dependencies
------------
- Internal: config.
- External: logging, shutil, datetime, pathlib (stdlib).
- Downstream: persistence.sqlite_handler, __main__.

Requirements
------------
- Python 3.10+

Notes
-----
- Weeks are decoded with ``date.fromisocalendar``; ``strptime('%W')`` is not
  ISO-8601 and shifts week numbers around the new year.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..config import BACKUP_DIR, DATABASE_DIR, ensure_directories

log = logging.getLogger("youtube_charts")


# ============================================================================
# CONSTANTS
# ============================================================================
DB_PREFIX = "youtube_charts_"
BACKUP_GLOB = "backup_*.db"


# ============================================================================
# BACKUP CREATION
# ============================================================================
def create_backup_before_update(week_id: str) -> Optional[Path]:
    """Copy the week's database aside before it is rewritten.

    The timestamp carries microseconds so two runs in the same second cannot
    overwrite each other's backup.
    """
    db_path = DATABASE_DIR / f"{DB_PREFIX}{week_id}.db"
    if not db_path.exists():
        return None

    ensure_directories()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = BACKUP_DIR / f"backup_{week_id}_{timestamp}.db"
    try:
        shutil.copy2(db_path, backup_path)
        log.info("Backup created: %s", backup_path.name)
        return backup_path
    except Exception as exc:
        log.warning("Backup failed: %s", exc)
        return None


# ============================================================================
# RETENTION
# ============================================================================
def cleanup_old_backups(days: int = 7) -> None:
    """Delete backups older than ``days`` based on file mtime."""
    log.info("Removing backups older than %d days", days)
    if not BACKUP_DIR.exists():
        return

    cutoff = datetime.now() - timedelta(days=days)
    deleted = 0
    for backup in BACKUP_DIR.glob(BACKUP_GLOB):
        try:
            if backup.stat().st_mtime < cutoff.timestamp():
                backup.unlink()
                deleted += 1
        except Exception as exc:
            log.warning("Could not delete %s: %s", backup.name, exc)
    log.info("Backups removed: %d", deleted)


def cleanup_old_databases(weeks: int = 52) -> None:
    """Delete weekly databases outside the retention window.

    The week is decoded with ``date.fromisocalendar``; ``strptime('%W')`` is not
    ISO-8601 and shifts week numbers around the new year.
    """
    log.info("Removing databases older than %d weeks", weeks)
    if not DATABASE_DIR.exists():
        return

    cutoff = datetime.now() - timedelta(weeks=weeks)
    deleted = 0
    for db_path in DATABASE_DIR.glob(f"{DB_PREFIX}*.db"):
        try:
            week_id = db_path.stem.replace(DB_PREFIX, "")
            year_text, week_text = week_id.split("-W")
            db_date = datetime.fromisocalendar(int(year_text), int(week_text), 1)
            if db_date < cutoff:
                db_path.unlink()
                deleted += 1
                log.info("Deleted: %s", db_path.name)
        except Exception as exc:
            log.warning("Could not process %s: %s", db_path.name, exc)
    log.info("Databases removed: %d", deleted)
