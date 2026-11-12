"""
Metrics - Aggregations for the Weekly Report
============================================================================
Pure aggregation functions consumed by the notebook builders.

Responsibilities
----------------
- Compute the metrics displayed in each section of the weekly report.
- Return plain DataFrames or dicts. No plotting, no notebook logic.
- Keep every function stateless and side-effect free.

Notes
-----
- Functions are extracted from the aggregation logic used in the previous
  monolithic generator, so the numbers match the existing notebooks.
- When the monthly report arrives (v3.0), functions that are specific to
  multi-week periods will be added in a dedicated module
  (`core.metrics.monthly`), not here. Keep this module strictly
  weekly-safe.
- No function in this module imports `nbformat`, `matplotlib` or
  `streamlit`. Builders and the dashboard import from here, never the
  other way around.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import pandas as pd

# ============================================================================
# GENERAL STATISTICS
# ============================================================================
def general_stats(df: pd.DataFrame) -> dict:
    """
    Return headline counters used in the 'General Statistics' section.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched songs for the period.

    Returns
    -------
    dict
        Keys: ``total_songs``, ``unique_countries``, ``unique_genres``,
        ``total_views``, ``total_likes``, ``total_comments``,
        ``avg_views``, ``avg_likes``, ``avg_engagement``.
    """
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


# ============================================================================
# COUNTRY METRICS
# ============================================================================
def top_countries(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """
    Top N countries by song count and total views.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched songs for the period.
    n : int
        Number of countries to return.

    Returns
    -------
    pd.DataFrame
        Columns: ``artist_country``, ``total_songs``, ``total_views``.
        Sorted by ``total_songs`` descending.
    """
    return (
        df.groupby("artist_country")
        .agg(
            total_songs=("rank", "count"),
            total_views=("views", "sum"),
        )
        .reset_index()
        .sort_values("total_songs", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )


def top_countries_by_likes(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """
    Top N countries by total likes.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched songs for the period.
    n : int
        Number of countries to return.

    Returns
    -------
    pd.DataFrame
        Columns: ``artist_country``, ``total_likes``.
        Sorted by ``total_likes`` descending.
    """
    return (
        df.groupby("artist_country")["likes"]
        .sum()
        .reset_index()
        .rename(columns={"likes": "total_likes"})
        .sort_values("total_likes", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )


def top_songs_by_country(
    df: pd.DataFrame,
    country: str,
    metric: str = "views",
    n: int = 5,
) -> pd.DataFrame:
    """
    Top N songs for a single country, by a given metric.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched songs for the period.
    country : str
        Value of ``artist_country`` to filter by.
    metric : str
        Column to sort by: ``"views"``, ``"likes"`` or ``"engagement"``.
    n : int
        Number of songs to return.

    Returns
    -------
    pd.DataFrame
        Columns: ``track_name``, ``artist_names``, ``views``, ``likes``,
        ``engagement``. Sorted by `metric` descending.
    """
    cols = ["track_name", "artist_names", "views", "likes", "engagement"]
    return (
        df[df["artist_country"] == country]
        .nlargest(n, metric)[cols]
        .reset_index(drop=True)
    )


# ============================================================================
# GENRE METRICS
# ============================================================================
def genre_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate song count, views, likes and engagement per macro genre.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched songs for the period.

    Returns
    -------
    pd.DataFrame
        Columns: ``macro_genre``, ``total_songs``, ``total_views``,
        ``total_likes``, ``avg_views``, ``avg_likes``,
        ``engagement_rate``. Sorted by ``total_songs`` descending.

    Notes
    -----
    ``engagement_rate`` is computed as
    ``total_likes / total_views * 100``, with 0 where ``total_views`` is 0.
    This matches the definition used by the previous monolithic generator.
    """
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
        out["total_likes"]
        / out["total_views"].replace(0, pd.NA)
        * 100
    ).fillna(0).round(2)
    return out.sort_values("total_songs", ascending=False).reset_index(drop=True)


# ============================================================================
# VIDEO METRICS
# ============================================================================
def video_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate count, average views and average engagement by video type.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched songs for the period.

    Returns
    -------
    pd.DataFrame
        One row per video type (``Official``, ``Lyric``, ``Live``) with
        columns: ``video_type``, ``count``, ``pct``, ``avg_views``,
        ``avg_engagement``.
    """
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
            "avg_engagement": (
                float(subset["engagement"].mean()) if len(subset) else 0.0
            ),
        })
    return pd.DataFrame(rows)


# ============================================================================
# SONG METRICS
# ============================================================================
def top_songs(
    df: pd.DataFrame,
    metric: str = "views",
    n: int = 10,
) -> pd.DataFrame:
    """
    Top N songs by a given metric.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched songs for the period.
    metric : str
        Column to sort by: ``"views"``, ``"likes"`` or ``"engagement"``.
    n : int
        Number of songs to return.

    Returns
    -------
    pd.DataFrame
        Columns: ``rank``, ``track_name``, ``artist_names``, `metric`,
        ``artist_country``. Sorted by `metric` descending.
    """
    cols = ["rank", "track_name", "artist_names", metric, "artist_country"]
    return df.nlargest(n, metric)[cols].reset_index(drop=True)


# ============================================================================
# COLLABORATION METRICS
# ============================================================================
def collaborations(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compare solo songs vs collaborations on views and engagement.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched songs for the period.

    Returns
    -------
    pd.DataFrame
        Two rows (``Solo`` and ``Collaboration``) with columns:
        ``is_collaboration``, ``count``, ``avg_views``, ``avg_engagement``.
    """
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
