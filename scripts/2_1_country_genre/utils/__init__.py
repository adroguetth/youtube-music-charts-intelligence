"""
Utilities - Shared Infrastructure for the Artist Database Builder
============================================================================
Package initialization and public API surface for all utility modules used
across the artist database builder. This package exposes the shared
infrastructure that every other module depends on: text processing, HTTP
session and cache management, SQLite operations, artist name parsing, and
country normalization.

The package aggregates five independent utility modules, each targeting a
different concern in the pipeline:

1. `text_utils` — text normalization, artist name variations, prefix
   removal, script detection (Latin/CJK/Cyrillic/Arabic/etc.).
2. `cache` — in-memory cache and shared HTTP sessions (per-source) to
   avoid redundant requests.
3. `db_utils` — SQLite database creation, artist lookup, insertion, and
   chart database discovery.
4. `artist_parser` — splitting collaborator strings into individual artist
   names.
5. `country_utils` — validation and normalization of country names against
   the canonical dictionary.

Features
--------
- Single import surface for all shared utilities.
- Explicit `__all__` export list grouped by module for discoverability.
- Session reuse via `get_http_sessions()` reduces TLS handshake overhead
  and respects per-source rate-limit policies.
- Shared cache via `get_cache()` ensures the same artist is not re-queried
  against the same source within a single run.

Dependencies
------------
- Internal: `.text_utils`, `.cache`, `.db_utils`, `.artist_parser`,
  `.country_utils` (sibling modules within the `utils` package).
- External: none directly (re-export only; imports are resolved by each
  sibling module).

Requirements
------------
- Python 3.7+
- All dependencies required by the sibling modules must be installed
  (requests, sqlite3, etc.).

Notes
-----
- This module performs **re-exports only**; no logic is implemented here.
  Keeping it side-effect-free ensures importing `utils` never triggers
  network calls, database creation, or cache initialization. Note that
  `cache.get_http_sessions()` and `cache.get_cache()` are **factories**,
  not module-level singletons, so importing them is safe.
- `db_utils.create_database()` and `db_utils.insert_artist()` have
  filesystem side effects when **called**, but importing the module does
  not. Consumers should invoke them explicitly at the point where a new
  database is needed.
- `country_utils.validate_and_normalize_country()` is the single entry
  point for country normalization across the pipeline; it depends on
  `dictionaries.countries.COUNTRIES_CANONICAL` and
  `dictionaries.countries.VARIANT_TO_COUNTRY`.
- `text_utils.detect_script_from_name()` is used to skip Latin-centric
  processing for non-Latin artist names and to route them through
  script-aware handling.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

# ============================================================================
# TEXT UTILS — NORMALIZATION AND NAME VARIATIONS
# ============================================================================
from .text_utils import (
    detect_script_from_name,
    generate_all_variations,
    generate_name_variations,
    normalize_text,
    remove_artist_prefixes,
)

# ============================================================================
# CACHE — IN-MEMORY CACHE AND SHARED HTTP SESSIONS
# ============================================================================
from .cache import get_cache, get_http_sessions

# ============================================================================
# DB UTILS — SQLITE OPERATIONS
# ============================================================================
from .db_utils import (
    artist_in_database,
    count_artists_in_database,
    create_database,
    get_artists_from_chart_db,
    get_latest_chart_database,
    insert_artist,
)

# ============================================================================
# ARTIST PARSER — COLLABORATOR STRING SPLITTING
# ============================================================================
from .artist_parser import split_artists

# ============================================================================
# COUNTRY UTILS — COUNTRY VALIDATION AND NORMALIZATION
# ============================================================================
from .country_utils import validate_and_normalize_country


# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = [
    # --- text_utils (normalization and name variations) ---
    "normalize_text",
    "generate_name_variations",
    "remove_artist_prefixes",
    "generate_all_variations",
    "detect_script_from_name",
    # --- cache (in-memory cache and shared HTTP sessions) ---
    "get_cache",
    "get_http_sessions",
    # --- db_utils (SQLite operations) ---
    "create_database",
    "artist_in_database",
    "insert_artist",
    "count_artists_in_database",
    "get_latest_chart_database",
    "get_artists_from_chart_db",
    # --- artist_parser (collaborator string splitting) ---
    "split_artists",
    # --- country_utils (country validation and normalization) ---
    "validate_and_normalize_country",
]
