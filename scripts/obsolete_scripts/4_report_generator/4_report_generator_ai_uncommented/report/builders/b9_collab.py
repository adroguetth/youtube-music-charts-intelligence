"""
B9 - Collaborations Analysis
============================================================================
Builder for Section 9: Collaborations Analysis.

Responsibilities
----------------
- Emit the section title.
- Subsection 9.1: Views vs Number of Artists (boxplot).
- Subsection 9.2: Engagement vs Number of Artists (boxplot).

Notes
-----
- Boxplots are used instead of scatter plots to better show the
  distribution, median, and outliers.
- Uses `style_axes` from the notebook's SETUP_CODE.
- The boxplots use `YT_DARK_GREY` for solos and `YT_RED` for collaborations.
- The two charts are separated into distinct code cells for better
  readability (full width).

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
        
        # 1. Tabla de resumen
        new_code_cell(
            "collab_stats = df.groupby('is_collaboration').agg(\n"
            "    count=('track_name', 'count'),\n"
            "    avg_views=('views', 'mean'),\n"
            "    avg_engagement=('engagement', 'mean')\n"
            ").reset_index()\n"
            "\n"
            "collab_stats['is_collaboration'] = collab_stats['is_collaboration'].map({0: 'Solo', 1: 'Collaboration'})\n"
            "collab_stats['avg_views'] = collab_stats['avg_views'].apply(lambda x: f'{x:,.0f}')\n"
            "collab_stats['avg_engagement'] = collab_stats['avg_engagement'].round(2).astype(str) + '%'\n"
            "display(collab_stats)"
        ),

        # ----------------------------------------------------------------------
        # 9.1 Views vs Number of Artists
        # ----------------------------------------------------------------------
        new_markdown_cell("### 9.1. Views vs Number of Artists" if language == "en" else "### 9.1. Vistas vs Cantidad de Artistas"),
        new_code_cell(
            "fig, ax = plt.subplots(figsize=(10, 5))\n"
            "fig.patch.set_facecolor(YT_BG)\n"
            "ax.set_facecolor(YT_BG)\n"
            "\n"
            "sns.boxplot(\n"
            "    data=df, x='artist_count', y='views', hue='is_collaboration', \n"
            "    palette={0: YT_DARK_GREY, 1: YT_RED}, ax=ax\n"
            ")\n"
            "\n"
            "ax.set_title('Views vs Number of Artists', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.set_xlabel('Number of Artists', fontsize=11, color=YT_TEXT)\n"
            "ax.set_ylabel('Views', fontsize=11, color=YT_TEXT)\n"
            "ax.yaxis.set_major_formatter(FuncFormatter(format_axis_millions))\n"
            "\n"
            "style_axes(ax, grid_axis='y')\n"
            "\n"
            "legend = ax.get_legend()\n"
            "if legend:\n"
            "    legend.get_frame().set_edgecolor(YT_GRID)\n"
            "    legend.get_frame().set_linewidth(0.8)\n"
            "    for text in legend.get_texts(): text.set_color(YT_TEXT)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        ),

        # ----------------------------------------------------------------------
        # 9.2 Engagement vs Number of Artists
        # ----------------------------------------------------------------------
        new_markdown_cell("### 9.2. Engagement vs Number of Artists" if language == "en" else "### 9.2. Engagement vs Cantidad de Artistas"),
        new_code_cell(
            "fig, ax = plt.subplots(figsize=(10, 5))\n"
            "fig.patch.set_facecolor(YT_BG)\n"
            "ax.set_facecolor(YT_BG)\n"
            "\n"
            "sns.boxplot(\n"
            "    data=df, x='artist_count', y='engagement', hue='is_collaboration', \n"
            "    palette={0: YT_DARK_GREY, 1: YT_RED}, ax=ax\n"
            ")\n"
            "\n"
            "ax.set_title('Engagement vs Number of Artists', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.set_xlabel('Number of Artists', fontsize=11, color=YT_TEXT)\n"
            "ax.set_ylabel('Engagement (%)', fontsize=11, color=YT_TEXT)\n"
            "\n"
            "style_axes(ax, grid_axis='y')\n"
            "\n"
            "legend = ax.get_legend()\n"
            "if legend:\n"
            "    legend.get_frame().set_edgecolor(YT_GRID)\n"
            "    legend.get_frame().set_linewidth(0.8)\n"
            "    for text in legend.get_texts(): text.set_color(YT_TEXT)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        ),
    ]
