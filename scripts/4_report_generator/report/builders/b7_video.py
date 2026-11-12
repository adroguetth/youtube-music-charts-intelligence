"""
B7 - Video Metrics
============================================================================
Builder for Section 7: Video Metrics.

Responsibilities
----------------
- Emit the section title.
- Subsection 7.1: Video summary table.
- Subsection 7.2: Average views by video type (horizontal bar chart).
- Subsection 7.3: Average engagement by video type (horizontal bar chart).
- Subsection 7.4: Duration analysis (histogram + boxplot).
- Subsection 7.5: Channel type distribution (horizontal bar chart).

Notes
-----
- Uses `style_axes` and `add_bar_labels` from `common.py`.
- Uses theme colors to maintain visual consistency.
- The duration analysis uses a Gaussian KDE overlaid on the histogram.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import pandas as pd
from nbformat.v4 import new_code_cell, new_markdown_cell

from report.titles import section_title


def build_video_metrics(df: pd.DataFrame, period, language: str) -> list:
    """
    Build the Video Metrics section.

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
        new_markdown_cell(section_title("video_metrics", language)),

        # ----------------------------------------------------------------------
        # 7.1 Video Summary
        # ----------------------------------------------------------------------
        new_markdown_cell("### 7.1. Video Summary" if language == "en" else "### 7.1. Resumen de Video"),
        new_code_cell(
            "video_stats = {\n"
            "    'Category': ['Official Videos', 'Lyric Videos', 'Live Performances', 'Collaborations'],\n"
            "    'Count': [df['is_official_video'].sum(), df['is_lyric_video'].sum(), df['is_live_performance'].sum(), df['is_collaboration'].sum()]\n"
            "}\n"
            "v_stats_df = pd.DataFrame(video_stats)\n"
            "v_stats_df['Percentage'] = (v_stats_df['Count'] / len(df) * 100).round(1).astype(str) + '%'\n"
            "display(v_stats_df)"
        ),

        # ----------------------------------------------------------------------
        # 7.2 Views by Video Type
        # ----------------------------------------------------------------------
        new_markdown_cell("### 7.2. Views by Video Type" if language == "en" else "### 7.2. Vistas por Tipo de Video"),
        new_code_cell(
            "df_video = df.copy()\n"
            "conditions = [df_video['is_official_video'] == 1, df_video['is_lyric_video'] == 1, df_video['is_live_performance'] == 1]\n"
            "choices = ['Official', 'Lyric', 'Live']\n"
            "df_video['video_type'] = np.select(conditions, choices, default='Other')\n"
            "\n"
            "views_stats = df_video.groupby('video_type').agg(\n"
            "    total_videos=('views', 'count'), \n"
            "    avg_views=('views', 'mean'), \n"
            "    median_views=('views', 'median'), \n"
            "    std_views=('views', 'std')\n"
            ").round(2).reset_index()\n"
            "\n"
            "table_views = views_stats.copy()\n"
            "table_views['total_videos'] = table_views['total_videos'].astype(int)\n"
            "table_views['avg_views'] = table_views['avg_views'].apply(lambda x: f'{x:,.0f}')\n"
            "table_views['median_views'] = table_views['median_views'].apply(lambda x: f'{x:,.0f}')\n"
            "table_views['std_views'] = table_views['std_views'].apply(lambda x: f'{x:,.0f}')\n"
            "table_views.columns = ['Video Type', 'Total Videos', 'Avg Views', 'Median Views', 'Std Dev']\n"
            "display(table_views)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(10, 5))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "\n"
            "sns.barplot(data=views_stats, y='video_type', x='avg_views', ax=ax, color=YT_RED, errorbar=None)\n"
            "\n"
            "ax.set_title('Average Views by Video Type', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.set_xlabel('Average Views', fontsize=11, color=YT_TEXT)\n"
            "ax.set_ylabel('Video Type', fontsize=11, color=YT_TEXT)\n"
            "ax.xaxis.set_major_formatter(FuncFormatter(format_axis_millions))\n"
            "\n"
            "style_axes(ax, grid_axis='x')\n"
            "\n"
            "for p in ax.patches:\n"
            "    width = p.get_width()\n"
            "    if width > 0:\n"
            "        ax.text(width + (width*0.02), p.get_y() + p.get_height()/2, \n"
            "                f'{width/1_000_000:.1f}M', ha='left', va='center', fontsize=11, color=YT_TEXT)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        ),

        # ----------------------------------------------------------------------
        # 7.3 Engagement by Video Type
        # ----------------------------------------------------------------------
        new_markdown_cell("### 7.3. Engagement by Video Type" if language == "en" else "### 7.3. Engagement por Tipo de Video"),
        new_code_cell(
            "engagement_by_type = df_video.groupby('video_type')['engagement'].mean().reset_index()\n"
            "engagement_by_type.columns = ['Video Type', 'Avg Engagement (%)']\n"
            "display(engagement_by_type)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(10, 5))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "\n"
            "sns.barplot(data=engagement_by_type, y='Video Type', x='Avg Engagement (%)', ax=ax, color=YT_RED, errorbar=None)\n"
            "\n"
            "ax.set_title('Average Engagement by Video Type', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.set_xlabel('Engagement (%)', fontsize=11, color=YT_TEXT)\n"
            "ax.set_ylabel('Video Type', fontsize=11, color=YT_TEXT)\n"
            "\n"
            "style_axes(ax, grid_axis='x')\n"
            "add_bar_labels(ax, fmt='{:.2f}', suffix='%', horizontal=True)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        ),

        # ----------------------------------------------------------------------
        # 7.4 Duration Analysis
        # ----------------------------------------------------------------------
        new_markdown_cell("### 7.4. Duration Analysis" if language == "en" else "### 7.4. Análisis de Duración"),
        new_code_cell(
            "duration_minutes = df['duration_s'] / 60\n"
            "\n"
            "dur_stats = pd.DataFrame({\n"
            "    'Statistic': ['Average (min)', 'Minimum (s)', 'Maximum (s)', 'Median (s)', 'Q1 (min)', 'Q3 (min)'],\n"
            "    'Value': [f'{duration_minutes.mean():.1f}', f'{df[\"duration_s\"].min()}', f'{df[\"duration_s\"].max()}', f'{df[\"duration_s\"].median()}', f'{duration_minutes.quantile(0.25):.1f}', f'{duration_minutes.quantile(0.75):.1f}']\n"
            "})\n"
            "display(dur_stats)\n"
            "\n"
            "fig, axes = plt.subplots(1, 2, figsize=(14, 5))\n"
            "fig.patch.set_facecolor(YT_BG)\n"
            "\n"
            "# Histogram\n"
            "ax1 = axes[0]\n"
            "ax1.set_facecolor(YT_BG)\n"
            "n, bins, patches = ax1.hist(duration_minutes, bins=15, edgecolor='white', alpha=0.8, density=True, color=YT_RED)\n"
            "kde = gaussian_kde(duration_minutes)\n"
            "x = np.linspace(duration_minutes.min(), duration_minutes.max(), 100)\n"
            "ax1.plot(x, kde(x), color=YT_DARK_GREY, linewidth=2, label='Density')\n"
            "ax1.axvline(duration_minutes.mean(), color=YT_DARK_GREY, linestyle='--', linewidth=1.5, label=f'Mean: {duration_minutes.mean():.1f} min')\n"
            "ax1.set_xlabel('Duration (minutes)', fontsize=11, color=YT_TEXT)\n"
            "ax1.set_ylabel('Density', fontsize=11, color=YT_TEXT)\n"
            "ax1.set_title('Duration Distribution', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "ax1.legend(loc='upper right', fontsize=9)\n"
            "\n"
            "# Boxplot\n"
            "ax2 = axes[1]\n"
            "ax2.set_facecolor(YT_BG)\n"
            "bp = ax2.boxplot(\n"
            "    duration_minutes, vert=False, patch_artist=True, widths=0.6, \n"
            "    boxprops=dict(facecolor=YT_RED, color=YT_DARK_GREY), \n"
            "    whiskerprops=dict(color=YT_DARK_GREY), capprops=dict(color=YT_DARK_GREY), \n"
            "    medianprops=dict(color='white', linewidth=2), \n"
            "    flierprops=dict(marker='o', markerfacecolor=YT_RED, markersize=4, alpha=0.5, markeredgecolor='none')\n"
            ")\n"
            "ax2.set_yticks([1]); ax2.set_yticklabels(['Duration'], fontsize=11, color=YT_TEXT)\n"
            "ax2.set_xlabel('Duration (minutes)', fontsize=11, color=YT_TEXT)\n"
            "ax2.set_title('Key Statistics', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "\n"
            "for ax in axes:\n"
            "    style_axes(ax, grid_axis='x')\n"
            "    ax.grid(True, color=YT_GRID, linestyle='--', alpha=0.5)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        ),

        # ----------------------------------------------------------------------
        # 7.5 Channel Type Distribution
        # ----------------------------------------------------------------------
        new_markdown_cell("### 7.5. Channel Type Distribution" if language == "en" else "### 7.5. Distribución por Tipo de Canal"),
        new_code_cell(
            "channel_counts = df['channel_type'].value_counts()\n"
            "ch_df = pd.DataFrame({'Channel Type': channel_counts.index, 'Count': channel_counts.values})\n"
            "ch_df['Percentage'] = (ch_df['Count'] / len(df) * 100).round(1).astype(str) + '%'\n"
            "display(ch_df)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(10, 5))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "\n"
            "bars = ax.barh(channel_counts.index, channel_counts.values, color=YT_RED, edgecolor='none', height=BAR_HEIGHT)\n"
            "\n"
            "ax.set_xlabel('Number of Songs', fontsize=11, color=YT_TEXT)\n"
            "ax.set_title('Channel Type Distribution', fontsize=TITLE_FONT_SIZE, color=YT_TEXT, loc='center', pad=20)\n"
            "\n"
            "style_axes(ax, grid_axis='x')\n"
            "add_bar_labels(ax, fmt='{:.0f}', horizontal=True)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        ),
    ]
