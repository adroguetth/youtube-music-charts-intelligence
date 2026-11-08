"""
Detector - Video Metadata Classification Helpers
============================================================================
Pure functions that classify YouTube video attributes from title and
description text. These functions are shared across all three metadata
retrieval layers (API, Selenium, yt-dlp) so that consistent heuristics are
applied regardless of the source.

This module contains NO I/O, NO network calls, and NO database access.
Every function here is deterministic and testable in isolation.

Features
--------
- Video type detection: official, lyric, live, special version.
- Collaboration detection: multi-artist tracks via title patterns and CSV
  delimiter counting.
- Channel type classification: VEVO, Topic, Label/Studio, Artist Channel,
  User Channel, General.
- Upload season derivation: maps a publish date to Q1–Q4.
- Region restriction detection: parses the `contentDetails` sub-object.

Dependencies
------------
- Internal: none.
- External: re, datetime (stdlib).

Requirements
------------
- Python 3.7+

Notes
-----
- All functions return plain `dict` objects so they can be merged with
  `metadata.update()` without type conflicts.
- Video type detection scans both the title and the description for
  official/live keywords, but only the title for lyric/special-version
  keywords (avoids false positives from descriptions).
- The `artist_count` heuristic caps at 10 to prevent outlier values from
  malformed CSV strings.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import re
from datetime import datetime


# ============================================================================
# VIDEO TYPE DETECTION
# ============================================================================
def detect_video_type(title: str, description: str = "") -> dict:
    """
    Classify the video type (official, lyric, live, remix/special version)
    by scanning title and description for known keyword patterns.

    Parameters
    ----------
    title : str
        YouTube video title.
    description : str, optional
        Video description text (improves accuracy when provided).

    Returns
    -------
    dict
        Boolean flags: `is_official_video`, `is_lyric_video`,
        `is_live_performance`, `is_special_version`.
    """
    full_text = f"{title.lower()} {description.lower()}"
    title_lower = title.lower()

    is_official = any(kw in full_text for kw in [
        "official", "video oficial", "official video",
        "official music video", "vídeo oficial",
    ])
    is_lyric = any(kw in title_lower for kw in [
        "lyric", "lyrics", "letra", "letras", "karaoke",
        "lyric video", "letra oficial",
    ]) or "lyric" in full_text

    is_live = any(kw in full_text for kw in [
        "live", "en vivo", "concert", "performance", "show",
        "live performance", "en concierto", "directo",
    ])
    is_special = any(kw in title_lower for kw in [
        "remix", "version", "edit", "mix", "bootleg", "rework",
        "sped up", "slowed", "reverb", "acoustic", "acústico",
        "piano version", "instrumental",
    ])

    return {
        "is_official_video": is_official,
        "is_lyric_video": is_lyric,
        "is_live_performance": is_live,
        "is_special_version": is_special,
    }


# ============================================================================
# COLLABORATION DETECTION
# ============================================================================
def detect_collaboration(title: str, artists_csv: str) -> dict:
    """
    Detect whether a track is a multi-artist collaboration.

    Uses regex patterns on the title and falls back to counting delimiters
    in the CSV artist field when title patterns are absent.

    Parameters
    ----------
    title : str
        YouTube video title.
    artists_csv : str
        Raw "Artist Names" string from the chart row.

    Returns
    -------
    dict
        `is_collaboration` (bool) and `artist_count` (int, capped at 10).
    """
    title_lower = title.lower()
    collab_patterns = [
        r"\sft\.\s", r"\sfeat\.\s", r"\sfeaturing\s", r"\sft\s",
        r"\scon\s", r"\swith\s", r"\s&\s", r"\sx\s", r"\s×\s",
        r"\(feat\.", r"\(ft\.", r"\(with", r"\[feat\.", r"\[ft\.",
    ]
    is_collab = any(re.search(p, title_lower, re.IGNORECASE) for p in collab_patterns)

    if artists_csv:
        # Count delimiter-separated tokens as a proxy for artist count
        artist_count = artists_csv.count("&") + artists_csv.count(",") + 1
    else:
        artist_count = 1
        if is_collab:
            # Rough heuristic when CSV is missing
            artist_count = 2 + title_lower.count(" & ") + title_lower.count(" x ")

    return {
        "is_collaboration": is_collab,
        "artist_count": min(artist_count, 10),  # cap at 10 to prevent outliers
    }


# ============================================================================
# CHANNEL TYPE DETECTION
# ============================================================================
def detect_channel_type(channel_title: str) -> dict:
    """
    Classify the YouTube channel type from its title string.

    Categories:
        - `VEVO`: major label premium channel.
        - `Topic`: auto-generated YouTube Music channel.
        - `Label/Studio`: record label or production house.
        - `Artist Channel`: verified artist or band channel.
        - `User Channel`: generic user/fan upload channel.
        - `General`: unclassified.

    Parameters
    ----------
    channel_title : str
        Channel display name.

    Returns
    -------
    dict
        `channel_type` key with the resolved category string.
    """
    if not channel_title:
        return {"channel_type": "unknown"}

    ch = channel_title.lower()

    if "vevo" in ch:
        return {"channel_type": "VEVO"}
    if "topic" in ch:
        return {"channel_type": "Topic"}
    if any(w in ch for w in [
        "records", "music", "label", "entertainment",
        "studios", "production", "presents", "network",
    ]):
        return {"channel_type": "Label/Studio"}
    if any(w in ch for w in [
        "official", "oficial", "artist", "band", "singer",
        "musician", "rapper", "dj", "producer",
    ]):
        return {"channel_type": "Artist Channel"}
    if any(w in ch for w in ["channel", "tv", "hd", "video", "videos"]):
        return {"channel_type": "User Channel"}

    # Structured names like "Beyoncé - Topic" often contain separators
    if " - " in channel_title or " | " in channel_title:
        return {"channel_type": "Artist Channel"}

    return {"channel_type": "General"}


# ============================================================================
# UPLOAD SEASON DETECTION
# ============================================================================
def parse_upload_season(publish_date: str) -> dict:
    """
    Derive the fiscal quarter from an ISO date string.

    Maps calendar months to Q1–Q4 using standard quarter boundaries.

    Parameters
    ----------
    publish_date : str
        Date string in `YYYY-MM-DD` format (only the first 10 chars are used).

    Returns
    -------
    dict
        `upload_season` key with value `'Q1'`–`'Q4'` or `'unknown'`.
    """
    if not publish_date or len(publish_date) < 10:
        return {"upload_season": "unknown"}

    try:
        date = datetime.strptime(publish_date[:10], "%Y-%m-%d")
        quarter = (date.month - 1) // 3 + 1
        return {"upload_season": f"Q{quarter}"}
    except Exception:
        return {"upload_season": "unknown"}


# ============================================================================
# REGION RESTRICTION DETECTION
# ============================================================================
def detect_region_restrictions(content_details: dict) -> dict:
    """
    Check whether a video carries regional restriction metadata.

    A video is flagged as restricted if the `contentDetails` object contains
    either a `blocked` or `allowed` region list — both indicate geo-gating.

    Parameters
    ----------
    content_details : dict
        The `contentDetails` sub-object from the YouTube API response.

    Returns
    -------
    dict
        `region_restricted` (bool).
    """
    if not content_details:
        return {"region_restricted": False}

    region = content_details.get("regionRestriction", {})
    return {
        "region_restricted": bool(region.get("blocked") or region.get("allowed"))
    }
