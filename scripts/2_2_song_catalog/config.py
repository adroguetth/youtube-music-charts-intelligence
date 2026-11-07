"""
Config - Paths and Logging Configuration
============================================================================
Centralized configuration for the song catalog builder (Script 2.2).

This module resolves all repository-relative paths to absolute paths based
on the location of this file. This ensures that the script works identically
whether it is run from the repository root, from the `scripts/` directory,
or via a GitHub Actions workflow.

Features
--------
- Absolute path resolution (no relative path surprises).
- Automatic directory creation for the target database.
- Standardized logger configuration (stdout, formatted).
- Single source of truth for database names and directories.

Dependencies
------------
- External: logging, pathlib, sys (stdlib).

Requirements
------------
- Python 3.7+

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import logging
import sys
from pathlib import Path

# ============================================================================
# REPOSITORY ROOT RESOLUTION
# ============================================================================
# We assume this file lives at:
# <repo_root>/scripts/2_2_build_song_catalog/config.py
#
# Therefore, parents[0] = 2_2_build_song_catalog
#             parents[1] = scripts
#             parents[2] = <repo_root>

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ============================================================================
# DIRECTORY AND FILE PATHS
# ============================================================================
# Source: Where weekly chart databases are stored (Script 1 output)
SOURCE_DIR = REPO_ROOT / "charts_archive" / "1_download-chart" / "databases"

# Artist metadata database path (country + macro-genre per artist)
# Produced by Script 2.1
ARTIST_DB_PATH = (
    REPO_ROOT 
    / "charts_archive" 
    / "2_1.countries-genres-artist" 
    / "artist_countries_genres.db"
)

# Target: Where the canonical song catalog will be maintained
TARGET_DIR = REPO_ROOT / "charts_archive" / "2_2.build-song-catalog"
TARGET_DB_NAME = "build_song.db"
TARGET_DB_PATH = TARGET_DIR / TARGET_DB_NAME

# ============================================================================
# DIRECTORY INITIALIZATION
# ============================================================================
# Ensure the target directory exists before any connection attempt
TARGET_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
# Configure a module-level logger. We avoid `basicConfig` here to prevent
# side effects if this module is imported by another script that already
# has its own logging configuration.

logger = logging.getLogger("song_catalog_builder")

# Only configure the logger if it hasn't been configured yet
if not logger.handlers:
    logger.setLevel(logging.INFO)
    
    # Formatter without timestamp to keep output clean (the timestamp is
    # already printed in the header of the ETL pipeline)
    formatter = logging.Formatter('%(message)s')
    
    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Prevent propagation to the root logger to avoid duplicate messages
    logger.propagate = False

# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = [
    "REPO_ROOT",
    "SOURCE_DIR",
    "ARTIST_DB_PATH",
    "TARGET_DIR",
    "TARGET_DB_NAME",
    "TARGET_DB_PATH",
    "logger",
]
