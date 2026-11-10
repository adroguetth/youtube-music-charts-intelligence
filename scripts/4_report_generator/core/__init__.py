"""
Core - Periods, Database Access and Metrics
============================================================================
Pure logic layer for the `4_report_generator` package.

Responsibilities
----------------
- Represent the reporting period (`periods`).
- Locate, load and validate enriched weekly DBs (`db`).
- Compute the aggregations displayed in the report (`metrics`).

Notes
-----
- This subpackage contains no I/O beyond reading the SQLite DB.
- No module here imports `nbformat`, `matplotlib` or `streamlit`.
  Notebook assembly lives in `report`. The dashboard (v4.0) will import
  from here, never the other way around.
- Every public symbol is re-exported below so callers can write
  ``from core import Period, load_week, genre_stats`` instead of reaching
  into individual modules.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

from .db import (
    find_week_db,
    latest_week_label,
    load_week,
    parse_db_filename,
    validate_schema,
)
from .metrics import (
    collaborations,
    general_stats,
    genre_stats,
    top_countries,
    top_countries_by_likes,
    top_songs,
    top_songs_by_country,
    video_metrics,
)
from .periods import Period, previous_week, week_from_label

__all__ = [
    # periods
    "Period",
    "previous_week",
    "week_from_label",
    # db
    "find_week_db",
    "latest_week_label",
    "load_week",
    "parse_db_filename",
    "validate_schema",
    # metrics
    "collaborations",
    "general_stats",
    "genre_stats",
    "top_countries",
    "top_countries_by_likes",
    "top_songs",
    "top_songs_by_country",
    "video_metrics",
]
