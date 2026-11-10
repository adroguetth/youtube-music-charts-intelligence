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
- Imports are absolute (`from core.metrics import ...`,
  `from report.titles import ...`), not relative. In script mode,
  `core` and `report` are top-level modules on `sys.path`.
- `SETUP_CODE` contains Python f-strings with `{}` placeholders. It must
  NOT be processed with `str.format()`, because `format` would try to
  interpret those braces as format fields and raise
  ``KeyError: 'x / 1_000_000_000'``. The DB filename is injected with
  `str.replace("__DB_FILENAME__", ...)` instead, which does not touch
  braces.
- Code cells reference metric functions by their plain names
  (`general_stats`, `genre_stats`, `top_songs`, ...). Those names are
  made available in the notebook's namespace by `SETUP_CODE`.
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

from core.metrics import (
    collaborations as metrics_collaborations,
    general_stats as metrics_general_stats,
    genre_stats as metrics_genre_stats,
    top_countries as metrics_top_countries,
    top_countries_by_likes as metrics_top_countries_by_likes,
    top_songs as metrics_top_songs,
    video_metrics as metrics_video_metrics,
)
from report.titles import section_title


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


# Metric functions: try to import from the package, fall back to inline.
try:
    from core.metrics import (
        collaborations,
        general_stats,
        genre_stats,
        top_countries,
        top_countries_by_likes,
        top_songs,
        top_songs_by_country,
        video_metrics,
    )
except ImportError:
    # Self-contained fallback so the notebook runs when moved or opened
    # outside the repository (e.g. Colab).
    def general_stats(df):
        return {
            "total_songs": int(len(df)),
            "unique_countries": int(df["artist_country"].nunique()),
            "unique_genres": int(df["macro_genre"].nunique()),
            "total_views": int(df["views"].sum()),
            "total_likes": int(df["likes"].sum()),
            "total_comments": int(df["comment_count"].sum()),
            "avg_views": float(df["views"].mean()),
            "avg_likes": float(df["likes"].mean()),
            "avg_engagement": float(df["engagement"].mean()),
        }

    def top_countries(df, n=10):
        return (
            df.groupby("artist_country")
            .agg(total_songs=("rank", "count"), total_views=("views", "sum"))
            .reset_index()
            .sort_values("total_songs", ascending=False)
            .head(n)
            .reset_index(drop=True)
        )

    def top_countries_by_likes(df, n=10):
        return (
            df.groupby("artist_country")["likes"]
            .sum()
            .reset_index()
            .rename(columns={"likes": "total_likes"})
            .sort_values("total_likes", ascending=False)
            .head(n)
            .reset_index(drop=True)
        )

    def top_songs_by_country(df, country, metric="views", n=5):
        cols = ["track_name", "artist_names", "views", "likes", "engagement"]
        return (
            df[df["artist_country"] == country]
            .nlargest(n, metric)[cols]
            .reset_index(drop=True)
        )

    def genre_stats(df):
        out = (
            df.groupby("macro_genre")
            .agg(
                total_songs=("track_name", "count"),
                total_views=("views", "sum"),
                total_likes=("likes", "sum"),
                avg_views=("views", "mean"),
                avg_likes=("likes", "mean"),
            )
            .reset_index()
        )
        out["engagement_rate"] = (
            out["total_likes"] / out["total_views"].replace(0, pd.NA) * 100
        ).fillna(0).round(2)
        return out.sort_values("total_songs", ascending=False).reset_index(drop=True)

    def video_metrics(df):
        flags = {
            "Official": "is_official_video",
            "Lyric": "is_lyric_video",
            "Live": "is_live_performance",
        }
        rows = []
        total = len(df)
        for label, flag in flags.items():
            subset = df[df[flag] == 1]
            rows.append({
                "video_type": label,
                "count": int(len(subset)),
                "pct": float(len(subset) / total * 100) if total else 0.0,
                "avg_views": float(subset["views"].mean()) if len(subset) else 0.0,
                "avg_engagement": float(subset["engagement"].mean()) if len(subset) else 0.0,
            })
        return pd.DataFrame(rows)

    def top_songs(df, metric="views", n=10):
        cols = ["rank", "track_name", "artist_names", metric, "artist_country"]
        return df.nlargest(n, metric)[cols].reset_index(drop=True)

    def collaborations(df):
        grouped = (
            df.groupby("is_collaboration")
            .agg(
                count=("track_name", "count"),
                avg_views=("views", "mean"),
                avg_engagement=("engagement", "mean"),
            )
            .reset_index()
        )
        grouped["is_collaboration"] = grouped["is_collaboration"].map(
            {0: "Solo", 1: "Collaboration"}
        )
        return grouped


DB_PATH = Path("../../charts_archive/3_enrich-chart-data/__DB_FILENAME__")
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
    Emit the setup cell: imports, palette, metric functions and data loading.

    This cell is not tied to a report section. It is prepended by
    `report.notebook.generate_notebook` before the first section.

    Notes
    -----
    The DB filename is injected with `str.replace`, not `str.format`,
    because `SETUP_CODE` contains Python f-strings whose `{}` braces would
    otherwise be interpreted as `str.format` fields.
    """
    db_filename = f"youtube_charts_{period.label}_enriched.db"
    code = SETUP_CODE.replace("__DB_FILENAME__", db_filename)
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
