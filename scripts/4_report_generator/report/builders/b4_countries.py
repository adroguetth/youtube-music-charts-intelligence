"""
B4 - Country Analysis
============================================================================
Builder for Section 4: Country Analysis.

Responsibilities
----------------
- Emit the section title.
- Subsection 4.1: Top 10 countries by song count (table + bar chart).
- Subsection 4.2: Top 10 countries by total likes (table + bar chart).
- Subsection 4.3: Top 5 songs for the top 5 countries (tables only).
- Inject AI insights after each subsection (if provided).

Notes
-----
- Uses `style_axes` and `add_bar_labels` from `common.py`.
- Uses theme colors to maintain visual consistency.
- The Top 5 songs subsection iterates over the top 5 countries to avoid
  an excessively long notebook output.
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


def build_countries(
    df: pd.DataFrame,
    period,
    language: str,
    insights: dict[str, str] | None = None,
) -> list:
    """
    Build the Country Analysis section.

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
    cells.append(new_markdown_cell(section_title("countries", language)))

    # ========================================================================
    # 4.1 Top Countries by Song Count
    # ========================================================================
    cells.append(
        new_markdown_cell(
            "### 4.1. Top Countries by Song Count"
            if language == "en"
            else "### 4.1. Top Países por Cantidad de Canciones"
        )
    )
    cells.append(
        new_code_cell(
            "top_countries = (df\n"
            "    .groupby('artist_country')\n"
            "    .agg(total_songs=('rank', 'count'), total_views=('views', 'sum'))\n"
            "    .reset_index()\n"
            "    .sort_values('total_songs', ascending=False)\n"
            "    .head(10))\n"
            "total = top_countries['total_songs'].sum()\n"
            "top_countries['percentage'] = (top_countries['total_songs'] / total * 100).round(2)\n"
            "display(top_countries)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(10, 6))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "\n"
            "bars = ax.barh(top_countries['artist_country'], top_countries['total_songs'],\n"
            "               color=YT_RED, edgecolor='none', height=BAR_HEIGHT)\n"
            "\n"
            "ax.set_xlabel('Number of Songs', fontsize=11, color=YT_TEXT)\n"
            "ax.set_title('Top 10 Countries by Song Count', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.invert_yaxis()\n"
            "\n"
            "style_axes(ax, grid_axis='x')\n"
            "add_bar_labels(ax, fmt='{:.0f}', horizontal=True)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        )
    )
    if insights and insights.get("countries_by_songs"):
        cells.append(new_markdown_cell(insights["countries_by_songs"]))

    # ========================================================================
    # 4.2 Top Countries by Total Likes
    # ========================================================================
    cells.append(
        new_markdown_cell(
            "### 4.2. Top Countries by Total Likes"
            if language == "en"
            else "### 4.2. Top Países por Total de Likes"
        )
    )
    cells.append(
        new_code_cell(
            "top_likes = (df\n"
            "    .groupby('artist_country')['likes']\n"
            "    .sum()\n"
            "    .reset_index()\n"
            "    .rename(columns={'likes': 'total_likes'})\n"
            "    .sort_values('total_likes', ascending=False)\n"
            "    .head(10))\n"
            "\n"
            "def format_likes(x):\n"
            "    if x >= 1_000_000: return f'{x/1_000_000:.1f}M'\n"
            "    if x >= 1_000: return f'{x/1_000:.1f}K'\n"
            "    return str(x)\n"
            "\n"
            "top_likes['total_likes_fmt'] = top_likes['total_likes'].apply(format_likes)\n"
            "display(top_likes[['artist_country', 'total_likes_fmt']])\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(10, 6))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "\n"
            "bars = ax.barh(top_likes['artist_country'], top_likes['total_likes'],\n"
            "               color=YT_RED, edgecolor='none', height=BAR_HEIGHT)\n"
            "\n"
            "ax.set_xlabel('Total Likes', fontsize=11, color=YT_TEXT)\n"
            "ax.set_title('Top 10 Countries by Total Likes', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.invert_yaxis()\n"
            "ax.xaxis.set_major_formatter(FuncFormatter(format_axis_millions))\n"
            "\n"
            "style_axes(ax, grid_axis='x')\n"
            # Add custom labels for likes formatted with K/M
            "for p in ax.patches:\n"
            "    width = p.get_width()\n"
            "    if width > 0:\n"
            "        ax.text(width + (width*0.02), p.get_y() + p.get_height()/2, \n"
            "                format_likes(width), ha='left', va='center', fontsize=11, color=YT_TEXT)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        )
    )
    if insights and insights.get("countries_by_likes"):
        cells.append(new_markdown_cell(insights["countries_by_likes"]))

    # ========================================================================
    # 4.3 Top 5 Songs by Top 5 Countries
    # ========================================================================
    cells.append(
        new_markdown_cell(
            "### 4.3. Top 5 Songs by Top 5 Countries"
            if language == "en"
            else "### 4.3. Top 5 Canciones por los 5 Primeros Países"
        )
    )
    cells.append(
        new_code_cell(
            "# Limit to top 5 countries\n"
            "top_countries_list = df['artist_country'].value_counts().head(5).index.tolist()\n"
            "for country in top_countries_list:\n"
            "    display(HTML(f'<hr style=\"border: 1px solid {YT_GRID}; margin: 20px 0;\">'))\n"
            "    display(HTML(f'<h4 style=\"color: {YT_TEXT}; margin-bottom: 10px;\">{country}</h4>'))\n"
            "    \n"
            "    df_country = df[df['artist_country'] == country]\n"
            "    \n"
            "    # Top 5 by views\n"
            "    top_views = df_country.nlargest(5, 'views')[['track_name', 'artist_names', 'views', 'likes', 'engagement']].copy()\n"
            "    top_views['views'] = top_views['views'].apply(format_number)\n"
            "    top_views['likes'] = top_views['likes'].apply(format_number)\n"
            "    display(HTML('<b>Top 5 by views:</b>'))\n"
            "    display(top_views)\n"
            "    \n"
            "    # Top 5 by likes\n"
            "    top_likes_country = df_country.nlargest(5, 'likes')[['track_name', 'artist_names', 'views', 'likes', 'engagement']].copy()\n"
            "    top_likes_country['views'] = top_likes_country['views'].apply(format_number)\n"
            "    top_likes_country['likes'] = top_likes_country['likes'].apply(format_number)\n"
            "    display(HTML('<b>Top 5 by likes:</b>'))\n"
            "    display(top_likes_country)\n"
            "\n"
            "display(HTML(f'<hr style=\"border: 1px solid {YT_GRID}; margin: 20px 0;\">'))"
        )
    )
    if insights and insights.get("countries_top_songs"):
        cells.append(new_markdown_cell(insights["countries_top_songs"]))

    return cells
