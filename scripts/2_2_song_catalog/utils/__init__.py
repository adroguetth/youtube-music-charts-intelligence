"""
Utils - Reusable Utilities for Song Catalog Enrichment
============================================================================
Package initialization and public API surface for the utility modules used
by the song catalog builder.

This package aggregates two independent utility modules:
1. `artist_parser` — Artist name normalization and list splitting.
2. `db_utils` — SQLite schema management, statistics, and artist lookup.

The separation allows the utility logic to be tested and reused
independently of the main ETL pipeline.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from .artist_parser import normalize_name, parse_artist_list
from .db_utils import (
    get_catalog_statistics,
    initialize_target_schema,
    load_artist_lookup,
)

__all__ = [
    # Artist parser
    "normalize_name",
    "parse_artist_list",
    # DB utils
    "initialize_target_schema",
    "get_catalog_statistics",
    "load_artist_lookup",
]
