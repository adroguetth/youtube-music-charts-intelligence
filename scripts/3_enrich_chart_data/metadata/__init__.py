"""
Metadata - Retrieval Orchestrator
============================================================================
Orchestrates the three-layer metadata retrieval fallback strategy.

This module is the single entry point for video metadata extraction. It
calls the appropriate layers in order (API → yt-dlp → Selenium) and returns
the first successful result. If all layers fail, it returns a zeroed-out
metadata dict with a populated `error` field.

The metadata schema is defined in `_empty_metadata()` and must remain
synchronized with the schema used by the API, yt-dlp, and Selenium layers.

Features
--------
- Three-layer fallback: API → yt-dlp → Selenium.
- Strict validation: a layer is only considered successful if it returns
  valid duration data (prevents saving empty dicts as "success").
- Robust error accumulation: all layer errors are collected into a single
  `error` field for diagnostics.
- Early exit: if a layer succeeds, subsequent layers are skipped.
- Handles empty/None URLs gracefully.

Dependencies
------------
- Internal: `.api`, `.yt_dlp`, `.selenium`, `.detector`, `..config`.
- External: none (the layers handle their own imports).

Requirements
------------
- Python 3.7+

Notes
-----
- Layer 1 (API) is tried only if `api_key` is provided and non-empty.
- Layer 2 (yt-dlp) is tried if Layer 1 fails or is unavailable. It is
  preferred over Selenium due to its speed and lower resource footprint.
- Layer 3 (Selenium) is tried only as a last resort.
- A layer is considered successful only if it returns a non-empty `error`
  field AND a `Duration (s)` > 0. This prevents partial/empty responses
  from being treated as valid data.
- The `_empty_metadata()` function MUST be kept in sync with the local
  defaults in `api.py`, `yt_dlp.py`, and `selenium.py`.

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
    `yt_dlp.py`, and `selenium.py`. Adding a field here requires adding it
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
# HELPERS
# ============================================================================
def _is_valid_result(metadata: dict) -> bool:
    """
    Determine if a metadata dict represents a successful retrieval.

    A result is considered valid if:
    1. The `error` field is empty.
    2. The `Duration (s)` field is greater than zero.

    Parameters
    ----------
    metadata : dict
        Metadata dict returned by one of the retrieval layers.

    Returns
    -------
    bool
        True if the result is valid, False otherwise.
    """
    if not metadata:
        return False
    if metadata.get("error"):
        return False
    if metadata.get("Duration (s)", 0) <= 0:
        return False
    return True


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

    Layer 2 — yt-dlp with anti-blocking client rotation:
        Tries android → ios → android+web → web player clients in order.
        Preferred over Selenium due to speed and lower resource usage.

    Layer 3 — Selenium headless browser:
        Partial metadata: duration, channel type, date, video type flags.
        Last resort; slower and more resource-intensive.

    Parameters
    ----------
    url : str
        Full YouTube video URL. May be None or empty.
    artists_csv : str, optional
        Raw "Artist Names" string for collaboration detection.
    api_key : str, optional
        YouTube Data API v3 key. When absent, Layer 1 is skipped.

    Returns
    -------
    dict
        Populated metadata dict. The `error` key is non-empty if all layers
        fail or if the input is invalid.
    """
    metadata = _empty_metadata()
    errors = []

    # ------------------------------------------------------------------
    # Pre-validation: URL
    # ------------------------------------------------------------------
    if not url or not isinstance(url, str) or not url.strip():
        metadata["error"] = "Invalid input: URL is empty, None, or not a string"
        if IN_GITHUB_ACTIONS:
            logger.warning(f"⚠️  Metadata error: invalid URL input")
        return metadata

    # ------------------------------------------------------------------
    # LAYER 1: YouTube Data API v3
    # ------------------------------------------------------------------
    if api_key:
        try:
            api_metadata = fetch_metadata_via_api(url, artists_csv, api_key)
            if _is_valid_result(api_metadata):
                return api_metadata
            else:
                errors.append(api_metadata.get("error", "API returned incomplete data"))
        except Exception as e:
            errors.append(f"API layer exception: {e}")

    # ------------------------------------------------------------------
    # LAYER 2: yt-dlp
    # ------------------------------------------------------------------
    try:
        ytdlp_metadata = fetch_metadata_via_ytdlp(url, artists_csv)
        if _is_valid_result(ytdlp_metadata):
            metadata.update(ytdlp_metadata)
            return metadata
        else:
            errors.append(ytdlp_metadata.get("error", "yt-dlp returned no data (empty dict)"))
    except Exception as e:
        errors.append(f"yt-dlp layer exception: {e}")

    # ------------------------------------------------------------------
    # LAYER 3: Selenium
    # ------------------------------------------------------------------
    try:
        sel_metadata = fetch_metadata_via_selenium(url, artists_csv)
        if _is_valid_result(sel_metadata):
            metadata.update(sel_metadata)
            return metadata
        else:
            errors.append(sel_metadata.get("error", "Selenium returned no data"))
    except Exception as e:
        errors.append(f"Selenium layer exception: {e}")

    # ------------------------------------------------------------------
    # FINAL: All layers failed
    # ------------------------------------------------------------------
    if errors:
        metadata["error"] = " | ".join(errors)
        if IN_GITHUB_ACTIONS:
            logger.warning(f"⚠️  Metadata error for {url}: {metadata['error']}")

    return metadata


# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = ["fetch_video_metadata"]
