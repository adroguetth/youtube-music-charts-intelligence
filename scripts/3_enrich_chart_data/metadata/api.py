"""
API - YouTube Data API v3 Layer
============================================================================
Layer 1 of the metadata retrieval fallback chain.

Uses the official YouTube Data API v3 to fetch full video metadata:
duration, likes, comment count, default audio language, region restrictions,
upload date, video type flags, channel type, and collaboration signals.

This is the preferred layer because it is fast, reliable, and returns
structured data without browser automation overhead. It requires a valid
`YOUTUBE_API_KEY` and gracefully falls back to other layers when unavailable.

Features
--------
- ISO 8601 duration parsing via `isodate` (auto-installed if missing).
- Robust video ID extraction from any YouTube URL format.
- Full metadata extraction: snippet, contentDetails, and statistics.
- Graceful error handling: any failure returns the zeroed metadata dict
  with a populated `error` field so the orchestrator can try the next layer.

Dependencies
------------
- Internal: `.detector` (classify helpers), `..config` (logger).
- External: re, subprocess, sys (stdlib); isodate, googleapiclient
  (auto-installed if missing).

Requirements
------------
- Python 3.7+
- `YOUTUBE_API_KEY` set in the environment to use this layer.

Notes
-----
- The metadata dict schema MUST match `_empty_metadata()` in the
  `metadata` package `__init__.py`. Any new field added here must also be
  added there.
- This function returns the metadata dict directly on success, and the
  orchestrator (`fetch_video_metadata`) exits immediately without trying
  the Selenium or yt-dlp layers.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import re
import subprocess
import sys

from .detector import (
    detect_channel_type,
    detect_collaboration,
    detect_video_type,
    parse_upload_season,
)
from ..config import logger


def fetch_metadata_via_api(url: str, artists_csv: str, api_key: str) -> dict:
    """
    Fetch video metadata using the YouTube Data API v3.

    Parameters
    ----------
    url : str
        Full YouTube video URL.
    artists_csv : str
        Raw "Artist Names" string used for collaboration detection.
    api_key : str
        YouTube Data API v3 key.

    Returns
    -------
    dict
        Populated metadata dict. If the API call fails, the `error` key is
        non-empty and all other fields remain at their zero defaults.
    """
    # Import and validate `isodate` (used to parse ISO 8601 durations)
    try:
        import isodate
    except ImportError:
        logger.info("   📦 Installing isodate...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "isodate"])
        import isodate

    from googleapiclient.discovery import build

    # Local defaults — mirror _empty_metadata() from the orchestrator
    metadata = {
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

    # Extract the 11-character video ID from any YouTube URL format
    vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
    if not vid_match:
        metadata["error"] = "API: could not extract video_id from URL"
        return metadata

    video_id = vid_match.group(1)

    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        response = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=video_id,
        ).execute()

        if not response.get("items"):
            metadata["error"] = "API: video not found"
            return metadata

        video = response["items"][0]
        snippet = video.get("snippet", {})
        stats = video.get("statistics", {})
        content = video.get("contentDetails", {})

        # Parse ISO 8601 duration (e.g., PT3M47S → 227 seconds)
        iso_dur = content.get("duration", "")
        if iso_dur:
            dur_s = int(isodate.parse_duration(iso_dur).total_seconds())
            metadata["Duration (s)"] = dur_s
            metadata["duration (m:s)"] = f"{dur_s // 60}:{dur_s % 60:02d}"

        metadata["likes"] = int(stats.get("likeCount", 0))
        metadata["comment_count"] = int(stats.get("commentCount", 0))

        lang = snippet.get("defaultAudioLanguage", "")
        metadata["audio_language"] = lang[:2].upper() if lang else ""

        region = content.get("regionRestriction", {})
        metadata["region_restricted"] = bool(
            region.get("blocked") or region.get("allowed")
        )

        pub_date = snippet.get("publishedAt", "")[:10]
        if pub_date:
            metadata["upload_date"] = pub_date
            metadata.update(parse_upload_season(pub_date))

        title_api = snippet.get("title", "")
        desc_api = snippet.get("description", "")
        channel_api = snippet.get("channelTitle", "")

        metadata.update(detect_video_type(title_api, desc_api))
        metadata.update(detect_channel_type(channel_api))
        metadata.update(detect_collaboration(title_api, artists_csv))

        return metadata

    except Exception as e:
        metadata["error"] = f"API error: {e}"
        return metadata
