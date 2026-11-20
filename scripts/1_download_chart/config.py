"""
Runtime Configuration - Paths, Constants and Browser Flags
============================================================================
Single source of truth for the scraper's filesystem layout, extraction
thresholds, timezone, proxy rotation and Chromium flags.

Every filesystem path is anchored at the repository root rather than the
process CWD, because cron starts jobs from an arbitrary directory.
``YOUTUBE_CHARTS_BASE_DIR`` overrides the root for relocated deployments.

Features
--------
- Repository-anchored paths that are safe under cron.
- Environment-driven proxy rotation for challenge recovery.
- Named extraction thresholds shared by every extractor.
- Platform-aware Chromium flags with anti-automation hardening.

Dependencies
------------
- Internal: none (leaf module).
- External: os, re, sys, datetime, pathlib (stdlib).
- Downstream: every other module in the package.

Requirements
------------
- Python 3.10+
- Write access to the repository root.

Notes
-----
- Importing this module creates no directories; call ``ensure_directories``.
- ``IS_GITHUB_ACTIONS`` is kept only to fail fast on unsupported hosts.
- Proxy credentials are read once at import time.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# ============================================================================
# ENVIRONMENT AND PLATFORM DETECTION
# ============================================================================
REPO_ROOT = Path(__file__).resolve().parents[2]

BASE_DIR = Path(
    os.environ.get("YOUTUBE_CHARTS_BASE_DIR") or REPO_ROOT
).expanduser().resolve()

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
IS_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"
IS_LOCAL = not IS_GITHUB_ACTIONS

LOCAL_TIMEZONE = (
    os.environ.get("TZ")
    or os.environ.get("YOUTUBE_CHARTS_TZ")
    or "America/Santiago"
)

# ============================================================================
# DIRECTORIES
# ============================================================================
OUTPUT_DIR = BASE_DIR / "data"
ARCHIVE_DIR = BASE_DIR / "charts_archive" / "1_download-chart"
DATABASE_DIR = ARCHIVE_DIR / "databases"
BACKUP_DIR = ARCHIVE_DIR / "backup"
LOGS_DIR = BASE_DIR / "logs"
DEBUG_DIR = LOGS_DIR / "debug"
BROWSER_PROFILE_DIR = BASE_DIR / ".browser-profile"
LOCK_FILE = LOGS_DIR / "youtube_charts.lock"

LATEST_CSV = ARCHIVE_DIR / "latest_chart.csv"

# ============================================================================
# EXTRACTION THRESHOLDS AND RETENTION
# ============================================================================
# Every strategy is validated against these before its output is persisted, so
# a partially rendered page never overwrites good data.
MIN_ROWS_PRIMARY = 20
MIN_ROWS_SECONDARY = 10
MIN_ROWS_IDEMPOTENCY = 50

BACKUP_RETENTION_DAYS = 7
DATABASE_RETENTION_WEEKS = 52

# ============================================================================
# BROWSER IDENTITY
# ============================================================================
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

DEFAULT_ACCEPT_LANGUAGE = "en-US,en;q=0.9"
DEFAULT_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/webp,*/*;q=0.8"
)

# ============================================================================
# PROXY ROTATION
# ============================================================================
# Optional outbound proxies. A single server or a rotation list; each retry
# consumes the next entry, which is the only lever that changes the exit IP
# without discarding the profile's accumulated trust.
PROXY_SERVER = os.environ.get("YOUTUBE_CHARTS_PROXY") or ""
PROXY_LIST = [
    entry.strip()
    for entry in re.split(r"[,\n]", os.environ.get("YOUTUBE_CHARTS_PROXY_LIST", ""))
    if entry.strip()
]
PROXY_USERNAME = os.environ.get("YOUTUBE_CHARTS_PROXY_USER") or ""
PROXY_PASSWORD = os.environ.get("YOUTUBE_CHARTS_PROXY_PASS") or ""

# ============================================================================
# CANONICAL SCHEMA
# ============================================================================
CANONICAL_COLUMNS = [
    "Rank",
    "Previous Rank",
    "Track Name",
    "Artist Names",
    "Periods on Chart",
    "Views",
    "Views Raw",
    "Growth",
    "YouTube URL",
]

COLUMN_ALIASES = {
    "title": "Track Name",
    "song": "Track Name",
    "track": "Track Name",
    "track name": "Track Name",
    "track_name": "Track Name",
    "artist": "Artist Names",
    "artists": "Artist Names",
    "artist names": "Artist Names",
    "artist_names": "Artist Names",
    "rank": "Rank",
    "position": "Rank",
    "pos": "Rank",
    "previous rank": "Previous Rank",
    "previous_rank": "Previous Rank",
    "prev rank": "Previous Rank",
    "periods on chart": "Periods on Chart",
    "weeks on chart": "Periods on Chart",
    "views": "Views",
    "view count": "Views",
    "growth": "Growth",
    "youtube url": "YouTube URL",
    "url": "YouTube URL",
    "link": "YouTube URL",
    "video url": "YouTube URL",
}


# ============================================================================
# HELPERS
# ============================================================================
def ensure_directories() -> None:
    """Create every runtime directory.

    Parameters
    ----------
    None

    Returns
    -------
    None

    Notes
    -----
    Called from the entry point only, after the process lock is acquired.
    """
    for path in (OUTPUT_DIR, ARCHIVE_DIR, DATABASE_DIR, BACKUP_DIR, LOGS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def proxy_candidates() -> List[Optional[Dict[str, str]]]:
    """Proxy configurations in rotation order; ``[None]`` means direct egress."""
    servers = PROXY_LIST or ([PROXY_SERVER] if PROXY_SERVER else [])
    if not servers:
        return [None]
    candidates: List[Optional[Dict[str, str]]] = []
    for server in servers:
        settings = {"server": server}
        if PROXY_USERNAME:
            settings["username"] = PROXY_USERNAME
        if PROXY_PASSWORD:
            settings["password"] = PROXY_PASSWORD
        candidates.append(settings)
    return candidates


def get_browser_args() -> List[str]:
    """Chromium flags for the target platform.

    ``--no-sandbox`` is required on Linux hosts without user namespaces;
    the automation flag is disabled to avoid the trivial headless checks.
    """
    args = [
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process,Translate",
        "--disable-translate",
        "--disable-infobars",
        "--disable-popup-blocking",
        "--window-size=1920,1080",
        "--start-maximized",
    ]
    if IS_LINUX:
        args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            *args,
        ]
    return args


def get_week_identifier(date: Optional[datetime] = None) -> str:
    """ISO week identifier in ``YYYY-Www`` form, e.g. ``2026-W47``."""
    date = date or datetime.now()
    year, week, _ = date.isocalendar()
    return f"{year}-W{week:02d}"


def get_chart_urls(chart: str = "TopSongs", country: str = "global") -> List[str]:
    """Candidate URLs for a chart, current layout first, legacy second."""
    chart = chart.strip() or "TopSongs"
    country = country.strip() or "global"
    return [
        f"https://charts.youtube.com/charts/{chart}/{country}",
        f"https://charts.youtube.com/charts/{chart}/{country}/weekly",
    ]
