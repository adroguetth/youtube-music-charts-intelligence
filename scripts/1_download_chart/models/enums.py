"""
Domain Enumerations
============================================================================
Enumerations shared across the pipeline: the chart identifiers accepted by
charts.youtube.com and the process exit codes consumed by cron and alerting.

Features
--------
- String-valued chart identifiers safe for URL composition.
- Integer exit codes that distinguish retryable from terminal outcomes.

Dependencies
------------
- Internal: none (leaf module).
- External: enum (stdlib).
- Downstream: cli, __main__.

Requirements
------------
- Python 3.10+

Notes
-----
- ``ExitCode.CAPTCHA_BLOCKED`` (21) is retryable by cron; it does not mean the
  run is broken, only that every egress in the rotation was challenged.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

from enum import Enum, IntEnum


# ============================================================================
# CHART IDENTIFIERS
# ============================================================================
class ChartType(str, Enum):
    """Chart identifiers accepted by charts.youtube.com."""

    TOP_SONGS = "TopSongs"
    TOP_ARTISTS = "TopArtists"
    TOP_VIDEOS = "TopVideos"


# ============================================================================
# EXIT CODES
# ============================================================================
class ExitCode(IntEnum):
    """Process exit codes consumed by the cron wrapper and alerting."""

    OK = 0
    GENERIC_ERROR = 1
    IDEMPOTENT_SKIP = 10
    NO_DATA = 20
    CAPTCHA_BLOCKED = 21
    LOCK_BUSY = 30
    DEPS_MISSING = 40
    TIMEOUT = 50
