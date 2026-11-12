"""
Builders - Report Section Registry
============================================================================
This package contains the individual cell builders for each section of
the weekly report. Each builder lives in its own file to keep the code
maintainable and easy to test.

This `__init__.py` exposes all builders under the `report.builders`
namespace so that `report.sections` can import them without knowing
about the internal file structure.

Responsibilities
----------------
- Re-export every builder function.

Notes
-----
- If you add a new builder file (e.g., `b11_new_section.py`), remember
  to import its `build_*` function here.
- The `build_setup` function is not re-exported here because it lives in
  `report.setup` (the setup cell is not a section, it is prepended to
  the notebook).

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

from report.builders.b1_intro import build_intro
from report.builders.b2_general import build_general_stats
from report.builders.b3_continents import build_continents
from report.builders.b4_countries import build_countries
from report.builders.b5_genres import build_genre_analysis
from report.builders.b6_songs import build_top_songs
from report.builders.b7_video import build_video_metrics
from report.builders.b8_temporal import build_temporal_analysis
from report.builders.b9_collab import build_collaborations
from report.builders.b10_summary import build_exec_summary

__all__ = [
    "build_intro",
    "build_general_stats",
    "build_continents",
    "build_countries",
    "build_genre_analysis",
    "build_top_songs",
    "build_video_metrics",
    "build_temporal_analysis",
    "build_collaborations",
    "build_exec_summary",
]
