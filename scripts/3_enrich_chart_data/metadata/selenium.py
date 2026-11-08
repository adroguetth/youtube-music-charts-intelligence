"""
Selenium - Browser Automation Layer
============================================================================
Layer 2 of the metadata retrieval fallback chain.

Uses a headless Chromium browser to extract basic video metadata when the
YouTube Data API is unavailable (no API key or quota exhausted) and before
falling back to yt-dlp.

Extracts: title, duration, channel name, upload date, and video type flags.

Note: Selenium does NOT return likes, comment count, or audio language.
Those fields remain at their zero defaults and are populated only by the API
layer (if available).

Features
--------
- Auto-installation of `selenium` and `webdriver-manager` if missing.
- Anti-detection configuration: realistic user-agent, window size.
- Graceful degradation: any failure returns the zeroed metadata dict with a
  populated `error` field, allowing the orchestrator to try yt-dlp next.

Dependencies
------------
- Internal: `.detector` (classify helpers), `..config` (logger).
- External: subprocess, sys (stdlib); selenium, webdriver-manager
  (auto-installed if missing).

Requirements
------------
- Python 3.7+
- Google Chrome / Chromium installed on the runner (GitHub Actions has it
  pre-installed on `ubuntu-latest`).

Notes
-----
- Selenium is slow (~5–10s per video) and fragile against YouTube layout
  changes. It is used only when the API layer is unavailable.
- The driver is always closed in a `finally` block to avoid zombie
  processes on the runner.

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


def fetch_metadata_via_selenium(url: str, artists_csv: str = "") -> dict:
    """
    Fetch basic video metadata using a headless Chromium browser.

    Parameters
    ----------
    url : str
        Full YouTube video URL.
    artists_csv : str, optional
        Raw "Artist Names" string used for collaboration detection.

    Returns
    -------
    dict
        Populated metadata dict. If the retrieval fails, the `error` key is
        non-empty and all other fields remain at their zero defaults.
    """
    # Ensure selenium and webdriver-manager are available
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        logger.info("   📦 Installing selenium and webdriver-manager...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "selenium", "webdriver-manager",
        ])
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        from webdriver_manager.chrome import ChromeDriverManager

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

    errors = []
    driver = None

    # Standard headless Chrome configuration with a realistic user-agent
    # to avoid bot-detection on YouTube pages
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)

        # Wait for the video title to confirm the page has rendered
        wait = WebDriverWait(driver, 10)
        title_el = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "h1.ytd-video-primary-info-renderer")
            )
        )
        title = title_el.text

        # Duration — scraped from the player progress bar label
        try:
            dur_el = driver.find_element(By.CSS_SELECTOR, "span.ytp-time-duration")
            parts = dur_el.text.split(":")
            if len(parts) == 2:
                duration_s = int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                duration_s = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            else:
                duration_s = 0
            metadata["Duration (s)"] = duration_s
            metadata["duration (m:s)"] = f"{duration_s // 60}:{duration_s % 60:02d}"
        except Exception:
            pass

        # Channel name — used for channel type classification
        try:
            channel_el = driver.find_element(By.CSS_SELECTOR, "a.ytd-channel-name")
            metadata.update(detect_channel_type(channel_el.text))
        except Exception:
            pass

        metadata.update(detect_video_type(title, ""))
        metadata.update(detect_collaboration(title, artists_csv))

        # Upload date from structured data meta tag (more reliable than visible text)
        try:
            date_el = driver.find_element(
                By.CSS_SELECTOR, "meta[itemprop='datePublished']"
            )
            date_str = date_el.get_attribute("content")[:10]
            if date_str:
                metadata["upload_date"] = date_str
                metadata.update(parse_upload_season(date_str))
        except Exception:
            pass

    except Exception as e:
        errors.append(f"Selenium error: {e}")

    finally:
        # Always close the driver to avoid zombie processes on the runner
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    if errors:
        metadata["error"] = " | ".join(errors)

    return metadata
