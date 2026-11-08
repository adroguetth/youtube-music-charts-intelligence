"""
yt-dlp - Command-Line Extraction Layer
============================================================================
Layer 3 of the metadata retrieval fallback chain.

Uses `yt-dlp` to extract video metadata without browser automation. This is
the last-resort layer: it is slower and more likely to be blocked by
YouTube's bot detection, but it requires no API key and no Chrome driver.

To maximize success, the function rotates through multiple "player clients"
(android → ios → android+web → web). YouTube treats these clients
differently, and what fails for one often succeeds for another.

Features
--------
- Auto-installation of `yt-dlp` if missing.
- Auto-upgrade of `yt-dlp` to the latest version (extractor fixes ship
  frequently).
- Multi-client rotation: android → ios → android+web → web.
- Retry logic with configurable sleep intervals to avoid rate limits.
- Graceful degradation: returns the zeroed metadata dict with a populated
  `error` field if all clients fail.

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
- The `extract_info` call uses `download=False`, so no media is downloaded;
  only metadata is fetched.
- If all clients fail, the last error message is preserved for diagnostics.

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
    Fetch video metadata using yt-dlp with multi-client rotation.

    Parameters
    ----------
    url : str
        Full YouTube video URL.
    artists_csv : str, optional
        Raw "Artist Names" string used for collaboration detection.

    Returns
    -------
    dict
        Populated metadata dict. If all clients fail, the `error` key is
        non-empty and all other fields remain at their zero defaults.
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
            if info:
                break
        except Exception as e:
            last_error = str(e)
            continue

    if not info:
        metadata["error"] = f"yt-dlp could not extract info: {last_error}"
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
