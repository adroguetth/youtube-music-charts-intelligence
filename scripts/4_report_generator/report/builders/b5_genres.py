"""
B5 - Genre Analysis
============================================================================
Builder for Section 5: Genre Analysis.

Responsibilities
----------------
- Emit the section title.
- Subsection 5.1: Genre statistics table.
- Subsection 5.2: Genre distribution treemap (keeps multi-color).
- Subsection 5.3: Top 10 genres by engagement rate (table + bar chart).
- Subsection 5.4: Country-Genre distribution heatmap (keeps multi-color).

Notes
-----
- The Treemap calculates luminance automatically to switch text color
  between white and black, ensuring readability on both dark and light
  blocks.
- Uses `style_axes` and `add_bar_labels` for standard charts.
- The Heatmap retains its `Reds` colormap because color represents data
  density there.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import pandas as pd
from nbformat.v4 import new_code_cell, new_markdown_cell

from report.titles import section_title


def build_genre_analysis(df: pd.DataFrame, period, language: str) -> list:
    """
    Build the Genre Analysis section.

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
        new_markdown_cell(section_title("genre_analysis", language)),

        # ----------------------------------------------------------------------
        # 5.1 Genre Statistics (Table) - FIX: Added missing title
        # ----------------------------------------------------------------------
        new_markdown_cell("### 5.1. Genre Statistics" if language == "en" else "### 5.1. Estadísticas por Género"),
        new_code_cell(
            "genre_stats = (df\n"
            "    .groupby('macro_genre')\n"
            "    .agg(\n"
            "        total_songs=('track_name', 'count'),\n"
            "        total_views=('views', 'sum'),\n"
            "        total_likes=('likes', 'sum'),\n"
            "        avg_views=('views', 'mean'),\n"
            "        avg_likes=('likes', 'mean')\n"
            "    )\n"
            "    .reset_index()\n"
            "    .sort_values('total_songs', ascending=False))\n"
            "\n"
            "genre_stats['engagement_rate'] = (genre_stats['total_likes'] / genre_stats['total_views'] * 100).round(2).fillna(0)\n"
            "display(genre_stats.head(10)[['macro_genre', 'total_songs', 'engagement_rate']])"
        ),

        # ----------------------------------------------------------------------
        # 5.2 Genre Distribution Treemap
        # ----------------------------------------------------------------------
        new_markdown_cell("### 5.2. Genre Distribution Treemap" if language == "en" else "### 5.2. Treemap de Distribución de Géneros"),
        new_code_cell(
            "treemap_data = genre_stats.head(15).copy()\n"
            "sizes = treemap_data['total_songs'].values\n"
            "colors = plt.cm.Reds(np.linspace(0.3, 0.9, len(sizes)))\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(14, 8))\n"
            "ax.set_facecolor(YT_BG); fig.patch.set_facecolor(YT_BG)\n"
            "\n"
            "# Calculate rectangles\n"
            "rects = squarify.normalize_sizes(sizes, 14, 8)\n"
            "rects = squarify.squarify(rects, 0, 0, 14, 8)\n"
            "\n"
            "for i, (rect, color) in enumerate(zip(rects, colors)):\n"
            "    # Determine luminance to decide text color (white on dark, black on light)\n"
            "    luminance = 0.299*color[0] + 0.587*color[1] + 0.114*color[2]\n"
            "    text_color = 'white' if luminance < 0.6 else 'black'\n"
            "    \n"
            "    rect_obj = plt.Rectangle(\n"
            "        (rect['x'], rect['y']), rect['dx'], rect['dy'], \n"
            "        facecolor=color, edgecolor='white', linewidth=1.5\n"
            "    )\n"
            "    ax.add_patch(rect_obj)\n"
            "    \n"
            "    label = f\"{treemap_data['macro_genre'].iloc[i]}\\n{format_number(treemap_data['total_songs'].iloc[i])}\"\n"
            "    ax.text(\n"
            "        rect['x'] + rect['dx']/2, rect['y'] + rect['dy']/2, label, \n"
            "        ha='center', va='center', fontsize=11, color=text_color\n"
            "    )\n"
            "\n"
            "ax.set_xlim(0, 14); ax.set_ylim(0, 8)\n"
            "ax.set_title('Genre Distribution by Song Count', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.axis('off')\n"
            "plt.tight_layout(); plt.show()"
        ),

        # ----------------------------------------------------------------------
        # 5.3 Engagement Rate by Genre
        # ----------------------------------------------------------------------
        new_markdown_cell("### 5.3. Engagement Rate by Genre" if language == "en" else "### 5.3. Tasa de Engagement por Género"),
        new_code_cell(
            "engagement_chart = genre_stats.sort_values('engagement_rate', ascending=False).head(10)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(10, 6))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "\n"
            "bars = ax.barh(engagement_chart['macro_genre'], engagement_chart['engagement_rate'],\n"
            "               color=YT_RED, edgecolor='none', height=BAR_HEIGHT)\n"
            "\n"
            "ax.set_xlabel('Engagement Rate (%)', fontsize=11, color=YT_TEXT)\n"
            "ax.set_title('Top 10 Genres by Engagement Rate', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.invert_yaxis()\n"
            "\n"
            "style_axes(ax, grid_axis='x')\n"
            "add_bar_labels(ax, fmt='{:.1f}', suffix='%', horizontal=True)\n"
            "\n"
            "avg_engagement = genre_stats['engagement_rate'].mean()\n"
            "ax.axvline(x=avg_engagement, color=YT_DARK_GREY, linestyle='--', linewidth=1.5, alpha=0.9)\n"
            "ax.text(avg_engagement + 0.1, len(engagement_chart) - 0.5, f'Average: {avg_engagement:.1f}%',\n"
            "        fontsize=10, color=YT_DARK_GREY)\n"
            "\n"
            "plt.tight_layout(); plt.show()\n"
            "\n"
            "# Summary table\n"
            "stats_summary = pd.DataFrame({\n"
            "    'Statistic': ['Average', 'Median', 'Max', 'Min'],\n"
            "    'Value': [avg_engagement, genre_stats['engagement_rate'].median(), genre_stats['engagement_rate'].max(), genre_stats['engagement_rate'].min()],\n"
            "    'Genre': ['', '', genre_stats.loc[genre_stats['engagement_rate'].idxmax(), 'macro_genre'], genre_stats.loc[genre_stats['engagement_rate'].idxmin(), 'macro_genre']]\n"
            "})\n"
            "display(stats_summary)"
        ),

        # ----------------------------------------------------------------------
        # 5.4 Country-Genre Distribution Heatmap
        # ----------------------------------------------------------------------
        new_markdown_cell("### 5.4. Country-Genre Distribution Heatmap" if language == "en" else "### 5.4. Heatmap País-Género"),
        new_code_cell(
            "df_analysis = df[~df['artist_country'].isin(['Multi-country', 'Unknown'])]\n"
            "if not df_analysis.empty:\n"
            "    matrix = pd.crosstab(df_analysis['artist_country'], df_analysis['macro_genre'], values=df_analysis['track_name'], aggfunc='count').fillna(0)\n"
            "    top_countries_h = matrix.sum(axis=1).sort_values(ascending=False).head(12).index\n"
            "    top_genres = [g for g in genre_stats.nlargest(10, 'total_songs')['macro_genre'].tolist() if g in matrix.columns]\n"
            "    \n"
            "    if len(top_countries_h) > 0 and len(top_genres) > 0:\n"
            "        matrix_heatmap = matrix.loc[top_countries_h, top_genres].astype(int)\n"
            "        \n"
            "        fig, ax = plt.subplots(figsize=(12, 8))\n"
            "        fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "        \n"
            "        sns.heatmap(\n"
            "            matrix_heatmap, annot=True, fmt='d', cmap='Reds',\n"
            "            xticklabels=True, yticklabels=True, linewidths=0.5, linecolor='white', ax=ax\n"
            "        )\n"
            "        \n"
            "        ax.set_title('Country vs Genre Distribution', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "        ax.set_xlabel('Genre', fontsize=11, color=YT_TEXT)\n"
            "        ax.set_ylabel('Country', fontsize=11, color=YT_TEXT)\n"
            "        plt.xticks(rotation=45, ha='right')\n"
            "        plt.tight_layout(); plt.show()"
        ),
    ]
