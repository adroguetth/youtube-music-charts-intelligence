"""
Artist Metadata Enrichment - Country and Genre Detection
============================================================================
Top-level package initialization and public API surface for the artist
metadata enrichment module. This package enriches chart artist records with
geographic and genre metadata resolved from multiple sources, in a layered
fallback cascade:

1. **Structured sources** (in order):
   - MusicBrainz (country + genre tags).
   - Wikidata (P27/P19 country, P136 genre).
   - Wikipedia (infobox + summary parsing).
2. **AI fallbacks** (in increasing cost, only when structured sources miss):
   - DeepSeek (primary AI fallback).
   - Groq / Llama 3.3 70B (secondary AI fallback).
   - Muse Spark / Meta (final AI fallback, deep reasoning).

This package is designed to be imported by the main orchestration script
(`main.py`), which drives the pipeline end-to-end.

Features
--------
- Single import surface for the whole enrichment pipeline: configuration,
  logging, cache and HTTP session factories, country detection, genre
  detection, genre normalization, and country validation.
- Config re-exports (`PROJECT_ROOT`, `CHARTS_DB_DIR`, `ARTIST_DB_PATH`,
  `setup_logging`, `get_cache`, `get_http_sessions`) so consumers do not
  need to import from `config` directly.
- Country detection entry point (`search_country`) and genre detection
  entry point (`search_artist_genre`) exposed at the package root.
- Genre normalization (`normalize_genre`) and country validation
  (`validate_and_normalize_country`) exposed for direct use.
- Zero side effects on import: no network calls, no database creation, no
  logging initialization. All factories are lazy.

Dependencies
------------
- Internal: `.config`, `.country_detector`, `.genre_detector`,
  `.utils.country_utils`.
- External: none directly (re-export only; imports are resolved by each
  submodule).

Requirements
------------
- Python 3.7+
- Environment variables for AI fallbacks (`DEEPSEEK_API_KEY`,
  `GROQ_API_KEY`, `MODEL_API_KEY`) must be set for those fallbacks to
  activate; the pipeline degrades gracefully when they are absent.
- Network access to `musicbrainz.org`, `wikidata.org`, and `wikipedia.org`.

Notes
-----
- **Re-exports only**: this module implements no logic. Keeping it
  side-effect-free ensures that `import artist_metadata` (or whatever the
  package name is) never triggers network calls, DB creation, or logging
  initialization. Consumers explicitly call `setup_logging()` when they
  want logging configured.
- **`setup_logging` is a function, not an import-time side effect**: unlike
  many packages that configure the root logger at import time, this one
  requires the caller to invoke `setup_logging()` explicitly. This gives
  tests and embedding applications full control over logging
  configuration.
- **`get_cache` and `get_http_sessions` are factories**, not singletons:
  the underlying cache and sessions are created lazily on first call. See
  `utils/cache.py` for details.
- **Import surface stability**: `__all__` is the public contract. Adding
  entries is safe; removing or renaming entries is **breaking** for
  downstream orchestration code. Internal helpers not listed in `__all__`
  are not part of the public API.
- **Layer separation**: `search_country` and `search_artist_genre` are the
  only entry points into the detection cascade. They internally orchestrate
  the structured-source → AI-fallback order and the caching layers. Do not
  invoke individual source clients directly from orchestration code; doing
  so bypasses caching and rate limiting.
- **`validate_and_normalize_country` lives in `utils`**, not in this
  package. It is re-exported here for convenience because orchestration
  code often needs it alongside `search_country`. Its implementation and
  invariants are documented in `utils/country_utils.py`.
- **No version pinning here**: this module does not expose `__version__`;
  version metadata is expected to live in `pyproject.toml` or
  `setup.cfg` at the project root.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

# ============================================================================
# CONFIGURATION AND INFRASTRUCTURE
# ============================================================================
from .config import (
    ARTIST_DB_PATH,
    CHARTS_DB_DIR,
    PROJECT_ROOT,
    get_cache,
    get_http_sessions,
    setup_logging,
)

# ============================================================================
# DETECTION ENTRY POINTS
# ============================================================================
from .country_detector import search_country
from .genre_detector import normalize_genre, search_artist_genre

# ============================================================================
# SHARED UTILITIES
# ============================================================================
# validate_and_normalize_country now lives in `utils`; re-exported here
# because orchestration code frequently needs it alongside `search_country`.
from .utils.country_utils import validate_and_normalize_country


# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = [
    # --- Configuration and infrastructure ---
    "PROJECT_ROOT",
    "CHARTS_DB_DIR",
    "ARTIST_DB_PATH",
    "setup_logging",
    "get_cache",
    "get_http_sessions",
    # --- Detection entry points ---
    "search_country",
    "search_artist_genre",
    "normalize_genre",
    # --- Shared utilities ---
    "validate_and_normalize_country",
]
