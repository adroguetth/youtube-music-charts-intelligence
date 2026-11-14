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
- Inject AI insights after each subsection (if provided).

Notes
-----
- All tables include the `macro_genre` column to provide context.
- Uses `display()` for clean rendering in Jupyter.
- No plots are generated in this section.
- AI insights are injected by the builder itself (not by `notebook.py`)
  to allow per-subsection placement.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import pandas as pd
from nbformat.v4 import new_code_cell, new_markdown_cell

from report.titles import section_title


def build_top_songs(
    df: pd.DataFrame,
    period,
    language: str,
    insights: dict[str, str] | None = None,
) -> list:
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
    insights : dict[str, str] or None
        Optional mapping of ``section_id -> markdown_text``. If provided,
        the insight for each subsection is injected right after its cells.

    Returns
    -------
    list
        A list of `nbformat` cells.
    """
    cells: list = []

    # ========================================================================
    # Section title
    # ========================================================================
    cells.append(new_markdown_cell(section_title("top_songs", language)))

    # ========================================================================
    # 6.1 Top Songs by Views
    # ========================================================================
    cells.append(
        new_markdown_cell(
            "### 6.1. Top Songs by Views"
            if language == "en"
            else "### 6.1. Top Canciones por Vistas"
        )
    )
    cells.append(
        new_code_cell(
            "display(df.nlargest(10, 'views')[\n"
            "    ['rank', 'track_name', 'artist_names', 'macro_genre', 'views', 'artist_country']\n"
            "])"
        )
    )
    if insights and insights.get("top_songs_by_views"):
        cells.append(new_markdown_cell(insights["top_songs_by_views"]))

    # ========================================================================
    # 6.2 Top Songs by Likes
    # ========================================================================
    cells.append(
        new_markdown_cell(
            "### 6.2. Top Songs by Likes"
            if language == "en"
            else "### 6.2. Top Canciones por Likes"
        )
    )
    cells.append(
        new_code_cell(
            "display(df.nlargest(10, 'likes')[\n"
            "    ['rank', 'track_name', 'artist_names', 'macro_genre', 'likes', 'artist_country']\n"
            "])"
        )
    )
    if insights and insights.get("top_songs_by_likes"):
        cells.append(new_markdown_cell(insights["top_songs_by_likes"]))

    # ========================================================================
    # 6.3 Top Songs by Engagement
    # ========================================================================
    cells.append(
        new_markdown_cell(
            "### 6.3. Top Songs by Engagement"
            if language == "en"
            else "### 6.3. Top Canciones por Engagement"
        )
    )
    cells.append(
        new_code_cell(
            "display(df.nlargest(10, 'engagement')[\n"
            "    ['rank', 'track_name', 'artist_names', 'macro_genre', 'engagement', 'artist_country']\n"
            "])"
        )
    )
    if insights and insights.get("top_songs_by_engagement"):
        cells.append(new_markdown_cell(insights["top_songs_by_engagement"]))

    return cells
