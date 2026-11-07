"""
Config - Paths and Logging for Song Catalog Builder
============================================================================
Centralized configuration for the song catalog builder pipeline.

This module is the single source of truth for all filesystem paths and
logging setup. It guarantees that both the ETL pipeline (`migrate.py`) and
the resolution logic (`resolver.py`) operate on the same directories and
share a consistent log format.

Directory Structure Assumptions:
    project_root/
    ├── charts_archive/
    │   ├── 1_download-chart/
    │   │   └── databases/              <-- SOURCE_DIR
    │   ├── 2_1.countries-genres-artist/
    │   │   └── artist_countries_genres.db  <-- ARTIST_DB_PATH
    │   └── 2_2.build-song-catalog/     <-- TARGET_DIR
    │       └── build_song.db           <-- TARGET_DB_NAME

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import logging
import sys
from pathlib import Path

# ============================================================================
# PATH RESOLUTION
# ============================================================================
# Determine the repository root dynamically.
# Assuming this file is at: project_root/scripts/2_2_build_song_catalog/config.py
# -> parents[0] = 2_2_build_song_catalog
# -> parents[1] = scripts
# -> parents[2] = project_root
_REPO_ROOT = Path(__file__).resolve().parents[2]

# 1. Source directory (Input from Script 1)
SOURCE_DIR: Path = _REPO_ROOT / "charts_archive" / "1_download-chart" / "databases"

# 2. Artist Metadata Database (Input from Script 2.1)
ARTIST_DB_PATH: Path = _REPO_ROOT / "charts_archive" / "2_1.countries-genres-artist" / "artist_countries_genres.db"

# 3. Target Directory and Database (Output of Script 2.2)
TARGET_DIR: Path = _REPO_ROOT / "charts_archive" / "2_2.build-song-catalog"
TARGET_DB_NAME: str = "build_song.db"

# Ensure the target directory exists safely upon import.
# This prevents "unable to open database file" errors during SQLite connection.
TARGET_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
def setup_logger(name: str = "song_catalog") -> logging.Logger:
    """
    Configure and return a centralized logger.
    
    Outputs to stdout with a clean format suitable for GitHub Actions
    and local terminal execution.

    Parameters
    ----------
    name : str
        Name of the logger instance.

    Returns
    -------
    logging.Logger
        Configured logger object.
    """
    _logger = logging.getLogger(name)
    
    # Only configure if it doesn't have handlers yet (prevents duplicate logs)
    if not _logger.handlers:
        _logger.setLevel(logging.INFO)
        
        # Standard output handler
        handler = logging.StreamHandler(sys.stdout)
        
        # Format: "2026-11-07 12:00:00 | INFO | message"
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        _logger.addHandler(handler)
        
        # Prevent propagation to the root logger to avoid double logging
        _logger.propagate = False
        
    return _logger

# Export the singleton logger instance for use across the package
logger = setup_logger()

# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = [
    "SOURCE_DIR",
    "ARTIST_DB_PATH",
    "TARGET_DIR",
    "TARGET_DB_NAME",
    "logger",
]
