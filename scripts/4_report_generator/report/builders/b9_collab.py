"""
B9 - Collaborations Analysis
============================================================================
Builder for Section 9: Collaborations Analysis.

Responsibilities
----------------
- Emit the section title.
- Emit a code cell that calculates collaboration statistics (solo vs collab).
- Display a summary table.
- Generate two boxplots comparing views and engagement between solos
  and collaborations.

Notes
-----
- Boxplots are used instead of scatter plots to better show the
  distribution, median, and outliers.
- Uses `style_axes` from `common.py`.
- The boxplots use `YT_DARK_GREY` for solos and `YT_RED` for collaborations.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import pandas as pd
from nbformat.v4 import new_code_cell, new_markdown_cell

from report.titles import section_title


def build_collaborations(df: pd.DataFrame, period, language: str) -> list:
    """
    Build the Collaborations Analysis section.

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
        new_markdown_cell(section_title("collaborations", language)),
        new_code_cell(
            # 1. Table aggregation
            "collab_stats = df.groupby('is_collaboration').agg(\n"
            "    count=('track_name', 'count'),\n"
            "    avg_views=('views', 'mean'),\n"
            "    avg_engagement=('engagement', 'mean')\n"
            ").reset_index()\n"
            "\n"
            "collab_stats['is_collaboration'] = collab_stats['is_collaboration'].map({0: 'Solo', 1: 'Collaboration'})\n"
            "collab_stats['avg_views'] = collab_stats['avg_views'].apply(lambda x: f'{x:,.0f}')\n"
            "collab_stats['avg_engagement'] = collab_stats['avg_engagement'].round(2).astype(str) + '%'\n"
            "display(collab_stats)\n"
            "\n"
            # 2. Figure preparation
            "fig, axes = plt.subplots(1, 2, figsize=(14, 6))\n"
            "fig.patch.set_facecolor(YT_BG)\n"
            "axes[0].set_facecolor(YT_BG)\n"
            "axes[1].set_facecolor(YT_BG)\n"
            "\n"
            # 3. Boxplot 1: Views
            "sns.boxplot(\n"
            "    data=df, x='artist_count', y='views', hue='is_collaboration', \n"
            "    palette={0: YT_DARK_GREY, 1: YT_RED}, ax=axes[0]\n"
            ")\n"
            "axes[0].set_title('Views vs Number of Artists', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "axes[0].set_xlabel('Number of Artists', fontsize=11, color=YT_TEXT)\n"
            "axes[0].set_ylabel('Views', fontsize=11, color=YT_TEXT)\n"
            "axes[0].yaxis.set_major_formatter(FuncFormatter(format_axis_millions))\n"
            "\n"
            # 4. Boxplot 2: Engagement
            "sns.boxplot(\n"
            "    data=df, x='artist_count', y='engagement', hue='is_collaboration', \n"
            "    palette={0: YT_DARK_GREY, 1: YT_RED}, ax=axes[1]\n"
            ")\n"
            "axes[1].set_title('Engagement vs Number of Artists', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "axes[1].set_xlabel('Number of Artists', fontsize=11, color=YT_TEXT)\n"
            "axes[1].set_ylabel('Engagement (%)', fontsize=11, color=YT_TEXT)\n"
            "\n"
            # 5. Styling loop
            "for ax in axes:\n"
            "    style_axes(ax, grid_axis='y')\n"
            "    legend = ax.get_legend()\n"
            "    if legend:\n"
            "        legend.get_frame().set_edgecolor(YT_GRID)\n"
            "        legend.get_frame().set_linewidth(0.8)\n"
            "        for text in legend.get_texts(): text.set_color(YT_TEXT)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        ),
    ]
