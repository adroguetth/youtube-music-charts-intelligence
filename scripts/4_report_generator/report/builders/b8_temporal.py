"""
B8 - Temporal Analysis
============================================================================
Builder for Section 8: Temporal Analysis.

Responsibilities
----------------
- Emit the section title.
- Subsection 8.1: Views evolution by quarter (grouped bar chart).
- Subsection 8.2: Engagement evolution by quarter (grouped bar chart).
- Subsection 8.3: Release distribution by quarter (bar chart).
- Inject AI insights after each subsection (if provided).

Notes
-----
- Uses the `CATEGORICAL_PALETTE` from `theme.py` because each color
  represents a different genre (multi-series).
- Uses `style_axes` and `format_axis_millions` for consistency.
- The charts are grouped bar charts (not line charts) to match the
  standardized design.
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


def build_temporal_analysis(
    df: pd.DataFrame,
    period,
    language: str,
    insights: dict[str, str] | None = None,
) -> list:
    """
    Build the Temporal Analysis section.

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
    cells.append(new_markdown_cell(section_title("temporal_analysis", language)))

    # ========================================================================
    # Shared data preparation (used by 8.1 and 8.2)
    # ========================================================================
    cells.append(
        new_code_cell(
            "top5_genres = genre_stats.nlargest(5, 'total_songs')['macro_genre'].tolist()\n"
            "df_temporal = df[df['macro_genre'].isin(top5_genres)].copy()\n"
            "\n"
            "temporal_views = df_temporal.groupby(['upload_quarter', 'macro_genre'])['views'].sum().reset_index()\n"
            "temporal_engagement = df_temporal.groupby(['upload_quarter', 'macro_genre'])['engagement'].mean().reset_index()"
        )
    )

    # ========================================================================
    # 8.1 Views Evolution by Quarter
    # ========================================================================
    cells.append(
        new_markdown_cell(
            "### 8.1. Views Evolution by Quarter"
            if language == "en"
            else "### 8.1. Evolución de Vistas por Trimestre"
        )
    )
    cells.append(
        new_code_cell(
            "fig1, ax1 = plt.subplots(figsize=(12, 6))\n"
            "fig1.patch.set_facecolor(YT_BG); ax1.set_facecolor(YT_BG)\n"
            "\n"
            "# Se usa CATEGORICAL_PALETTE para distinguir los géneros\n"
            "sns.barplot(data=temporal_views, x='upload_quarter', y='views', hue='macro_genre', palette=CATEGORICAL_PALETTE, ax=ax1)\n"
            "\n"
            "ax1.set_title('Views Evolution by Quarter (Top 5 Genres)', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "ax1.set_xlabel('Release Quarter', fontsize=11, color=YT_TEXT)\n"
            "ax1.set_ylabel('Total Views', fontsize=11, color=YT_TEXT)\n"
            "ax1.yaxis.set_major_formatter(FuncFormatter(format_axis_millions))\n"
            "\n"
            "style_axes(ax1, grid_axis='y')\n"
            "\n"
            "legend1 = ax1.get_legend()\n"
            "if legend1:\n"
            "    legend1.get_frame().set_edgecolor(YT_GRID); legend1.get_frame().set_linewidth(0.8)\n"
            "    for text in legend1.get_texts(): text.set_color(YT_TEXT)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        )
    )
    if insights and insights.get("temporal_views"):
        cells.append(new_markdown_cell(insights["temporal_views"]))

    # ========================================================================
    # 8.2 Engagement Evolution by Quarter
    # ========================================================================
    cells.append(
        new_markdown_cell(
            "### 8.2. Engagement Evolution by Quarter"
            if language == "en"
            else "### 8.2. Evolución del Engagement por Trimestre"
        )
    )
    cells.append(
        new_code_cell(
            "fig2, ax2 = plt.subplots(figsize=(12, 6))\n"
            "fig2.patch.set_facecolor(YT_BG); ax2.set_facecolor(YT_BG)\n"
            "\n"
            "sns.barplot(data=temporal_engagement, x='upload_quarter', y='engagement', hue='macro_genre', palette=CATEGORICAL_PALETTE, ax=ax2)\n"
            "\n"
            "ax2.set_title('Engagement Evolution by Quarter (Top 5 Genres)', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "ax2.set_xlabel('Release Quarter', fontsize=11, color=YT_TEXT)\n"
            "ax2.set_ylabel('Engagement (%)', fontsize=11, color=YT_TEXT)\n"
            "\n"
            "style_axes(ax2, grid_axis='y')\n"
            "\n"
            "legend2 = ax2.get_legend()\n"
            "if legend2:\n"
            "    legend2.get_frame().set_edgecolor(YT_GRID); legend2.get_frame().set_linewidth(0.8)\n"
            "    for text in legend2.get_texts(): text.set_color(YT_TEXT)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        )
    )
    if insights and insights.get("temporal_engagement"):
        cells.append(new_markdown_cell(insights["temporal_engagement"]))

    # ========================================================================
    # 8.3 Release Distribution by Quarter
    # ========================================================================
    cells.append(
        new_markdown_cell(
            "### 8.3. Release Distribution by Quarter"
            if language == "en"
            else "### 8.3. Distribución de Lanzamientos por Trimestre"
        )
    )
    cells.append(
        new_code_cell(
            "season_counts = df['upload_quarter'].value_counts().sort_index()\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(8, 5))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "\n"
            "bars = ax.bar(season_counts.index, season_counts.values, color=YT_RED, edgecolor='none')\n"
            "\n"
            "ax.set_xlabel('Quarter', fontsize=11, color=YT_TEXT)\n"
            "ax.set_ylabel('Number of Songs', fontsize=11, color=YT_TEXT)\n"
            "ax.set_title('Release Distribution by Quarter', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "\n"
            "style_axes(ax, grid_axis='y')\n"
            "add_bar_labels(ax, fmt='{:.0f}', horizontal=False)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        )
    )
    if insights and insights.get("temporal_releases"):
        cells.append(new_markdown_cell(insights["temporal_releases"]))

    return cells
