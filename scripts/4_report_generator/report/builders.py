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
- Keep the visual output clean, modern, and standardized.
- Use `display()` for tabular data and charts, avoiding plain text prints.

Notes
-----
- All code, comments, and chart labels are strictly in English.
- Visual style: Arial/Helvetica font, pure white background, subtle grey
  borders (0.8 width), solid soft red (#FC4B4B) for single-series charts,
  and a standardized categorical palette for multi-series charts.
- SETUP_CODE defines all metric functions inline to ensure the notebook
  is self-contained and runs reliably in any environment (CI, Colab, etc.)
  without requiring the repository to be installed as a package.

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
from IPython.display import display, Markdown, HTML
from matplotlib.ticker import FuncFormatter

# ==============================================================================
# GLOBAL VISUAL CONFIGURATION
# ==============================================================================
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
plt.rcParams["figure.figsize"] = (12, 6)
plt.rcParams["font.size"] = 11
plt.rcParams["axes.titlesize"] = 18
plt.rcParams["axes.titleweight"] = "normal"
plt.rcParams["axes.labelsize"] = 11
plt.rcParams["figure.dpi"] = 110

# Standardized color palette
YT_RED = "#FC4B4B"          # Soft Red for main data
YT_DARK_GREY = "#282828"    # Dark Grey for comparisons
YT_TEXT = "#000000"         # Black for axis labels and text
YT_GRAY = "#606060"         # Medium Grey for secondary text
YT_GRID = "#E5E5E5"         # Light Grey for grid lines
YT_BG = "#FFFFFF"           # Pure White background
BORDER_COLOR = "#A0A0A0"    # Subtle grey for chart borders

# Categorical palette for multi-series charts
CATEGORICAL_PALETTE = ["#FC4B4B", "#282828", "#4A90E2", "#F5A623", "#50E3C2"]

# Format global to avoid scientific notation in DataFrames
pd.set_option('display.float_format', lambda x: f'{x:,.3f}')

def format_number(x):
    if pd.isna(x): return "N/A"
    if x >= 1_000_000_000: return f"{x / 1_000_000_000:.1f}B"
    if x >= 1_000_000: return f"{x / 1_000_000:.1f}M"
    if x >= 1_000: return f"{x / 1_000:.1f}K"
    return f"{x:,.0f}"

def format_axis_millions(x, pos):
    if x >= 1_000_000: return f'{x/1_000_000:.0f}M'
    if x >= 1_000: return f'{x/1_000:.0f}K'
    return f'{x:.0f}'

def get_continent(country):
    continents = {
        'North America': ['United States', 'Mexico', 'Canada', 'Puerto Rico'],
        'South America': ['Brazil', 'Argentina', 'Colombia', 'Chile', 'Peru', 'Venezuela'],
        'Europe': ['United Kingdom', 'Sweden', 'Germany', 'France', 'Spain', 'Italy', 'Netherlands', 'Turkey'],
        'Asia': ['India', 'South Korea', 'Japan', 'China', 'Indonesia', 'Pakistan', 'Philippines', 'Thailand', 'Vietnam'],
        'Africa': ['Nigeria', 'South Africa', 'Kenya', 'Ghana'],
        'Oceania': ['Australia', 'New Zealand'],
        'Middle East': ['Israel', 'UAE', 'Saudi Arabia']
    }
    for continent, countries in continents.items():
        if country in countries: return continent
    return 'Other'

# ==============================================================================
# METRIC FUNCTIONS (Inline for self-containment)
# ==============================================================================
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
df["engagement"] = np.where(df["views"] > 0, (df["likes"] / df["views"] * 100).round(2), 0.0)
df["continent"] = df["artist_country"].apply(get_continent)
"""


def build_setup(period, language: str) -> list:
    """Emit the setup cell."""
    db_filename = f"youtube_charts_{period.label}_enriched.db"
    code = SETUP_CODE.replace("__DB_FILENAME__", db_filename)
    return [new_code_cell(code)]


# ============================================================================
# SECTION 1 - INTRODUCTION
# ============================================================================
def build_intro(df: pd.DataFrame, period, language: str) -> list:
    if language == "en":
        meta = f"**Week:** {period.label} | **Period:** {period.start} → {period.end} | **Days:** {period.n_days}"
    else:
        meta = f"**Semana:** {period.label} | **Periodo:** {period.start} → {period.end} | **Días:** {period.n_days}"
    return [new_markdown_cell(section_title("intro", language)), new_markdown_cell(meta)]


# ============================================================================
# SECTION 2 - GENERAL STATISTICS
# ============================================================================
def build_general_stats(df: pd.DataFrame, period, language: str) -> list:
    return [
        new_markdown_cell(section_title("general_stats", language)),
        new_code_cell("stats = general_stats(df)\ndisplay(pd.DataFrame(list(stats.items()), columns=['Metric', 'Value']))"),
    ]


# ============================================================================
# SECTION 3 - CONTINENT ANALYSIS
# ============================================================================
def build_continents(df: pd.DataFrame, period, language: str) -> list:
    return [
        new_markdown_cell(section_title("continents", language)),
        new_code_cell(
            "continent_stats = df.groupby('continent').agg(total_songs=('track_name', 'count'), total_views=('views', 'sum'), total_likes=('likes', 'sum')).reset_index().sort_values('total_songs', ascending=False)\n"
            "display(continent_stats)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(10, 6))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "bars = ax.barh(continent_stats['continent'], continent_stats['total_songs'], color=YT_RED, edgecolor='none', height=0.65)\n"
            "ax.set_xlabel('Number of Songs', fontsize=11, color=YT_TEXT)\n"
            "ax.set_title('Song Distribution by Continent', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.invert_yaxis()\n"
            "for spine in ax.spines.values(): spine.set_color(BORDER_COLOR); spine.set_linewidth(0.8)\n"
            "ax.tick_params(colors=YT_TEXT, labelsize=11)\n"
            "ax.xaxis.grid(True, color=YT_GRID, linestyle='--', alpha=0.7)\n"
            "for bar, val in zip(bars, continent_stats['total_songs']): ax.text(val + 0.5, bar.get_y() + bar.get_height()/2, f'{int(val)}', va='center', fontsize=11, color=YT_TEXT)\n"
            "plt.tight_layout(); plt.show()"
        ),
    ]


# ============================================================================
# SECTION 4 - COUNTRY ANALYSIS
# ============================================================================
def build_countries(df: pd.DataFrame, period, language: str) -> list:
    return [
        new_markdown_cell(section_title("countries", language)),
        
        new_markdown_cell("### 4.1. Top Countries by Song Count" if language == "en" else "### 4.1. Top Países por Cantidad de Canciones"),
        new_code_cell(
            "top_countries = (df.groupby('artist_country').agg(total_songs=('rank', 'count'), total_views=('views', 'sum')).reset_index().sort_values('total_songs', ascending=False).head(10))\n"
            "total = top_countries['total_songs'].sum()\n"
            "top_countries['percentage'] = (top_countries['total_songs'] / total * 100).round(2)\n"
            "display(top_countries)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(10, 6))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "bars = ax.barh(top_countries['artist_country'], top_countries['total_songs'], color=YT_RED, edgecolor='none', height=0.65)\n"
            "ax.set_xlabel('Number of Songs', fontsize=11, color=YT_TEXT)\n"
            "ax.set_title('Top 10 Countries by Song Count', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.invert_yaxis()\n"
            "for spine in ax.spines.values(): spine.set_color(BORDER_COLOR); spine.set_linewidth(0.8)\n"
            "ax.tick_params(colors=YT_TEXT, labelsize=11)\n"
            "ax.xaxis.grid(True, color=YT_GRID, linestyle='--', alpha=0.7)\n"
            "for bar, val in zip(bars, top_countries['total_songs']): ax.text(val + 0.5, bar.get_y() + bar.get_height()/2, f'{int(val)}', va='center', fontsize=11, color=YT_TEXT)\n"
            "plt.tight_layout(); plt.show()"
        ),
        
        new_markdown_cell("### 4.2. Top Countries by Total Likes" if language == "en" else "### 4.2. Top Países por Total de Likes"),
        new_code_cell(
            "top_likes = (df.groupby('artist_country')['likes'].sum().reset_index().rename(columns={'likes': 'total_likes'}).sort_values('total_likes', ascending=False).head(10))\n"
            "def format_likes(x): return f'{x/1_000_000:.1f}M' if x >= 1_000_000 else (f'{x/1_000:.1f}K' if x >= 1_000 else str(x))\n"
            "top_likes['total_likes_fmt'] = top_likes['total_likes'].apply(format_likes)\n"
            "display(top_likes[['artist_country', 'total_likes_fmt']])\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(10, 6))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "bars = ax.barh(top_likes['artist_country'], top_likes['total_likes'], color=YT_RED, edgecolor='none', height=0.65)\n"
            "ax.set_xlabel('Total Likes', fontsize=11, color=YT_TEXT)\n"
            "ax.set_title('Top 10 Countries by Total Likes', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.invert_yaxis()\n"
            "for spine in ax.spines.values(): spine.set_color(BORDER_COLOR); spine.set_linewidth(0.8)\n"
            "ax.tick_params(colors=YT_TEXT, labelsize=11)\n"
            "ax.xaxis.grid(True, color=YT_GRID, linestyle='--', alpha=0.7)\n"
            "ax.xaxis.set_major_formatter(FuncFormatter(format_axis_millions))\n"
            "for bar, val in zip(bars, top_likes['total_likes']): ax.text(val + (val*0.02), bar.get_y() + bar.get_height()/2, format_likes(val), va='center', fontsize=11, color=YT_TEXT)\n"
            "plt.tight_layout(); plt.show()"
        ),
        
        new_markdown_cell("### 4.3. Top 5 Songs by Top 5 Countries" if language == "en" else "### 4.3. Top 5 Canciones por los 5 Primeros Países"),
        new_code_cell(
            "top_countries_list = df['artist_country'].value_counts().head(5).index.tolist()\n"
            "for country in top_countries_list:\n"
            "    display(HTML(f'<hr style=\"border: 1px solid {YT_GRID}; margin: 20px 0;\">'))\n"
            "    display(HTML(f'<h4 style=\"color: {YT_TEXT}; margin-bottom: 10px;\">{country}</h4>'))\n"
            "    df_country = df[df['artist_country'] == country]\n"
            "    top_views = df_country.nlargest(5, 'views')[['track_name', 'artist_names', 'views', 'likes', 'engagement']].copy()\n"
            "    top_views['views'] = top_views['views'].apply(format_number); top_views['likes'] = top_views['likes'].apply(format_number)\n"
            "    display(HTML('<b>Top 5 by views:</b>')); display(top_views)\n"
            "    top_likes_country = df_country.nlargest(5, 'likes')[['track_name', 'artist_names', 'views', 'likes', 'engagement']].copy()\n"
            "    top_likes_country['views'] = top_likes_country['views'].apply(format_number); top_likes_country['likes'] = top_likes_country['likes'].apply(format_number)\n"
            "    display(HTML('<b>Top 5 by likes:</b>')); display(top_likes_country)\n"
            "display(HTML(f'<hr style=\"border: 1px solid {YT_GRID}; margin: 20px 0;\">'))"
        ),
    ]


# ============================================================================
# SECTION 5 - GENRE ANALYSIS
# ============================================================================
def build_genre_analysis(df: pd.DataFrame, period, language: str) -> list:
    return [
        new_markdown_cell(section_title("genre_analysis", language)),
        new_code_cell(
            "genre_stats = (df.groupby('macro_genre').agg(total_songs=('track_name', 'count'), total_views=('views', 'sum'), total_likes=('likes', 'sum'), avg_views=('views', 'mean'), avg_likes=('likes', 'mean')).reset_index().sort_values('total_songs', ascending=False))\n"
            "genre_stats['engagement_rate'] = (genre_stats['total_likes'] / genre_stats['total_views'] * 100).round(2).fillna(0)\n"
            "display(genre_stats.head(10)[['macro_genre', 'total_songs', 'engagement_rate']])"
        ),
        
        new_markdown_cell("### 5.2. Genre Distribution Treemap" if language == "en" else "### 5.2. Treemap de Distribución de Géneros"),
        new_code_cell(
            "treemap_data = genre_stats.head(15).copy()\n"
            "sizes = treemap_data['total_songs'].values\n"
            "colors = plt.cm.Reds(np.linspace(0.3, 0.9, len(sizes)))\n"
            "fig, ax = plt.subplots(figsize=(14, 8))\n"
            "ax.set_facecolor(YT_BG); fig.patch.set_facecolor(YT_BG)\n"
            "rects = squarify.normalize_sizes(sizes, 14, 8)\n"
            "rects = squarify.squarify(rects, 0, 0, 14, 8)\n"
            "for i, (rect, color) in enumerate(zip(rects, colors)):\n"
            "    luminance = 0.299*color[0] + 0.587*color[1] + 0.114*color[2]\n"
            "    text_color = 'white' if luminance < 0.6 else 'black'\n"
            "    rect_obj = plt.Rectangle((rect['x'], rect['y']), rect['dx'], rect['dy'], facecolor=color, edgecolor='white', linewidth=1.5)\n"
            "    ax.add_patch(rect_obj)\n"
            "    label = f\"{treemap_data['macro_genre'].iloc[i]}\\n{format_number(treemap_data['total_songs'].iloc[i])}\"\n"
            "    ax.text(rect['x'] + rect['dx']/2, rect['y'] + rect['dy']/2, label, ha='center', va='center', fontsize=11, color=text_color)\n"
            "ax.set_xlim(0, 14); ax.set_ylim(0, 8)\n"
            "ax.set_title('Genre Distribution by Song Count', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.axis('off')\n"
            "plt.tight_layout(); plt.show()"
        ),
        
        new_markdown_cell("### 5.3. Engagement Rate by Genre" if language == "en" else "### 5.3. Tasa de Engagement por Género"),
        new_code_cell(
            "engagement_chart = genre_stats.sort_values('engagement_rate', ascending=False).head(10)\n"
            "fig, ax = plt.subplots(figsize=(10, 6))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "bars = ax.barh(engagement_chart['macro_genre'], engagement_chart['engagement_rate'], color=YT_RED, edgecolor='none', height=0.65)\n"
            "ax.set_xlabel('Engagement Rate (%)', fontsize=11, color=YT_TEXT)\n"
            "ax.set_title('Top 10 Genres by Engagement Rate', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.invert_yaxis()\n"
            "for spine in ax.spines.values(): spine.set_color(BORDER_COLOR); spine.set_linewidth(0.8)\n"
            "ax.tick_params(colors=YT_TEXT, labelsize=11)\n"
            "ax.xaxis.grid(True, color=YT_GRID, linestyle='--', alpha=0.7)\n"
            "for bar, val in zip(bars, engagement_chart['engagement_rate']): ax.text(val + 0.2, bar.get_y() + bar.get_height()/2, f'{val:.1f}%', va='center', fontsize=11, color=YT_TEXT)\n"
            "avg_engagement = genre_stats['engagement_rate'].mean()\n"
            "ax.axvline(x=avg_engagement, color=YT_DARK_GREY, linestyle='--', linewidth=1.5, alpha=0.9)\n"
            "ax.text(avg_engagement + 0.1, len(engagement_chart) - 0.5, f'Average: {avg_engagement:.1f}%', fontsize=10, color=YT_DARK_GREY)\n"
            "plt.tight_layout(); plt.show()\n"
            "stats_summary = pd.DataFrame({'Statistic': ['Average', 'Median', 'Max', 'Min'], 'Value': [avg_engagement, genre_stats['engagement_rate'].median(), genre_stats['engagement_rate'].max(), genre_stats['engagement_rate'].min()], 'Genre': ['', '', genre_stats.loc[genre_stats['engagement_rate'].idxmax(), 'macro_genre'], genre_stats.loc[genre_stats['engagement_rate'].idxmin(), 'macro_genre']]})\n"
            "display(stats_summary)"
        ),
        
        new_markdown_cell("### 5.4. Country-Genre Distribution Heatmap" if language == "en" else "### 5.4. Heatmap País-Género"),
        new_code_cell(
            "df_analysis = df[~df['artist_country'].isin(['Multi-country', 'Unknown'])]\n"
            "if not df_analysis.empty:\n"
            "    matrix = pd.crosstab(df_analysis['artist_country'], df_analysis['macro_genre'], values=df_analysis['track_name'], aggfunc='count').fillna(0)\n"
            "    top_countries_h = matrix.sum(axis=1).sort_values(ascending=False).head(12).index\n"
            "    top_genres = [g for g in genre_stats.nlargest(10, 'total_songs')['macro_genre'].tolist() if g in matrix.columns]\n"
            "    if len(top_countries_h) > 0 and len(top_genres) > 0:\n"
            "        matrix_heatmap = matrix.loc[top_countries_h, top_genres].astype(int)\n"
            "        fig, ax = plt.subplots(figsize=(12, 8))\n"
            "        fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "        sns.heatmap(matrix_heatmap, annot=True, fmt='d', cmap='Reds', xticklabels=True, yticklabels=True, linewidths=0.5, linecolor='white', ax=ax)\n"
            "        ax.set_title('Country vs Genre Distribution', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "        ax.set_xlabel('Genre', fontsize=11, color=YT_TEXT)\n"
            "        ax.set_ylabel('Country', fontsize=11, color=YT_TEXT)\n"
            "        plt.xticks(rotation=45, ha='right'); plt.tight_layout(); plt.show()"
        ),
    ]


# ============================================================================
# SECTION 6 - SONG METRICS
# ============================================================================
def build_top_songs(df: pd.DataFrame, period, language: str) -> list:
    return [
        new_markdown_cell(section_title("top_songs", language)),
        new_markdown_cell("### 6.1. Top Songs by Views" if language == "en" else "### 6.1. Top Canciones por Vistas"),
        new_code_cell("display(df.nlargest(10, 'views')[['rank', 'track_name', 'artist_names', 'macro_genre', 'views', 'artist_country']])"),
        new_markdown_cell("### 6.2. Top Songs by Likes" if language == "en" else "### 6.2. Top Canciones por Likes"),
        new_code_cell("display(df.nlargest(10, 'likes')[['rank', 'track_name', 'artist_names', 'macro_genre', 'likes', 'artist_country']])"),
        new_markdown_cell("### 6.3. Top Songs by Engagement" if language == "en" else "### 6.3. Top Canciones por Engagement"),
        new_code_cell("display(df.nlargest(10, 'engagement')[['rank', 'track_name', 'artist_names', 'macro_genre', 'engagement', 'artist_country']])"),
    ]

# ============================================================================
# SECTION 7 - VIDEO METRICS
# ============================================================================
def build_video_metrics(df: pd.DataFrame, period, language: str) -> list:
    return [
        new_markdown_cell(section_title("video_metrics", language)),
        new_markdown_cell("### 7.1. Video Summary" if language == "en" else "### 7.1. Resumen de Video"),
        new_code_cell(
            "video_stats = {'Category': ['Official Videos', 'Lyric Videos', 'Live Performances', 'Collaborations'], 'Count': [df['is_official_video'].sum(), df['is_lyric_video'].sum(), df['is_live_performance'].sum(), df['is_collaboration'].sum()]}\n"
            "v_stats_df = pd.DataFrame(video_stats)\n"
            "v_stats_df['Percentage'] = (v_stats_df['Count'] / len(df) * 100).round(1).astype(str) + '%'\n"
            "display(v_stats_df)"
        ),
        new_markdown_cell("### 7.2. Views by Video Type" if language == "en" else "### 7.2. Vistas por Tipo de Video"),
        new_code_cell(
            "df_video = df.copy()\n"
            "conditions = [df_video['is_official_video'] == 1, df_video['is_lyric_video'] == 1, df_video['is_live_performance'] == 1]\n"
            "choices = ['Official', 'Lyric', 'Live']\n"
            "df_video['video_type'] = np.select(conditions, choices, default='Other')\n"
            "views_stats = df_video.groupby('video_type').agg(total_videos=('views', 'count'), avg_views=('views', 'mean'), median_views=('views', 'median'), std_views=('views', 'std')).round(2).reset_index()\n"
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
            "ax.set_title('Average Views by Video Type', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.set_xlabel('Average Views', fontsize=11, color=YT_TEXT)\n"
            "ax.set_ylabel('Video Type', fontsize=11, color=YT_TEXT)\n"
            "\n"
            "for spine in ax.spines.values(): \n"
            "    spine.set_color(BORDER_COLOR)\n"
            "    spine.set_linewidth(0.8)\n"
            "ax.tick_params(colors=YT_TEXT, labelsize=11)\n"
            "ax.xaxis.grid(True, color=YT_GRID, linestyle='--', alpha=0.7)\n"
            "ax.xaxis.set_major_formatter(FuncFormatter(format_axis_millions))\n"
            "\n"
            "for p in ax.patches:\n"
            "    width = p.get_width()\n"
            "    ax.text(width + (width*0.02), p.get_y() + p.get_height()/2, \n"
            "            f'{width/1_000_000:.1f}M', ha='left', va='center', fontsize=11, color=YT_TEXT)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        ),
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
            "ax.set_title('Average Engagement by Video Type', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "ax.set_xlabel('Engagement (%)', fontsize=11, color=YT_TEXT)\n"
            "ax.set_ylabel('Video Type', fontsize=11, color=YT_TEXT)\n"
            "\n"
            "for spine in ax.spines.values(): \n"
            "    spine.set_color(BORDER_COLOR)\n"
            "    spine.set_linewidth(0.8)\n"
            "ax.tick_params(colors=YT_TEXT, labelsize=11)\n"
            "ax.xaxis.grid(True, color=YT_GRID, linestyle='--', alpha=0.7)\n"
            "\n"
            "for p in ax.patches:\n"
            "    width = p.get_width()\n"
            "    ax.text(width + 0.1, p.get_y() + p.get_height()/2, \n"
            "            f'{width:.2f}%', ha='left', va='center', fontsize=11, color=YT_TEXT)\n"
            "\n"
            "plt.tight_layout(); plt.show()"
        ),
        new_markdown_cell("### 7.4. Duration Analysis" if language == "en" else "### 7.4. Análisis de Duración"),
        new_code_cell(
            "duration_minutes = df['duration_s'] / 60\n"
            "dur_stats = pd.DataFrame({'Statistic': ['Average (min)', 'Minimum (s)', 'Maximum (s)', 'Median (s)', 'Q1 (min)', 'Q3 (min)'], 'Value': [f'{duration_minutes.mean():.1f}', f'{df[\"duration_s\"].min()}', f'{df[\"duration_s\"].max()}', f'{df[\"duration_s\"].median()}', f'{duration_minutes.quantile(0.25):.1f}', f'{duration_minutes.quantile(0.75):.1f}']})\n"
            "display(dur_stats)\n"
            "fig, axes = plt.subplots(1, 2, figsize=(14, 5))\n"
            "fig.patch.set_facecolor(YT_BG)\n"
            "ax1 = axes[0]; ax1.set_facecolor(YT_BG)\n"
            "n, bins, patches = ax1.hist(duration_minutes, bins=15, edgecolor='white', alpha=0.8, density=True, color=YT_RED)\n"
            "kde = gaussian_kde(duration_minutes)\n"
            "x = np.linspace(duration_minutes.min(), duration_minutes.max(), 100)\n"
            "ax1.plot(x, kde(x), color=YT_DARK_GREY, linewidth=2, label='Density')\n"
            "ax1.axvline(duration_minutes.mean(), color=YT_DARK_GREY, linestyle='--', linewidth=1.5, label=f'Mean: {duration_minutes.mean():.1f} min')\n"
            "ax1.set_xlabel('Duration (minutes)', fontsize=11, color=YT_TEXT)\n"
            "ax1.set_ylabel('Density', fontsize=11, color=YT_TEXT)\n"
            "ax1.set_title('Duration Distribution', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "ax1.legend(loc='upper right', fontsize=9)\n"
            "ax2 = axes[1]; ax2.set_facecolor(YT_BG)\n"
            "bp = ax2.boxplot(duration_minutes, vert=False, patch_artist=True, widths=0.6, boxprops=dict(facecolor=YT_RED, color=YT_DARK_GREY), whiskerprops=dict(color=YT_DARK_GREY), capprops=dict(color=YT_DARK_GREY), medianprops=dict(color='white', linewidth=2), flierprops=dict(marker='o', markerfacecolor=YT_RED, markersize=4, alpha=0.5, markeredgecolor='none'))\n"
            "ax2.set_yticks([1]); ax2.set_yticklabels(['Duration'], fontsize=11, color=YT_TEXT)\n"
            "ax2.set_xlabel('Duration (minutes)', fontsize=11, color=YT_TEXT)\n"
            "ax2.set_title('Key Statistics', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "for ax in axes:\n"
            "    for spine in ax.spines.values(): spine.set_color(BORDER_COLOR); spine.set_linewidth(0.8)\n"
            "    ax.tick_params(colors=YT_TEXT, labelsize=11)\n"
            "    ax.grid(True, color=YT_GRID, linestyle='--', alpha=0.5)\n"
            "plt.tight_layout(); plt.show()"
        ),
        new_markdown_cell("### 7.5. Channel Type Distribution" if language == "en" else "### 7.5. Distribución por Tipo de Canal"),
        new_code_cell(
            "channel_counts = df['channel_type'].value_counts()\n"
            "ch_df = pd.DataFrame({'Channel Type': channel_counts.index, 'Count': channel_counts.values})\n"
            "ch_df['Percentage'] = (ch_df['Count'] / len(df) * 100).round(1).astype(str) + '%'\n"
            "display(ch_df)\n"
            "fig, ax = plt.subplots(figsize=(10, 5))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "bars = ax.barh(channel_counts.index, channel_counts.values, color=YT_RED, edgecolor='none', height=0.6)\n"
            "ax.set_xlabel('Number of Songs', fontsize=11, color=YT_TEXT)\n"
            "ax.set_title('Channel Type Distribution', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "for spine in ax.spines.values(): spine.set_color(BORDER_COLOR); spine.set_linewidth(0.8)\n"
            "ax.tick_params(colors=YT_TEXT, labelsize=11)\n"
            "ax.xaxis.grid(True, color=YT_GRID, linestyle='--', alpha=0.7)\n"
            "for bar, val in zip(bars, channel_counts.values): ax.text(val + 0.3, bar.get_y() + bar.get_height()/2, f'{val} ({val/len(df)*100:.1f}%)', va='center', fontsize=11, color=YT_TEXT)\n"
            "plt.tight_layout(); plt.show()"
        ),
    ]


# ============================================================================
# SECTION 8 - TEMPORAL ANALYSIS
# ============================================================================
def build_temporal_analysis(df: pd.DataFrame, period, language: str) -> list:
    return [
        new_markdown_cell(section_title("temporal_analysis", language)),
        new_code_cell(
            "top5_genres = genre_stats.nlargest(5, 'total_songs')['macro_genre'].tolist()\n"
            "df_temporal = df[df['macro_genre'].isin(top5_genres)].copy()\n"
            "temporal_views = df_temporal.groupby(['upload_quarter', 'macro_genre'])['views'].sum().reset_index()\n"
            "temporal_engagement = df_temporal.groupby(['upload_quarter', 'macro_genre'])['engagement'].mean().reset_index()"
        ),
        new_markdown_cell("### 8.1. Views Evolution by Quarter" if language == "en" else "### 8.1. Evolución de Vistas por Trimestre"),
        new_code_cell(
            "fig1, ax1 = plt.subplots(figsize=(12, 6))\n"
            "fig1.patch.set_facecolor(YT_BG); ax1.set_facecolor(YT_BG)\n"
            "sns.barplot(data=temporal_views, x='upload_quarter', y='views', hue='macro_genre', palette=CATEGORICAL_PALETTE, ax=ax1)\n"
            "ax1.set_title('Views Evolution by Quarter (Top 5 Genres)', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "ax1.set_xlabel('Release Quarter', fontsize=11, color=YT_TEXT)\n"
            "ax1.set_ylabel('Total Views', fontsize=11, color=YT_TEXT)\n"
            "for spine in ax1.spines.values(): spine.set_color(BORDER_COLOR); spine.set_linewidth(0.8)\n"
            "ax1.tick_params(colors=YT_TEXT, labelsize=11)\n"
            "ax1.yaxis.grid(True, color=YT_GRID, linestyle='--', alpha=0.7)\n"
            "ax1.yaxis.set_major_formatter(FuncFormatter(format_axis_millions))\n"
            "legend1 = ax1.get_legend()\n"
            "if legend1:\n"
            "    legend1.get_frame().set_edgecolor(YT_GRID); legend1.get_frame().set_linewidth(0.8)\n"
            "    for text in legend1.get_texts(): text.set_color(YT_TEXT)\n"
            "plt.tight_layout(); plt.show()"
        ),
        new_markdown_cell("### 8.2. Engagement Evolution by Quarter" if language == "en" else "### 8.2. Evolución del Engagement por Trimestre"),
        new_code_cell(
            "fig2, ax2 = plt.subplots(figsize=(12, 6))\n"
            "fig2.patch.set_facecolor(YT_BG); ax2.set_facecolor(YT_BG)\n"
            "sns.barplot(data=temporal_engagement, x='upload_quarter', y='engagement', hue='macro_genre', palette=CATEGORICAL_PALETTE, ax=ax2)\n"
            "ax2.set_title('Engagement Evolution by Quarter (Top 5 Genres)', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "ax2.set_xlabel('Release Quarter', fontsize=11, color=YT_TEXT)\n"
            "ax2.set_ylabel('Engagement (%)', fontsize=11, color=YT_TEXT)\n"
            "for spine in ax2.spines.values(): spine.set_color(BORDER_COLOR); spine.set_linewidth(0.8)\n"
            "ax2.tick_params(colors=YT_TEXT, labelsize=11)\n"
            "ax2.yaxis.grid(True, color=YT_GRID, linestyle='--', alpha=0.7)\n"
            "legend2 = ax2.get_legend()\n"
            "if legend2:\n"
            "    legend2.get_frame().set_edgecolor(YT_GRID); legend2.get_frame().set_linewidth(0.8)\n"
            "    for text in legend2.get_texts(): text.set_color(YT_TEXT)\n"
            "plt.tight_layout(); plt.show()"
        ),
        new_markdown_cell("### 8.3. Release Distribution by Quarter" if language == "en" else "### 8.3. Distribución de Lanzamientos por Trimestre"),
        new_code_cell(
            "season_counts = df['upload_quarter'].value_counts().sort_index()\n"
            "fig, ax = plt.subplots(figsize=(8, 5))\n"
            "fig.patch.set_facecolor(YT_BG); ax.set_facecolor(YT_BG)\n"
            "bars = ax.bar(season_counts.index, season_counts.values, color=YT_RED, edgecolor='none')\n"
            "ax.set_xlabel('Quarter', fontsize=11, color=YT_TEXT)\n"
            "ax.set_ylabel('Number of Songs', fontsize=11, color=YT_TEXT)\n"
            "ax.set_title('Release Distribution by Quarter', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "for spine in ax.spines.values(): spine.set_color(BORDER_COLOR); spine.set_linewidth(0.8)\n"
            "ax.tick_params(colors=YT_TEXT, labelsize=11)\n"
            "ax.yaxis.grid(True, color=YT_GRID, linestyle='--', alpha=0.7)\n"
            "for bar in bars:\n"
            "    height = bar.get_height()\n"
            "    ax.text(bar.get_x() + bar.get_width()/2., height + 0.5, f'{int(height)}', ha='center', va='bottom', fontsize=11, color=YT_TEXT)\n"
            "plt.tight_layout(); plt.show()"
        ),
    ]


# ============================================================================
# SECTION 9 - COLLABORATIONS
# ============================================================================
def build_collaborations(df: pd.DataFrame, period, language: str) -> list:
    return [
        new_markdown_cell(section_title("collaborations", language)),
        new_code_cell(
            "collab_stats = df.groupby('is_collaboration').agg(count=('track_name', 'count'), avg_views=('views', 'mean'), avg_engagement=('engagement', 'mean')).reset_index()\n"
            "collab_stats['is_collaboration'] = collab_stats['is_collaboration'].map({0: 'Solo', 1: 'Collaboration'})\n"
            "collab_stats['avg_views'] = collab_stats['avg_views'].apply(lambda x: f'{x:,.0f}')\n"
            "collab_stats['avg_engagement'] = collab_stats['avg_engagement'].round(2).astype(str) + '%'\n"
            "display(collab_stats)\n"
            "fig, axes = plt.subplots(1, 2, figsize=(14, 6))\n"
            "fig.patch.set_facecolor(YT_BG); axes[0].set_facecolor(YT_BG); axes[1].set_facecolor(YT_BG)\n"
            "sns.boxplot(data=df, x='artist_count', y='views', hue='is_collaboration', palette={0: YT_DARK_GREY, 1: YT_RED}, ax=axes[0])\n"
            "axes[0].set_title('Views vs Number of Artists', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "axes[0].set_xlabel('Number of Artists', fontsize=11, color=YT_TEXT)\n"
            "axes[0].set_ylabel('Views', fontsize=11, color=YT_TEXT)\n"
            "sns.boxplot(data=df, x='artist_count', y='engagement', hue='is_collaboration', palette={0: YT_DARK_GREY, 1: YT_RED}, ax=axes[1])\n"
            "axes[1].set_title('Engagement vs Number of Artists', fontsize=18, color=YT_TEXT, loc='center', pad=20)\n"
            "axes[1].set_xlabel('Number of Artists', fontsize=11, color=YT_TEXT)\n"
            "axes[1].set_ylabel('Engagement (%)', fontsize=11, color=YT_TEXT)\n"
            "for ax in axes:\n"
            "    for spine in ax.spines.values(): spine.set_color(BORDER_COLOR); spine.set_linewidth(0.8)\n"
            "    ax.tick_params(colors=YT_TEXT, labelsize=11)\n"
            "    ax.yaxis.grid(True, color=YT_GRID, linestyle='--', alpha=0.7)\n"
            "    legend = ax.get_legend()\n"
            "    if legend:\n"
            "        legend.get_frame().set_edgecolor(YT_GRID); legend.get_frame().set_linewidth(0.8)\n"
            "plt.tight_layout(); plt.show()"
        ),
    ]


# ============================================================================
# SECTION 10 - EXECUTIVE SUMMARY
# ============================================================================
def build_exec_summary(df: pd.DataFrame, period, language: str) -> list:
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
