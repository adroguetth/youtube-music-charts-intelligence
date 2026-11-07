"""
Config - Paths, Constants and Logging Configuration
============================================================================
Centralized configuration module for the song catalog builder (Script 2.2).

This module defines all filesystem paths, filename patterns, and the shared
logger instance used across the `2_2_build_song_catalog` package.

Features
--------
- Repository-relative paths: ensures consistent behavior across local
  development and GitHub Actions CI/CD environments.
- Directory auto-creation: creates the target directory structure if it
  doesn't exist.
- Centralized logging: provides a single configured `logger` instance that
  can be imported by all other modules.
- Filename regex: compiled pattern for identifying weekly YouTube Charts
  databases.

Dependencies
------------
- External: logging, re, sys, pathlib (stdlib).

Requirements
------------
- Python 3.7+

Notes
-----
- The paths are resolved dynamically based on the location of this file
  (`__file__`), making the script fully portable.
- The `logger` is configured to output to `sys.stdout` to ensure compatibility
  with GitHub Actions log capture.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import logging
import re
import sys
from pathlib import Path


# ============================================================================
# DIRECTORY STRUCTURE CONFIGURATION
# ============================================================================
# Determine repository root (two levels up from this file)
REPO_ROOT: Path = Path(__file__).parent.parent.parent

# Source: Where weekly chart databases are stored (Script 1 output)
SOURCE_DIR: Path = REPO_ROOT / "charts_archive" / "1_download-chart" / "databases"

# Artist metadata database path (country + macro-genre per artist, Script 2.1 output)
ARTIST_DB_PATH: Path = (
    REPO_ROOT / "charts_archive" / "2_1.countries-genres-artist" / "artist_countries_genres.db"
)

# Target: Where the canonical song catalog will be maintained
TARGET_DIR: Path = REPO_ROOT / "charts_archive" / "2_2.build-song-catalog"
TARGET_DB_NAME: str = "build_song.db"


# ============================================================================
# REGEX PATTERNS
# ============================================================================
# Regex pattern for YouTube Charts weekly database filenames
# Format: youtube_charts_YYYY-Www.db (e.g., youtube_charts_2026-W15.db)
DB_FILENAME_PATTERN: re.Pattern = re.compile(r"youtube_charts_20\d{2}-W\d{1,2}\.db$")


# ============================================================================
# DIRECTORY INITIALIZATION
# ============================================================================
# Create target directory structure if it doesn't exist
# This is safe to execute at import time as it uses `parents=True`
TARGET_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
def _setup_logger() -> logging.Logger:
    """
    Configure and return the shared logger instance.

    The logger is configured to write to `sys.stdout` with a simple message
    format (no timestamps) to match the style of Script 2.1 and ensure
    readability in CI/CD environments.

    Returns
    -------
    logging.Logger
        Configured logger instance named '2_2_catalog'.
    """
    log = logging.getLogger("2_2_catalog")
    
    # Prevent adding multiple handlers if the module is reloaded
    if not log.handlers:
        log.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(message)s'))
        log.addHandler(handler)
        log.propagate = False
        
    return log


# Shared logger instance for the entire package
logger: logging.Logger = _setup_logger()


# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = [
    "REPO_ROOT",
    "SOURCE_DIR",
    "ARTIST_DB_PATH",
    "TARGET_DIR",
    "TARGET_DB_NAME",
    "DB_FILENAME_PATTERN",
    "logger",
]
