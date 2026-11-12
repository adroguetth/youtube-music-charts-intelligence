"""
B10 - Executive Summary
============================================================================
Builder for Section 10: Executive Summary.

Responsibilities
----------------
- Emit the section title.
- Emit a code cell with a numeric recap of the week's key metrics.

Notes
-----
- In v1.0, this section prints a simple numeric recap (total songs,
  countries, genres, views, likes, and average engagement).
- In v2.0, the AI-generated analytical text will be injected here
  (or right after this cell) by `report.notebook.generate_notebook`.
- Uses the `general_stats` and `format_number` helpers defined in the
  notebook's SETUP_CODE.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import pandas as pd
from nbformat.v4 import new_code_cell, new_markdown_cell

from report.titles import section_title


def build_exec_summary(df: pd.DataFrame, period, language: str) -> list:
    """
    Build the Executive Summary section.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched DataFrame for the period.
    period : core.periods.Period
        The reporting period.
    language : str
        ``"en"`` or ``"es"``.

    Returns
    -------
    list
        A list of `nbformat` cells.
    """
    return [
        new_markdown_cell(section_title("exec_summary", language)),
        new_code_cell(
            "stats = general_stats(df)\n"
            "print(f\"Songs: {stats['total_songs']}\")\n"
            "print(f\"Countries: {stats['unique_countries']}\")\n"
            "print(f\"Genres: {stats['unique_genres']}\")\n"
            "print(f\"Total views: {format_number(stats['total_views'])}\")\n"
            "print(f\"Total likes: {format_number(stats['total_likes'])}\")\n"
            "print(f\"Avg engagement: {stats['avg_engagement']:.2f}%\")"
        ),
    ]
