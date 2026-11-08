"""
yt-dlp - Command-Line Extraction Layer
============================================================================
Layer 2 of the metadata retrieval fallback chain.

Uses `yt-dlp` to extract video metadata without browser automation. This is
the preferred fallback layer (before Selenium) because it is significantly
faster and consumes less memory.

To maximize success, the function rotates through multiple "player clients"
(android → ios → android+web → web). YouTube treats these clients
differently, and what fails for one often succeeds for another.

Features
--------
- Auto-installation and auto-upgrade of `yt-dlp`.
- Multi-client rotation with strict validation of returned data.
- Deep validation: a result is only accepted if it contains a valid
  `duration` field. Empty dicts or incomplete responses are rejected.
- Graceful degradation: returns the zeroed metadata dict with a populated
  `error` field if all clients fail or return invalid data.

Dependencies
------------
- Internal: `.detector` (classify helpers), `..config` (logger).
- External: subprocess, sys (stdlib); yt-dlp (auto-installed/upgraded).

Requirements
------------
- Python 3.7+

Notes
-----
- yt-dlp returns upload dates as `YYYYMMDD` (no separators). This module
  converts them to ISO format (`YYYY-MM-DD`) before passing to the detector.
- YouTube frequently updates its bot-detection mechanisms. When yt-dlp
  returns an empty dict or an error string like "Sign in to confirm you're
  not a bot", this module rejects the result and lets the orchestrator fall
  back to Selenium.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import subprocess
import sys

from .detector import (
    detect_channel_type,
    detect_collaboration,
    detect_video_type,
    parse_upload_season,
)
from ..config import logger


def fetch_metadata_via_ytdlp(url: str, artists_csv: str = "") -> dict:
    """
    Fetch video metadata using yt-dlp with multi-client rotation and
    strict validation.

    Parameters
    ----------
    url : str
        Full YouTube video URL.
    artists_csv : str, optional
        Raw "Artist Names" string used for collaboration detection.

    Returns
    -------
    dict
        Populated metadata dict. If all clients fail or return invalid
        data, the `error` key is non-empty and all other fields remain at
        their zero defaults.
    """
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

    # Early validation: reject empty or non-string URLs
    if not url or not isinstance(url, str) or not url.strip():
        metadata["error"] = "yt-dlp error: URL is empty, None, or not a string"
        return metadata

    # Ensure yt-dlp is available
    try:
        import yt_dlp
    except ImportError:
        logger.info("   📦 Installing yt-dlp...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
        import yt_dlp

    # Keep yt-dlp up-to-date — extractor fixes ship frequently
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            check=False,
        )
    except Exception:
        pass

    # Rotate through player clients to evade bot detection
    client_options = [
        {"player_client": ["android"]},
        {"player_client": ["ios"]},
        {"player_client": ["android", "web"]},
        {"player_client": ["web"]},
    ]

    info = None
    last_error = ""

    for opts in client_options:
        ydl_config = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": False,
            "extract_flat": False,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "extractor_retries": 5,
            "fragment_retries": 5,
            "retry_sleep_functions": {"extractor": 2},
            "sleep_interval": 2,
            "sleep_interval_requests": 2,
            **opts,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_config) as ydl:
                info = ydl.extract_info(url, download=False)

            # STRICT VALIDATION:
            # yt-dlp can return an empty dict or a dict without 'duration'
            # when YouTube blocks the request (e.g., "Sign in to confirm").
            # Reject these responses and try the next client.
            if info and info.get("duration") is not None:
                break
            else:
                last_error = "yt-dlp returned incomplete info (missing duration)"
                info = None
        except Exception as e:
            last_error = str(e)
            continue

    if not info:
        metadata["error"] = f"yt-dlp failed: {last_error}"
        return metadata

    duration = info.get("duration", 0)
    raw_date = info.get("upload_date", "")

    # yt-dlp returns date as YYYYMMDD — convert to ISO format
    if raw_date and len(raw_date) == 8:
        iso_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        metadata["upload_date"] = iso_date
        metadata.update(parse_upload_season(iso_date))

    title_ydlp = info.get("title", "")
    desc_ydlp = info.get("description", "")
    channel_ydlp = info.get("channel", "")

    metadata.update({
        "Duration (s)": duration,
        "duration (m:s)": f"{duration // 60}:{duration % 60:02d}",
        "likes": info.get("like_count", 0),
    })
    metadata.update(detect_video_type(title_ydlp, desc_ydlp))
    metadata.update(detect_channel_type(channel_ydlp))
    metadata.update(detect_collaboration(title_ydlp, artists_csv))

    return metadata
