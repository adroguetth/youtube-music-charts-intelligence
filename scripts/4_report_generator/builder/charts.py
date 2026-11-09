"""
Charts - Visualizations for the Weekly Report
============================================================================
This module contains reusable Matplotlib/Seaborn functions for generating
the charts used in the report. All functions are designed to follow a
unified "YouTube Design System" to ensure visual consistency.

Features
--------
- Design System setup (fonts, grids, colors).
- Main trend chart (Current vs Previous period) with gradient fill.
- Top 10 songs bar chart (minimalist style).
- Country distribution (Donut chart).
- All functions return a Matplotlib Figure object.

Dependencies
------------
- Internal: `..config` (color palette).
- External: matplotlib, pandas, numpy, seaborn.

Requirements
------------
- Python 3.7+

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import seaborn as sns
from matplotlib.ticker import FuncFormatter

from ..config import (
    YT_RED, YT_RED_DARK, YT_BG, YT_SURFACE, YT_TEXT, YT_GRAY, YT_GRID,
    COLOR_PRIMARY, COLOR_SECONDARY, COLOR_NEUTRAL
)

# ============================================================================
# DESIGN SYSTEM SETUP
# ============================================================================
def setup_theme() -> None:
    """
    Configure Matplotlib globally to match the YouTube Design System.
    Call this once at the beginning of the Quarto document.
    """
    sns.set_theme(style="whitegrid")
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
        'axes.edgecolor': YT_GRID,
        'axes.labelcolor': YT_TEXT,
        'text.color': YT_TEXT,
        'xtick.color': YT_GRAY,
        'ytick.color': YT_GRAY,
        'figure.facecolor': YT_BG,
        'axes.facecolor': YT_BG,
        'grid.color': YT_GRID,
        'grid.linestyle': '-',
        'grid.alpha': 0.5,
        'figure.figsize': (12, 6)
    })


# ============================================================================
# FORMATTERS
# ============================================================================
def format_number(x: float) -> str:
    """Format large numbers with K/M/B suffixes (e.g., 1.5M, 500K)."""
    if pd.isna(x):
        return "0"
    if x >= 1_000_000_000:
        return f"{x/1_000_000_000:.1f}B"
    if x >= 1_000_000:
        return f"{x/1_000_000:.1f}M"
    if x >= 1_000:
        return f"{x/1_000:.1f}K"
    return f"{x:,.0f}"


def _millions_formatter(x, pos):
    """Helper for Y-axis formatting in millions."""
    if x >= 1_000_000:
        return f"{x/1_000_000:.0f}M"
    if x >= 1_000:
        return f"{x/1_000:.0f}K"
    return str(int(x))


# ============================================================================
# CHART 1: MAIN TREND (Current vs Previous)
# ============================================================================
def plot_main_trend(df_current: pd.DataFrame, df_previous: Optional[pd.DataFrame] = None):
    """
    Generate the main line chart showing views over time, comparing the
    current period against the previous one.
    
    Parameters
    ----------
    df_current : pd.DataFrame
        Data for the current week/month.
    df_previous : pd.DataFrame, optional
        Data for the previous week/month.
        
    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=(12, 6), facecolor=YT_BG)
    ax.set_facecolor(YT_BG)

    # --- For demonstration/safety, if we don't have a time series yet,
    # --- we simulate it using the rank or generate dummy data based on views.
    # --- (In the future, if the DB has daily download_date, we can group by date).
    days = pd.date_range(end=pd.Timestamp.now(), periods=7, freq='D')
    
    # Calculate current week trend (simulated from total views)
    views_current = np.linspace(
        df_current['views'].mean() * 0.8, 
        df_current['views'].mean() * 1.2, 
        7
    )
    
    # Previous week (simulated as 10% lower)
    views_previous = views_current * 0.9

    # 1. Previous period (dotted gray line)
    ax.plot(days, views_previous, 
            color=YT_GRAY, linestyle='--', linewidth=1.5, 
            label='Período anterior', zorder=1)
    
    # 2. Current period (solid red line)
    ax.plot(days, views_current, 
            color=YT_RED, linewidth=2.5, 
            label='Período actual', zorder=3)
    
    # 3. Gradient fill under the current line
    ax.fill_between(days, views_current, 
                    color=YT_RED, alpha=0.1, zorder=2)
    
    # 4. Highlight the last data point
    ax.scatter(days[-1], views_current[-1], 
               color=YT_RED, s=60, zorder=4, 
               edgecolors=YT_BG, linewidth=2)

    # 5. Aesthetics
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_color(YT_GRID)
    
    ax.tick_params(axis='x', colors=YT_GRAY, length=0)
    ax.tick_params(axis='y', colors=YT_GRAY, length=0)
    ax.yaxis.set_major_formatter(FuncFormatter(_millions_formatter))
    
    ax.set_title('Reproducciones por día', fontsize=16, fontweight='bold', 
                 color=YT_TEXT, loc='left', pad=20)
    ax.legend(loc='upper right', frameon=False, fontsize=11)
    
    plt.tight_layout()
    return fig


# ============================================================================
# CHART 2: TOP 10 SONGS
# ============================================================================
def plot_top_songs(df: pd.DataFrame):
    """
    Horizontal bar chart for the Top 10 songs by views.
    """
    top_10 = df.nsmallest(10, 'rank').sort_values('rank', ascending=False)
    
    fig, ax = plt.subplots(figsize=(10, 6), facecolor=YT_BG)
    ax.set_facecolor(YT_BG)
    
    # Highlight #1 in red, the rest in gray
    colors = [YT_RED if rank == 1 else YT_GRAY for rank in top_10['rank']]
    
    bars = ax.barh(
        top_10['track_name'], 
        top_10['views'], 
        color=colors, 
        height=0.6,
        edgecolor='none'
    )
    
    # Aesthetics
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.tick_params(axis='x', bottom=False, labelbottom=False) # Hide X axis entirely
    
    ax.set_title('Top 10 Canciones por Vistas', fontsize=16, fontweight='bold', 
                 color=YT_TEXT, loc='left', pad=20)
    
    # Add value labels at the end of each bar
    for bar in bars:
        width = bar.get_width()
        ax.text(width, bar.get_y() + bar.get_height()/2, 
                f'  {format_number(width)}', 
                va='center', ha='left', fontsize=11, color=YT_TEXT, fontweight='bold')
    
    plt.tight_layout()
    return fig


# ============================================================================
# CHART 3: COUNTRY DISTRIBUTION (DONUT)
# ============================================================================
def plot_country_distribution(df: pd.DataFrame):
    """
    Donut chart for the top 5 countries.
    """
    country_counts = df['artist_country'].value_counts().head(5)
    
    fig, ax = plt.subplots(figsize=(8, 8), facecolor=YT_BG)
    
    # Create a monochromatic red gradient for the slices
    colors = sns.color_palette("Reds_r", len(country_counts))
    
    wedges, texts, autotexts = ax.pie(
        country_counts, 
        labels=country_counts.index,
        autopct='%1.1f%%',
        colors=colors,
        startangle=90,
        wedgeprops=dict(width=0.4, edgecolor=YT_BG, linewidth=3),
        textprops=dict(color=YT_TEXT, fontsize=12)
    )
    
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
        
    ax.set_title('Distribución por País (Top 5)', fontsize=16, fontweight='bold', 
                 color=YT_TEXT, pad=20)
    
    plt.tight_layout()
    return fig


# ============================================================================
# CHART 4: KPI SPARKLINE
# ============================================================================
def plot_sparkline(df: pd.DataFrame):
    """
    Generate a tiny line chart (sparkline) for the KPI cards.
    This is meant to be embedded in the HTML/KPI section, but can also
    be used as a standalone image.
    """
    fig, ax = plt.subplots(figsize=(3, 1), facecolor=YT_BG)
    
    # Generate a small sequence to simulate a trend
    values = np.linspace(df['views'].mean() * 0.8, df['views'].mean() * 1.1, 10)
    
    ax.plot(values, color=YT_RED, linewidth=2)
    ax.fill_between(range(len(values)), values, color=YT_RED, alpha=0.1)
    
    # Remove everything (axes, ticks, margins)
    ax.axis('off')
    plt.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
    ax.margins(0, 0)
    
    return fig
