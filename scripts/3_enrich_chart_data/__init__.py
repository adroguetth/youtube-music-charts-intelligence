"""
YouTube Charts Data Enrichment Pipeline - Package Initialization
============================================================================
This package enriches weekly chart data with YouTube metadata and catalog
information (country, macro-genre, and song_id).

The package is structured into the following submodules:
- `config`: Paths, environment variables, and logging configuration.
- `metadata`: Three-layer metadata retrieval (API → Selenium → yt-dlp).
- `utils`: Helper functions for database operations.

Features
--------
- Three-layer metadata fallback system.
- Robust SQLite integration for reading chart data and writing enriched data.
- Idempotent output generation: re-running the pipeline yields exactly one
  row per chart entry.

Dependencies
------------
- Internal: config, metadata, utils.
- External: sqlite3, subprocess, sys (stdlib).

Requirements
------------
- Python 3.7+

Notes
-----
- Importing this package does not trigger the enrichment pipeline. You must
  explicitly call `main()` (or run `python -m scripts.3_enrich_chart_data`)
  to start the process.
- The version string follows Semantic Versioning (SemVer).

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

__version__ = "1.0.0"

# ============================================================================
# PUBLIC API
# ============================================================================
# Expose the main orchestration function from the metadata module so callers
# can import it directly without knowing the internal folder structure.
from .metadata import fetch_video_metadata

__all__ = [
    "__version__",
    "fetch_video_metadata",
]
