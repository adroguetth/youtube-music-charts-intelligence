"""
Config - Paths, Environment Variables and Logging Configuration
============================================================================
Centralized configuration module for the chart enrichment pipeline (Script 3).

This module defines all filesystem paths, environment variables, and the
shared logger instance used across the `3_enrich_chart_data` package.

Features
--------
- Repository-relative paths: ensures consistent behavior across local
  development and GitHub Actions CI/CD environments.
- Environment variable loading: reads `YOUTUBE_API_KEY` and detects if the
  pipeline is running in a CI/CD environment.
- Directory auto-creation: creates the target output directory structure if
  it doesn't exist.
- Centralized logging: provides a single configured `logger` instance that
  can be imported by all other modules.

Dependencies
------------
- External: logging, os, sys, pathlib (stdlib).

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
import os
import sys
from pathlib import Path


# ============================================================================
# DIRECTORY STRUCTURE CONFIGURATION
# ============================================================================
# Determine repository root (two levels up from this file)
REPO_ROOT: Path = Path(__file__).parent.parent.parent

# Input: most recent weekly chart database (Script 1 output)
INPUT_DB_DIR: Path = REPO_ROOT / "charts_archive" / "1_download-chart" / "databases"

# Local song catalog database (Script 2.2 output)
SONG_CATALOG_DB_PATH: Path = (
    REPO_ROOT / "charts_archive" / "2_2.build-song-catalog" / "build_song.db"
)

# Output: enriched database written here
OUTPUT_DIR: Path = REPO_ROOT / "charts_archive" / "3_enrich-chart-data"

# Create output directory structure if it doesn't exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================
# Optional: set YOUTUBE_API_KEY env var to enable the API layer
YOUTUBE_API_KEY: str = os.environ.get("YOUTUBE_API_KEY", "")

# Detect GitHub Actions environment to suppress interactive prompts
IN_GITHUB_ACTIONS: bool = os.environ.get("GITHUB_ACTIONS") == "true"


# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
def _setup_logger() -> logging.Logger:
    """
    Configure and return the shared logger instance.

    The logger is configured to write to `sys.stdout` with a simple message
    format (no timestamps) to match the style of Scripts 2.1 and 2.2 and
    ensure readability in CI/CD environments.

    Returns
    -------
    logging.Logger
        Configured logger instance named '3_enrich_chart_data'.
    """
    log = logging.getLogger("3_enrich_chart_data")

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
    "INPUT_DB_DIR",
    "SONG_CATALOG_DB_PATH",
    "OUTPUT_DIR",
    "YOUTUBE_API_KEY",
    "IN_GITHUB_ACTIONS",
    "logger",
]
