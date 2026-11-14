"""
B2 - General Statistics
============================================================================
Builder for Section 2: General Statistics.

Responsibilities
----------------
- Emit the section title.
- Emit a code cell that calculates general statistics (total songs,
  unique countries, unique genres, total views/likes, averages).
- Format the output as a vertical table to avoid horizontal overflow.

Notes
-----
- This builder does not create any plots in the current version.
- The numeric formatting uses `format_number` from the notebook's
  SETUP_CODE to avoid scientific notation and trailing zeros.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import pandas as pd
from nbformat.v4 import new_code_cell, new_markdown_cell

from report.titles import section_title


def build_general_stats(df: pd.DataFrame, period, language: str) -> list:
    """
    Build the General Statistics section.

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
        new_markdown_cell(section_title("general_stats", language)),
        new_code_cell(
            # 1. Calculate stats.
            # 2. Build a DataFrame with formatted values.
            # 3. Display it.
            "stats = general_stats(df)\n"
            "\n"
            "formatted_stats = pd.DataFrame({\n"
            "    'Metric': [\n"
            "        'Total Songs',\n"
            "        'Unique Countries',\n"
            "        'Unique Genres',\n"
            "        'Total Views',\n"
            "        'Total Likes',\n"
            "        'Total Comments',\n"
            "        'Avg Views',\n"
            "        'Avg Likes',\n"
            "        'Avg Engagement'\n"
            "    ],\n"
            "    'Value': [\n"
            "        f\"{stats['total_songs']:,}\",\n"
            "        f\"{stats['unique_countries']:,}\",\n"
            "        f\"{stats['unique_genres']:,}\",\n"
            "        format_number(stats['total_views']),\n"
            "        format_number(stats['total_likes']),\n"
            "        format_number(stats['total_comments']),\n"
            "        format_number(stats['avg_views']),\n"
            "        format_number(stats['avg_likes']),\n"
            "        f\"{stats['avg_engagement']:.2f}%\"\n"
            "    ]\n"
            "})\n"
            "\n"
            "display(formatted_stats)"
        ),
    ]
