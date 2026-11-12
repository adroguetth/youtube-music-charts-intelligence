"""
B3 - Continent Analysis
============================================================================
Builder for Section 3: Continent Analysis.

Responsibilities
----------------
- Emit the section title.
- Emit a code cell that calculates song distribution by continent.
- Display a summary table.
- Generate a horizontal bar chart showing the distribution.

Notes
-----
- Uses the standardized color palette defined in `report.theme`.
- Uses `style_axes` and `add_bar_labels` to maintain consistency.
- Continents are mapped in the notebook's SETUP_CODE via `get_continent`.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import pandas as pd
from nbformat.v4 import new_code_cell, new_markdown_cell

from report.titles import section_title


def build_continents(df: pd.DataFrame, period, language: str) -> list:
    """
    Build the Continent Analysis section.

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
        new_markdown_cell(section_title("continents", language)),
        new_code_cell(
            # 1. Aggregate data by continent
            "continent_stats = df.groupby('continent').agg(\n"
            "    total_songs=('track_name', 'count'),\n"
            "    total_views=('views', 'sum'),\n"
            "    total_likes=('likes', 'sum')\n"
            ").reset_index().sort_values('total_songs', ascending=False)\n"
            "\n"
            "display(continent_stats)\n"
            "\n"
            # 2. Prepare the figure
            "fig, ax = plt.subplots(figsize=(10, 6))\n"
            "fig.patch.set_facecolor(YT_BG)\n"
            "ax.set_facecolor(YT_BG)\n"
            "\n"
            # 3. Draw horizontal bars with a solid color
            "bars = ax.barh(continent_stats['continent'], continent_stats['total_songs'],\n"
            "               color=YT_RED, edgecolor='none', height=BAR_HEIGHT)\n"
            "\n"
            # 4. Labels and title
            "ax.set_xlabel('Number of Songs', fontsize=11, color=YT_TEXT)\n"
            "ax.set_title('Song Distribution by Continent', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "\n"
            "ax.invert_yaxis() # Ensure the largest category is at the top\n"
            "\n"
            # 5. Apply shared styling and data labels
            "style_axes(ax, grid_axis='x')\n"
            "add_bar_labels(ax, fmt='{:.0f}', horizontal=True)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        ),
    ]
