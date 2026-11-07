"""
YouTube Charts Song Catalog Builder - Package Initialization
============================================================================
This package automates the creation and maintenance of a canonical song
catalog by cross-referencing YouTube Charts weekly databases with the
artist metadata database (produced by Script 2.1).

The package is structured into the following submodules:
- `config`: Paths, constants, and logging configuration.
- `migrate`: Core ETL pipeline (orchestrator).
- `resolver`: Collaboration weight algorithm for multi-artist tracks.
- `dictionaries`: Static lookup tables (continents, genre hierarchies, etc.).
- `utils`: Helper functions (DB operations, artist parsing).

Features
--------
- Idempotent execution: safe to run multiple times without duplicating data.
- Two-phase resolution: repairs historical incomplete records and inserts
  new songs from the latest chart.
- Graceful error handling: individual record failures do not abort the pipeline.

Dependencies
------------
- Internal: config, migrate, resolver, utils, dictionaries.
- External: sqlite3, pathlib, re, sys (stdlib).

Requirements
------------
- Python 3.7+

Notes
-----
- Importing this package does not trigger the ETL pipeline. You must
  explicitly call `migrate_data()` to start the process.
- The version string follows Semantic Versioning (SemVer).

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

__version__ = "1.0.0"

# ============================================================================
# PUBLIC API
# ============================================================================
# Expose the main ETL pipeline and the catalog summary function so they can
# be imported directly from the package root.
from .migrate import migrate_data
from .catalog_summary import list_catalog_summary

__all__ = [
    "__version__",
    "migrate_data",
    "list_catalog_summary",
]
