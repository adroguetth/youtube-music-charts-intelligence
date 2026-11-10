"""
Database Utilities - Locate, Load and Validate Enriched Weekly Charts
============================================================================
Utilities to locate and load the enriched weekly chart databases stored
under `charts_archive/3_enrich-chart-data/`.

Responsibilities
----------------
- Select the most recent enriched DB available in the archive directory.
- Load a weekly DB into a DataFrame with derived columns
  (`upload_date`, `upload_quarter`, `engagement`, `week_slug`).
- Validate the expected schema before returning the DataFrame.

Notes
-----
- This module does not download anything. It operates on the local
  working copy of the repository. In CI, the workflow already clones
  the repo; in local usage, the user already has the repo cloned.
- Ordering of week labels is done by parsing each filename into a
  ``(year, week)`` tuple and comparing those integers. String sorting is
  deliberately avoided: ``"2026-W52"`` must not win over ``"2027-W01"``,
  and ``"2025-W9"`` must not win over ``"2025-W10"``.
- This module does not perform any aggregation. All metrics live in
  `core.metrics`.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

# ============================================================================
# CONSTANTS
# ============================================================================
EXPECTED_TABLE: str = "enriched_songs"

_DB_FILENAME_PATTERN = re.compile(
    r"^youtube_charts_(\d{4})-W(\d{1,2})_enriched\.db$"
)

REQUIRED_COLUMNS: frozenset[str] = frozenset({
    "rank", "id", "artist_names", "track_name", "views", "likes",
    "comment_count", "duration_s", "upload_date", "is_official_video",
    "is_lyric_video", "is_live_performance", "channel_type",
    "is_collaboration", "artist_count", "artist_country", "macro_genre",
})

# ============================================================================
# WEEK LABEL HELPERS
# ============================================================================
def parse_db_filename(filename: str) -> tuple[int, int] | None:
    """Parse an enriched DB filename into ``(year, week)``, or None."""
    match = _DB_FILENAME_PATTERN.match(filename)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def latest_week_label(archive_dir: Path) -> str:
    """
    Return the label of the most recent enriched weekly DB in `archive_dir`.

    Ordering is done by parsing each filename into ``(year, week)`` and
    comparing those integers. This avoids the lexicographic pitfalls of
    sorting week labels as plain strings, where ``"2025-W9"`` sorts after
    ``"2025-W10"`` and ``"2026-W52"`` would win over ``"2027-W01"`` if the
    year comparison were done character-by-character on unprepared data.

    Parameters
    ----------
    archive_dir : Path
        Directory containing ``youtube_charts_YYYY-WXX_enriched.db`` files.

    Returns
    -------
    str
        Label of the most recent week, normalised to ``YYYY-WXX``
        (zero-padded week number), e.g. ``"2027-W01"``.

    Raises
    ------
    FileNotFoundError
        If no enriched DB is found in `archive_dir`.
    """
    candidates: list[tuple[int, int]] = []
    for path in archive_dir.glob("youtube_charts_*_enriched.db"):
        parsed = parse_db_filename(path.name)
        if parsed is not None:
            candidates.append(parsed)

    if not candidates:
        raise FileNotFoundError(
            f"No enriched DB files found in {archive_dir}. "
            f"Expected pattern: youtube_charts_YYYY-WXX_enriched.db"
        )

    year, week = max(candidates)
    return f"{year}-W{week:02d}"


# ============================================================================
# FILE LOOKUP
# ============================================================================
def find_week_db(label: str, archive_dir: Path) -> Path:
    """Return the path to the enriched DB for a given week label."""
    path = archive_dir / f"youtube_charts_{label}_enriched.db"
    if not path.exists():
        raise FileNotFoundError(
            f"Enriched DB not found for week {label}: {path}"
        )
    return path


# ============================================================================
# LOADING
# ============================================================================
def load_week(label: str, archive_dir: Path) -> pd.DataFrame:
    """
    Load the enriched chart DB for a given ISO week.

    Parameters
    ----------
    label : str
        ISO week label, e.g. ``"2026-W46"``.
    archive_dir : Path
        Directory containing the enriched `.db` files.

    Returns
    -------
    pd.DataFrame
        Enriched songs with derived columns:
        - ``upload_date`` as datetime
        - ``upload_quarter`` as int
        - ``engagement`` as float (``likes / views * 100``; 0 if views == 0)
        - ``week_slug`` as str (equal to `label`)
    """
    db_path = find_week_db(label, archive_dir)
    conn = sqlite3.connect(db_path)
    try:
        tables = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table';", conn
        )["name"].tolist()
        table = EXPECTED_TABLE if EXPECTED_TABLE in tables else tables[0]
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    finally:
        conn.close()

    validate_schema(df)

    df["upload_date"] = pd.to_datetime(df["upload_date"], errors="coerce")
    df["upload_quarter"] = df["upload_date"].dt.quarter
    df["engagement"] = np.where(
        df["views"] > 0,
        (df["likes"] / df["views"] * 100).round(2),
        0.0,
    )
    df["week_slug"] = label
    return df


def validate_schema(df: pd.DataFrame) -> None:
    """Raise if required columns are missing from the loaded DataFrame."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Enriched DB is missing required columns: {sorted(missing)}"
        )
