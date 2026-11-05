"""
Dictionaries - Canonical Data for Artist Country and Genre Detection
============================================================================
Package initialization and public API surface for all canonical
dictionaries used in the artist metadata detection pipeline. This package
exposes the static reference data that powers country normalization, genre
mapping to macro-genres, country-specific ranking rules, and stopword
filtering.

The package aggregates five independent dictionary modules, each targeting
a different concern in the detection pipeline:

1. `countries` — canonical country names, cities, and demonyms.
2. `genres` — raw genre labels mapped to normalized macro-genres.
3. `macro_genres` — the canonical list of valid macro-genres.
4. `country_rules` — country-specific genre priorities and ranking rules.
5. `stopwords` — stopwords used to filter false positives in genre
   extraction.

Features
--------
- Single import surface for all dictionary data.
- Explicit `__all__` export list grouped by concern for discoverability.
- Static data only — no logic, no I/O, no side effects on import.
- Deterministic: all values are constants that can be safely imported at
  module load time.

Dependencies
------------
- Internal: `.macro_genres`, `.country_rules`, `.stopwords` (sibling
  modules within the `dictionaries` package).
- External: none (pure Python data).

Requirements
------------
- Python 3.7+
- No external packages or environment variables required.

Notes
-----
- This module performs **re-exports only**; no logic is implemented here.
  Keeping it side-effect-free ensures importing `dictionaries` never
  triggers network calls, file reads, or heavy initialization.
- The `countries` and `genres` modules are not re-exported here because
  their contents are consumed via utility functions
  (`country_utils`, `genre_detector`) rather than directly. They remain
  importable via `from dictionaries.countries import ...` when needed.
- `MACRO_GENRES` and `GENERIC_MACROS` are the authoritative source of
  truth for valid genre targets; any macro-genre appearing in
  `COUNTRY_GENRE_PRIORITY` or `COUNTRY_SPECIFIC_RULES` must exist in
  `MACRO_GENRES` to avoid silent ranking failures downstream.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

# ============================================================================
# MACRO GENRES — CANONICAL GENRE TARGETS
# ============================================================================
from .macro_genres import GENERIC_MACROS, MACRO_GENRES

# ============================================================================
# COUNTRY RULES — PRIORITIES AND RANKING RULES
# ============================================================================
from .country_rules import (
    COUNTRY_GENRE_PRIORITY,
    COUNTRY_SPECIFIC_RULES,
    DEFAULT_GENRE_PRIORITY,
)

# ============================================================================
# STOPWORDS — FALSE-POSITIVE FILTERING
# ============================================================================
from .stopwords import GENRE_STOPWORDS


# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = [
    # --- Macro genres (canonical targets) ---
    "MACRO_GENRES",
    "GENERIC_MACROS",
    # --- Country rules (priorities and ranking) ---
    "COUNTRY_GENRE_PRIORITY",
    "COUNTRY_SPECIFIC_RULES",
    "DEFAULT_GENRE_PRIORITY",
    # --- Stopwords (false-positive filtering) ---
    "GENRE_STOPWORDS",
]
