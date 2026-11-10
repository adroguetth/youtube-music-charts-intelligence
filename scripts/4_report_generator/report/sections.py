"""
Sections - Report Structure and Builder Registry
============================================================================
Declares the ordered list of sections that make up the weekly report
and wires each section identifier to its builder function.

Responsibilities
----------------
- Declare the ordered list of section identifiers (`WEEKLY_SECTIONS`).
- Provide a single registry (`BUILDERS`) mapping each identifier to the
  callable that produces its cells.

Notes
-----
- Builders live in `report.builders`. This module only lists and wires
  them, so the report order is visible in one place and can be changed
  without touching the builders themselves.
- Adding a new section is a two-step change:
    1. Append its identifier to `WEEKLY_SECTIONS`.
    2. Register its builder in `BUILDERS`.
  The tests in `tests/test_sections.py` assert that both stay in sync.
- When the monthly report arrives (v3.0), `WEEKLY_SECTIONS` will be
  generalised into a `SECTION_SETS` mapping keyed by period kind, and
  `BUILDERS` will grow with the monthly-only builders. No builder that
  exists today will need to change.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

from typing import Callable

from .builders import (
    build_collaborations,
    build_countries,
    build_exec_summary,
    build_general_stats,
    build_genre_analysis,
    build_intro,
    build_top_songs,
    build_video_metrics,
)


# ============================================================================
# SECTION ORDER
# ============================================================================
WEEKLY_SECTIONS: list[str] = [
    "intro",
    "general_stats",
    "countries",
    "genre_analysis",
    "video_metrics",
    "top_songs",
    "collaborations",
    "exec_summary",
]


# ============================================================================
# BUILDER REGISTRY
# ============================================================================
# Each builder has the signature:
#     builder(df, period, language) -> list[nbformat.cells]
BUILDERS: dict[str, Callable] = {
    "intro": build_intro,
    "general_stats": build_general_stats,
    "countries": build_countries,
    "genre_analysis": build_genre_analysis,
    "video_metrics": build_video_metrics,
    "top_songs": build_top_songs,
    "collaborations": build_collaborations,
    "exec_summary": build_exec_summary,
}
