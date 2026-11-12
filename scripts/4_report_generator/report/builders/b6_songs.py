"""
B6 - Song Metrics
============================================================================
Builder for Section 6: Song Metrics.

Responsibilities
----------------
- Emit the section title.
- Subsection 6.1: Top 10 songs by views (table).
- Subsection 6.2: Top 10 songs by likes (table).
- Subsection 6.3: Top 10 songs by engagement (table).

Notes
-----
- All tables include the `macro_genre` column to provide context.
- Uses `display()` for clean rendering in Jupyter.
- No plots are generated in this section.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import pandas as pd
from nbformat.v4 import new_code_cell, new_markdown_cell

from report.titles import section_title


def build_top_songs(df: pd.DataFrame, period, language: str) -> list:
    """
    Build the Song Metrics section.

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
        new_markdown_cell(section_title("top_songs", language)),

        # ----------------------------------------------------------------------
        # 6.1 Top Songs by Views
        # ----------------------------------------------------------------------
        new_markdown_cell("### 6.1. Top Songs by Views" if language == "en" else "### 6.1. Top Canciones por Vistas"),
        new_code_cell(
            "display(df.nlargest(10, 'views')[\n"
            "    ['rank', 'track_name', 'artist_names', 'macro_genre', 'views', 'artist_country']\n"
            "])"
        ),

        # ----------------------------------------------------------------------
        # 6.2 Top Songs by Likes
        # ----------------------------------------------------------------------
        new_markdown_cell("### 6.2. Top Songs by Likes" if language == "en" else "### 6.2. Top Canciones por Likes"),
        new_code_cell(
            "display(df.nlargest(10, 'likes')[\n"
            "    ['rank', 'track_name', 'artist_names', 'macro_genre', 'likes', 'artist_country']\n"
            "])"
        ),

        # ----------------------------------------------------------------------
        # 6.3 Top Songs by Engagement
        # ----------------------------------------------------------------------
        new_markdown_cell("### 6.3. Top Songs by Engagement" if language == "en" else "### 6.3. Top Canciones por Engagement"),
        new_code_cell(
            "display(df.nlargest(10, 'engagement')[\n"
            "    ['rank', 'track_name', 'artist_names', 'macro_genre', 'engagement', 'artist_country']\n"
            "])"
        ),
    ]
