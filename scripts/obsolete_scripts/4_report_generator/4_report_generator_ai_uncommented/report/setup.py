"""
Setup - Notebook Initialization Cell
============================================================================
Builds the first code cell of the notebook. This cell is responsible for:
    - Importing required libraries (pandas, matplotlib, seaborn, etc.).
    - Configuring global visual parameters (fonts, sizes) from `theme.py`.
    - Defining helper functions for formatting and continent mapping.
    - Defining metric functions inline to ensure the notebook is self-contained.
    - Defining visual helpers (`style_axes`, `add_bar_labels`).
    - Loading the enriched database into a DataFrame.

Notes
-----
- The cell code is stored as a template string (`SETUP_CODE_TEMPLATE`).
- Theme constants are injected into the template using a safe replacement
  mechanism (`__THEME_*__` placeholders). We do NOT use `str.format()` because
  the code contains Python f-strings with `{}` that would break formatting.
- The DB filename is injected using `__DB_FILENAME__`.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

from nbformat.v4 import new_code_cell

from report import theme


# ============================================================================
# TEMPLATE
# ============================================================================
SETUP_CODE_TEMPLATE = """\
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
plt.rcParams["font.sans-serif"] = __THEME_FONT_FAMILY__
plt.rcParams["figure.figsize"] = __THEME_FIGURE_SIZE__
plt.rcParams["font.size"] = __THEME_BASE_FONT_SIZE__
plt.rcParams["axes.titlesize"] = __THEME_TITLE_FONT_SIZE__
plt.rcParams["axes.titleweight"] = "normal"
plt.rcParams["axes.labelsize"] = __THEME_BASE_FONT_SIZE__
plt.rcParams["figure.dpi"] = __THEME_FIGURE_DPI__

# Standardized color palette
YT_RED = "__THEME_YT_RED__"
YT_DARK_GREY = "__THEME_YT_DARK_GREY__"
YT_TEXT = "__THEME_YT_TEXT__"
YT_GRAY = "__THEME_YT_GRAY__"
YT_GRID = "__THEME_YT_GRID__"
YT_BG = "__THEME_YT_BG__"

# Style variables
BORDER_COLOR = "__THEME_BORDER_COLOR__"
BAR_HEIGHT = __THEME_BAR_HEIGHT__
GRID_STYLE = __THEME_GRID_STYLE__
GRID_ALPHA = __THEME_GRID_ALPHA__
TITLE_FONT_SIZE = __THEME_TITLE_FONT_SIZE__

# Categorical palette for multi-series charts
CATEGORICAL_PALETTE = __THEME_CATEGORICAL_PALETTE__

# Format global to avoid scientific notation in DataFrames
pd.set_option('display.float_format', lambda x: f'{x:,.3f}')

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
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

def style_axes(ax, grid_axis='y'):
    for spine in ax.spines.values():
        spine.set_color(BORDER_COLOR)
        spine.set_linewidth(0.8)
    ax.tick_params(colors=YT_TEXT, labelsize=11)
    if grid_axis == "y":
        ax.yaxis.grid(True, color=YT_GRID, linestyle=GRID_STYLE, alpha=GRID_ALPHA)
        ax.xaxis.grid(False)
    else:
        ax.xaxis.grid(True, color=YT_GRID, linestyle=GRID_STYLE, alpha=GRID_ALPHA)
        ax.yaxis.grid(False)

def add_bar_labels(ax, fmt="{:.0f}", suffix="", horizontal=True):
    if horizontal:
        for p in ax.patches:
            width = p.get_width()
            if width == 0: continue
            ax.text(width + (width * 0.02), p.get_y() + p.get_height() / 2,
                    f"{fmt.format(width)}{suffix}", ha='left', va='center', fontsize=11, color=YT_TEXT)
    else:
        for p in ax.patches:
            height = p.get_height()
            if height == 0: continue
            ax.text(p.get_x() + p.get_width() / 2, height + (height * 0.02),
                    f"{fmt.format(height)}{suffix}", ha='center', va='bottom', fontsize=11, color=YT_TEXT)

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


# ==============================================================================
# DATA LOADING
# ==============================================================================
DB_PATH = Path("../../charts_archive/3_enrich-chart-data/__DB_FILENAME__")
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("SELECT * FROM enriched_songs", conn)
conn.close()

df["upload_date"] = pd.to_datetime(df["upload_date"], errors="coerce")
df["upload_quarter"] = df["upload_date"].dt.quarter
df["engagement"] = np.where(df["views"] > 0, (df["likes"] / df["views"] * 100).round(2), 0.0)
df["continent"] = df["artist_country"].apply(get_continent)
"""


# ============================================================================
# BUILDER
# ============================================================================
def build_setup(period, language: str) -> list:
    """
    Emit the setup cell with theme variables injected.
    
    Parameters
    ----------
    period : core.periods.Period
        The reporting period (used to build the DB filename).
    language : str
        ``"en"`` or ``"es"`` (currently unused in this cell, kept for
        signature consistency with other builders).

    Returns
    -------
    list
        A list containing a single `nbformat` code cell.
    """
    code = SETUP_CODE_TEMPLATE

    # Inject theme constants safely (no str.format, avoids f-string braces issues)
    replacements = {
        "__THEME_FONT_FAMILY__": repr(theme.FONT_FAMILY),
        "__THEME_FIGURE_SIZE__": str(theme.FIGURE_SIZE),
        "__THEME_BASE_FONT_SIZE__": str(theme.BASE_FONT_SIZE),
        "__THEME_TITLE_FONT_SIZE__": str(theme.TITLE_FONT_SIZE),
        "__THEME_FIGURE_DPI__": str(theme.FIGURE_DPI),
        "__THEME_YT_RED__": theme.YT_RED,
        "__THEME_YT_DARK_GREY__": theme.YT_DARK_GREY,
        "__THEME_YT_TEXT__": theme.YT_TEXT,
        "__THEME_YT_GRAY__": theme.YT_GRAY,
        "__THEME_YT_GRID__": theme.YT_GRID,
        "__THEME_YT_BG__": theme.YT_BG,
        "__THEME_BORDER_COLOR__": theme.BORDER_COLOR,
        "__THEME_BAR_HEIGHT__": str(theme.BAR_HEIGHT),
        "__THEME_GRID_STYLE__": repr(theme.GRID_STYLE),
        "__THEME_GRID_ALPHA__": str(theme.GRID_ALPHA),
        "__THEME_CATEGORICAL_PALETTE__": repr(theme.CATEGORICAL_PALETTE),
        "__DB_FILENAME__": f"youtube_charts_{period.label}_enriched.db",
    }

    for placeholder, value in replacements.items():
        code = code.replace(placeholder, value)

    return [new_code_cell(code)]
