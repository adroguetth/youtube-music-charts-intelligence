"""
Metadata - Retrieval Orchestrator
============================================================================
Orchestrates the three-layer metadata retrieval fallback strategy.

This module is the single entry point for video metadata extraction. It
calls the appropriate layers in order (API → Selenium → yt-dlp) and returns
the first successful result. If all layers fail, it returns a zeroed-out
metadata dict with a populated `error` field.

The metadata schema is defined in `_empty_metadata()` and must remain
synchronized with the schema used by the API, Selenium, and yt-dlp layers.

Features
--------
- Three-layer fallback: API → Selenium → yt-dlp.
- Layer-agnostic: callers only need to know about `fetch_video_metadata`.
- Robust error accumulation: all layer errors are collected into a single
  `error` field for diagnostics.
- Schema consistency: the returned dict always has the same keys, regardless
  of which layer succeeded.

Dependencies
------------
- Internal: `.api`, `.selenium`, `.yt_dlp`, `.detector`, `..config`.
- External: none (the layers handle their own imports).

Requirements
------------
- Python 3.7+

Notes
-----
- Layer 1 (API) is tried only if `api_key` is provided and non-empty.
- Layer 2 (Selenium) is tried if Layer 1 fails or is unavailable.
- Layer 3 (yt-dlp) is tried only as a last resort.
- The `_empty_metadata()` function MUST be kept in sync with the local
  defaults in `api.py`, `selenium.py`, and `yt_dlp.py`.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from typing import Optional

from .api import fetch_metadata_via_api
from .selenium import fetch_metadata_via_selenium
from .yt_dlp import fetch_metadata_via_ytdlp
from ..config import IN_GITHUB_ACTIONS, logger


# ============================================================================
# METADATA SCHEMA
# ============================================================================
def _empty_metadata() -> dict:
    """
    Return a zeroed-out metadata dict used as the default before any
    successful retrieval.

    This schema MUST match the local defaults used in `api.py`,
    `selenium.py`, and `yt_dlp.py`. Adding a field here requires adding it
    to all three layers.

    Returns
    -------
    dict
        Metadata dict with all fields at their zero values.
    """
    return {
        "Duration (s)": 0,
        "duration (m:s)": "0:00",
        "upload_date": "",
        "likes": 0,
        "comment_count": 0,
        "audio_language": "",
        "is_official_video": False,
        "is_lyric_video": False,
        "is_live_performance": False,
        "upload_season": "unknown",
        "channel_type": "unknown",
        "is_collaboration": False,
        "artist_count": 1,
        "region_restricted": False,
        "error": "",
    }


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================
def fetch_video_metadata(
    url: str,
    artists_csv: str = "",
    api_key: Optional[str] = None,
) -> dict:
    """
    Orchestrate the three-layer metadata retrieval strategy.

    Layer 1 — YouTube Data API v3 (requires `api_key`):
        Full metadata: duration, likes, comments, language, date, restrictions.
        Exits immediately on success.

    Layer 2 — Selenium headless browser:
        Partial metadata: duration, channel type, date, video type flags.
        Used when API is absent or returns an error.

    Layer 3 — yt-dlp with anti-blocking client rotation:
        Tries android → ios → android+web → web player clients in order.
        Last resort; may be slower and still fail against aggressive bot detection.

    Parameters
    ----------
    url : str
        Full YouTube video URL.
    artists_csv : str, optional
        Raw "Artist Names" string for collaboration detection.
    api_key : str, optional
        YouTube Data API v3 key. When absent, Layer 1 is skipped.

    Returns
    -------
    dict
        Populated metadata dict. The `error` key is non-empty if all layers
        fail.
    """
    metadata = _empty_metadata()
    errors = []

    # ------------------------------------------------------------------
    # LAYER 1: YouTube Data API v3
    # ------------------------------------------------------------------
    if api_key:
        try:
            api_metadata = fetch_metadata_via_api(url, artists_csv, api_key)
            if not api_metadata["error"]:
                return api_metadata  # Layer 1 succeeded — skip layers 2 and 3
            else:
                errors.append(api_metadata["error"])
        except Exception as e:
            errors.append(f"API layer exception: {e}")

    # ------------------------------------------------------------------
    # LAYER 2: Selenium headless browser
    # ------------------------------------------------------------------
    if errors or not api_key:
        try:
            sel_metadata = fetch_metadata_via_selenium(url, artists_csv)
            if not sel_metadata["error"]:
                metadata.update(sel_metadata)
                return metadata
            else:
                errors.append(sel_metadata["error"])
        except Exception as e:
            errors.append(f"Selenium layer exception: {e}")

    # ------------------------------------------------------------------
    # LAYER 3: yt-dlp
    # ------------------------------------------------------------------
    try:
        ytdlp_metadata = fetch_metadata_via_ytdlp(url, artists_csv)
        if not ytdlp_metadata["error"]:
            metadata.update(ytdlp_metadata)
            errors = []  # Clear previous errors — layer 3 succeeded
        else:
            errors.append(ytdlp_metadata["error"])
    except Exception as e:
        errors.append(f"yt-dlp layer exception: {e}")

    # If all layers failed, return the empty metadata with the accumulated errors
    if errors:
        metadata["error"] = " | ".join(errors)
        if IN_GITHUB_ACTIONS:
            logger.warning(f"⚠️  Metadata error for {url}: {metadata['error']}")

    return metadata


# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = ["fetch_video_metadata"]
