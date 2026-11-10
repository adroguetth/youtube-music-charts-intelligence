"""
Builders - Notebook Cell Constructors per Section
============================================================================
One builder per report section. Each builder receives the enriched
DataFrame, the reporting period and the target language, and returns a
list of `nbformat` cells ready to be appended to the notebook.

Builder contract
----------------
    builder(df, period, language) -> list[nbformat.cells]

- `df`: enriched DataFrame for the period (already validated by `core.db`).
- `period`: `core.periods.Period` instance.
- `language`: ``"en"`` or ``"es"``.

Responsibilities
----------------
- Produce the markdown headings and code cells for each section.
- Keep the visual output identical to the previous monolithic generator.

Notes
-----
- Builders do not aggregate beyond trivial pandas calls. All metrics come
  from `core.metrics`, so the numbers match across the notebook, the
  dashboard and any future consumer.
- Builders do not print or log. They build cells. Logging happens in
  `main.py`.
- Code cells reference the names imported in the notebook setup cell
  (`general_stats`, `genre_stats`, `top_songs`, ...). The setup cell is
  emitted by `builders.build_setup` and is always the first code cell in
  the notebook. If you rename a metric function, update both the setup
  cell and the builder that calls it.
- AI-generated insights (v2.0) will be injected by
  `report.notebook.generate_notebook` between a section's cells and the
  next section's header. No builder needs to change for that.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import pandas as pd
from nbformat.v4 import new_code_cell, new_markdown_cell

from ..core.metrics import (
    collaborations as metrics_collaborations,
    general_stats as metrics_general_stats,
    genre_stats as metrics_genre_stats,
    top_countries as metrics_top_countries,
    top_countries_by_likes as metrics_top_countries_by_likes,
    top_songs as metrics_top_songs,
    video_metrics as metrics_video_metrics,
)
from .titles import section_title


# ============================================================================
# SETUP CELL (emitted once, before any section)
# ============================================================================
SETUP_CODE = """\
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import squarify

from scipy.stats import gaussian_kde

plt.rcParams["figure.figsize"] = (12, 6)
plt.rcParams["font.size"] = 12
plt.rcParams["figure.dpi"] = 100

YT_RED = "#FF0000"
YT_RED_DARK = "#CC0000"
YT_BG = "#FFFFFF"
YT_SURFACE = "#F9F9F9"
YT_TEXT = "#0F0F0F"
YT_GRAY = "#606060"
YT_GRID = "#E5E5E5"


def format_number(x):
    if pd.isna(x):
        return "N/A"
    if x >= 1_000_000_000:
        return f"{x / 1_000_000_000:.1f}B"
    if x >= 1_000_000:
        return f"{x / 1_000_000:.1f}M"
    if x >= 1_000:
        return f"{x / 1_000:.1f}K"
    return f"{x:,.0f}"


DB_PATH = Path("../../charts_archive/3_enrich-chart-data/{db_filename}")
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("SELECT * FROM enriched_songs", conn)
conn.close()

df["upload_date"] = pd.to_datetime(df["upload_date"], errors="coerce")
df["upload_quarter"] = df["upload_date"].dt.quarter
df["engagement"] = np.where(
    df["views"] > 0, (df["likes"] / df["views"] * 100).round(2), 0.0
)
"""


def build_setup(period, language: str) -> list:
    """
    Emit the setup cell: imports, palette, helpers and data loading.

    This cell is not tied to a report section. It is prepended by
    `report.notebook.generate_notebook` before the first section.
    """
    db_filename = f"youtube_charts_{period.label}_enriched.db"
    code = SETUP_CODE.format(db_filename=db_filename)
    return [new_code_cell(code)]


# ============================================================================
# SECTION 1 - INTRODUCTION
# ============================================================================
def build_intro(df: pd.DataFrame, period, language: str) -> list:
    """Intro section: title and period metadata. No AI in v1.0."""
    if language == "en":
        meta = (
            f"**Week:** {period.label} | "
            f"**Period:** {period.start} → {period.end} | "
            f"**Days:** {period.n_days}"
        )
    else:
        meta = (
            f"**Semana:** {period.label} | "
            f"**Periodo:** {period.start} → {period.end} | "
            f"**Días:** {period.n_days}"
        )
    return [
        new_markdown_cell(section_title("intro", language)),
        new_markdown_cell(meta),
    ]


# ============================================================================
# SECTION 2 - GENERAL STATISTICS
# ============================================================================
def build_general_stats(df: pd.DataFrame, period, language: str) -> list:
    """General statistics section: headline counters."""
    return [
        new_markdown_cell(section_title("general_stats", language)),
        new_code_cell(
            "stats = general_stats(df)\n"
            "display(pd.DataFrame([stats]))"
        ),
    ]


# ============================================================================
# SECTION 3 - COUNTRY ANALYSIS
# ============================================================================
def build_countries(df: pd.DataFrame, period, language: str) -> list:
    """Country section: top by songs, top by likes, top songs per country."""
    return [
        new_markdown_cell(section_title("countries", language)),
        new_code_cell(
            "# Top 10 countries by song count\n"
            "top_countries(df, n=10)"
        ),
        new_code_cell(
            "# Top 10 countries by total likes\n"
            "top_countries_by_likes(df, n=10)"
        ),
        new_code_cell(
            "# Top 5 songs by country (top 10 countries)\n"
            "for country in df['artist_country'].value_counts().head(10).index:\n"
            "    print(f'\\n{country}:')\n"
            "    display(top_songs_by_country(df, country, metric='views', n=5))"
        ),
    ]


# ============================================================================
# SECTION 4 - GENRE ANALYSIS
# ============================================================================
def build_genre_analysis(df: pd.DataFrame, period, language: str) -> list:
    """Genre section: distribution treemap and engagement ranking."""
    return [
        new_markdown_cell(section_title("genre_analysis", language)),
        new_code_cell(
            "# Genre distribution treemap (top 15 genres)\n"
            "gs = genre_stats(df).head(15)\n"
            "sizes = gs['total_songs'].values\n"
            "labels = [\n"
            "    f\"{g}\\n{format_number(s)}\"\n"
            "    for g, s in zip(gs['macro_genre'], gs['total_songs'])\n"
            "]\n"
            "colors = plt.cm.Reds(np.linspace(0.3, 0.9, len(sizes)))\n"
            "fig, ax = plt.subplots(figsize=(14, 8))\n"
            "squarify.plot(\n"
            "    sizes=sizes, label=labels, alpha=0.9, color=colors,\n"
            "    text_kwargs={'fontsize': 10, 'fontweight': 'bold', 'color': 'white'},\n"
            "    ax=ax,\n"
            ")\n"
            "ax.set_title('Genre Distribution by Song Count', fontweight='bold')\n"
            "ax.axis('off')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        ),
        new_code_cell(
            "# Engagement rate by genre (top 10)\n"
            "gs = genre_stats(df).sort_values('engagement_rate', ascending=False).head(10)\n"
            "fig, ax = plt.subplots(figsize=(10, 6))\n"
            "colors = plt.cm.Reds(np.linspace(0.4, 1, len(gs)))[::-1]\n"
            "ax.barh(gs['macro_genre'], gs['engagement_rate'], color=colors, height=0.65)\n"
            "ax.invert_yaxis()\n"
            "ax.set_xlabel('Engagement Rate (%)')\n"
            "ax.set_title('Top 10 Genres by Engagement Rate', fontweight='bold')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        ),
    ]


# ============================================================================
# SECTION 5 - VIDEO METRICS
# ============================================================================
def build_video_metrics(df: pd.DataFrame, period, language: str) -> list:
    """Video section: aggregate table and average views/engagement bar chart."""
    return [
        new_markdown_cell(section_title("video_metrics", language)),
        new_code_cell(
            "vm = video_metrics(df)\n"
            "display(vm)"
        ),
        new_code_cell(
            "# Average views by video type\n"
            "fig, ax = plt.subplots(figsize=(8, 6))\n"
            "sns.barplot(data=vm, x='video_type', y='avg_views', ax=ax, color='#FC4B4C')\n"
            "ax.set_title('Average Views by Video Type', fontweight='bold')\n"
            "ax.set_ylabel('Average Views')\n"
            "ax.set_xlabel('Video Type')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        ),
        new_code_cell(
            "# Average engagement by video type\n"
            "fig, ax = plt.subplots(figsize=(8, 6))\n"
            "sns.barplot(data=vm, x='video_type', y='avg_engagement', ax=ax, color='#FC4B4C')\n"
            "ax.set_title('Average Engagement by Video Type', fontweight='bold')\n"
            "ax.set_ylabel('Engagement (%)')\n"
            "ax.set_xlabel('Video Type')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        ),
    ]


# ============================================================================
# SECTION 6 - SONG METRICS
# ============================================================================
def build_top_songs(df: pd.DataFrame, period, language: str) -> list:
    """Song section: top 10 by views, likes and engagement."""
    return [
        new_markdown_cell(section_title("top_songs", language)),
        new_code_cell(
            "# Top 10 songs by views\n"
            "display(top_songs(df, metric='views', n=10))"
        ),
        new_code_cell(
            "# Top 10 songs by likes\n"
            "display(top_songs(df, metric='likes', n=10))"
        ),
        new_code_cell(
            "# Top 10 songs by engagement\n"
            "display(top_songs(df, metric='engagement', n=10))"
        ),
    ]


# ============================================================================
# SECTION 7 - COLLABORATIONS
# ============================================================================
def build_collaborations(df: pd.DataFrame, period, language: str) -> list:
    """Collaborations section: solo vs collab table and scatter plots."""
    return [
        new_markdown_cell(section_title("collaborations", language)),
        new_code_cell(
            "display(collaborations(df))"
        ),
        new_code_cell(
            "# Views vs number of artists\n"
            "fig, axes = plt.subplots(1, 2, figsize=(14, 6))\n"
            "sns.scatterplot(\n"
            "    data=df, x='artist_count', y='views', hue='is_collaboration',\n"
            "    palette={0: '#282828', 1: 'red'}, ax=axes[0], alpha=0.6,\n"
            ")\n"
            "axes[0].set_title('Views vs Number of Artists', fontweight='bold')\n"
            "sns.scatterplot(\n"
            "    data=df, x='artist_count', y='engagement', hue='is_collaboration',\n"
            "    palette={0: '#282828', 1: 'red'}, ax=axes[1], alpha=0.6,\n"
            ")\n"
            "axes[1].set_title('Engagement vs Number of Artists', fontweight='bold')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        ),
    ]


# ============================================================================
# SECTION 8 - EXECUTIVE SUMMARY
# ============================================================================
def build_exec_summary(df: pd.DataFrame, period, language: str) -> list:
    """Executive summary section. AI text in v2.0; numeric recap in v1.0."""
    return [
        new_markdown_cell(section_title("exec_summary", language)),
        new_code_cell(
            "stats = general_stats(df)\n"
            "print(f\"Songs: {stats['total_songs']}\")\n"
            "print(f\"Countries: {stats['unique_countries']}\")\n"
            "print(f\"Genres: {stats['unique_genres']}\")\n"
            "print(f\"Total views: {format_number(stats['total_views'])}\")\n"
            "print(f\"Total likes: {format_number(stats['total_likes'])}\")\n"
            "print(f\"Avg engagement: {stats['avg_engagement']:.2f}%\")"
        ),
    ]
