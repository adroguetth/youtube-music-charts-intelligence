"""
Config - Configuration and Shared Resources
============================================================================
Central configuration module for the artist database builder. Defines
project paths, logging setup, the in-memory cache, and the reusable HTTP
sessions used across all API clients. This module is the **root of the
dependency graph**: every other module either imports from it directly
(logger, paths, factories) or indirectly through `utils.cache`.

The module is deliberately responsible for four concerns that must stay
consistent across the pipeline:

1. **Paths** — canonical locations for chart databases, the artist
   database, and the project root, derived from this file's location so
   the pipeline works regardless of the current working directory.
2. **Logging** — a single configured logger shared by every module, with
   a format compatible with the emoji-prefixed status messages used
   throughout the pipeline.
3. **In-memory cache** — a process-wide, per-source cache to avoid
   redundant network calls within a single run.
4. **HTTP sessions** — reusable `requests.Session` objects per external
   source, preserving connection pools and per-source rate-limit state.

Features
--------
- Path derivation from `__file__` (not CWD) so scripts work from any
  working directory.
- Automatic creation of the artist database's parent directory on import
  (idempotent, safe to re-run).
- Single `setup_logging()` entry point with a `StreamHandler` on
  `sys.stdout` and a plain `%(message)s` format that preserves emoji
  prefixes.
- Module-level `logger` instance pre-configured for immediate use.
- Global `_CACHE` keyed by source × datatype
  (`musicbrainz_country`, `wikidata_genre`, `wikipedia_country`, …),
  shared across all API clients.
- Module-level `requests.Session` singletons per source
  (`wikipedia`, `wikidata`, `musicbrainz`), exposed via
  `get_http_sessions()`.

Dependencies
------------
- Internal: none (this is a leaf module at the bottom of the dependency
  graph; everything else depends on it).
- External: logging, sys, pathlib, typing, requests (stdlib + requests).

Requirements
------------
- Python 3.7+
- `requests` library installed.
- The `charts_archive/` directory structure is expected under
  `PROJECT_ROOT`, but missing directories are created on import for the
  artist database.

Notes
-----
- **Path derivation**: `PROJECT_ROOT` is computed as
  `Path(__file__).parent.parent.parent.absolute()`, which assumes this
  file lives at `<root>/scripts/2_1_country_genre/config.py`. Moving
  this file requires updating the `.parent` chain. This is intentional —
  it hardcodes the layout contract so path drift is caught at import time
  (paths resolve to wrong locations immediately) rather than silently.
- **Import-time side effect**: this module creates the parent directory
  of `ARTIST_DB_PATH` via `mkdir(parents=True, exist_ok=True)` at import
  time. This is the **only** side effect on import in the entire project
  and is idempotent (safe to run repeatedly). It exists so that
  downstream code can open the DB without a pre-flight `mkdir`.
- **Logging format is `%(message)s` only**: no timestamps, no level
  prefixes, no module names. This is deliberate — the pipeline emits
  emoji-prefixed messages (`✅`, `❌`, `📊`, …) that already carry status
  information, and adding prefixes would clutter the output. If you need
  structured logging, configure a different handler in the caller.
- **`setup_logging` is called once at import** to produce the
  module-level `logger`. Calling it again re-invokes
  `logging.basicConfig`, which is a **no-op** if the root logger is
  already configured (i.e., `basicConfig` only takes effect on the first
  call). To change the level or format after import, use
  `logger.setLevel(...)` directly rather than `setup_logging(...)`.
- **`logger` is a module-level singleton**: every module that imports
  `logger` from `config` shares the same instance. This is what makes
  emoji-prefixed logs consistent across `api_clients`, `utils`, and
  orchestration code.
- **`_CACHE` structure**: the cache is a `Dict[str, Dict[str, Any]]`
  where the top-level keys are `"<source>_<datatype>"` (e.g.,
  `"musicbrainz_country"`, `"wikipedia_genre"`). The inner dict maps
  artist name → cached value. Consumers (`api_clients/*`) read and write
  directly to `_CACHE[source_key][artist]`. The cache has no eviction
  policy and no size limit — it is expected to hold one pipeline run's
  worth of artists and be discarded at process exit.
- **`_CACHE` is not thread-safe**: it is a plain dict. The current
  pipeline is single-threaded; if parallelism is introduced later, wrap
  accesses in a `threading.Lock` or replace with a `threading.local` +
  merge strategy.
- **HTTP sessions are per-source singletons**: `_SESSION_WIKIPEDIA`,
  `_SESSION_WIKIDATA`, `_SESSION_MUSICBRAINZ` are module-level
  `requests.Session` instances. They reuse TCP connections across calls
  to the same host, which is critical for performance (avoids TLS
  handshake per request) and for rate-limit correctness (rate limits are
  usually per-connection). Sessions are shared globally; do not mutate
  their headers per-call in concurrent code.
- **No `User-Agent` is set on the sessions here**: each API client sets
  its own `User-Agent` per request (e.g., MusicBrainz requires
  `"ArtistDB/5.0 (contact@example.com)"`, Wikimedia REST requires
  `"ArtistDB/5.0"`). Centralizing them here would couple unrelated
  clients; per-request is the correct granularity.
- **No timeouts are configured on the sessions**: each call passes its
  own `timeout=` argument. Defaulting to no timeout is deliberate — a
  hung request without a timeout would block the entire pipeline, and
  forcing a default at the session level would silently mask clients that
  forgot to set one.
- **Circular import avoidance**: this module is at the bottom of the
  import graph and imports nothing from the project itself. If you add a
  project-internal import here, you will very likely create a cycle
  (`config` → `utils` → `config` or `config` → `api_clients` → `config`).
  Use `utils.cache` as the re-export layer instead of importing `config`
  from modules that `config` would need to import.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict

import requests

# ============================================================================
# PROJECT PATHS
# ============================================================================
# Project root derived from this file's location:
#   config.py -> 2_1_country_genre -> scripts -> project root (youtube-charts)
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

# Directory containing YouTube chart databases (produced by the scraper).
CHARTS_DB_DIR = (
    PROJECT_ROOT / "charts_archive" / "1_download-chart" / "databases"
)

# Output path for the artist database (this pipeline's persistent store).
ARTIST_DB_PATH = (
    PROJECT_ROOT
    / "charts_archive"
    / "2_1.countries-genres-artist"
    / "artist_countries_genres.db"
)

# Ensure the artist database's parent directory exists before any caller
# tries to open the database. Idempotent and safe to re-run.
ARTIST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Configure and return the pipeline logger.

    Configures the root logger with a `StreamHandler` on `sys.stdout` and
    a plain `%(message)s` format, then returns a module-named logger.

    Parameters
    ----------
    level : int, optional
        Logging level (default: `logging.INFO`).

    Returns
    -------
    logging.Logger
        Configured logger for the current module (`config`).

    Notes
    -----
    - `logging.basicConfig` only takes effect on the **first** call within
      a process. Subsequent calls are no-ops for the handler/format
      configuration. To change the level after import, use
      `logger.setLevel(...)` on the returned logger instead of calling
      `setup_logging` again.
    - The `%(message)s`-only format is deliberate: pipeline messages carry
      emoji prefixes (`✅`, `❌`, `📊`, …) that already encode status, so
      adding timestamps or level prefixes would clutter output.
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger(__name__)


# Module-level logger shared across the entire pipeline.
# Every module imports this instance so emoji-prefixed status messages
# stay consistent in format and destination.
logger = setup_logging()


# ============================================================================
# IN-MEMORY CACHE
# ============================================================================
# Global cache shared across all API clients to avoid redundant calls.
# Structure: { "<source>_<datatype>": { artist: cached_value } }
#   - musicbrainz_country, musicbrainz_genre
#   - wikidata_country, wikidata_genre
#   - wikipedia_country, wikipedia_genre
#
# No eviction policy and no size limit: expected to hold one pipeline
# run's worth of artists and be discarded at process exit. Not
# thread-safe (plain dict); the current pipeline is single-threaded.

_CACHE: Dict[str, Dict[str, Any]] = {
    "musicbrainz_country": {},
    "wikidata_country": {},
    "wikipedia_country": {},
    "musicbrainz_genre": {},
    "wikidata_genre": {},
    "wikipedia_genre": {},
}


# ============================================================================
# HTTP SESSIONS
# ============================================================================
# Reusable per-source sessions with connection pooling. Sessions are
# shared globally; do not mutate their headers per-call in concurrent
# code. Each API client is responsible for setting its own User-Agent and
# timeout per request.

_SESSION_WIKIPEDIA = requests.Session()
_SESSION_WIKIDATA = requests.Session()
_SESSION_MUSICBRAINZ = requests.Session()


# ============================================================================
# PUBLIC FACTORIES
# ============================================================================
def get_cache() -> Dict[str, Dict[str, Any]]:
    """
    Return the global in-memory cache dictionary.

    Returns
    -------
    dict
        The shared `_CACHE` object. Mutations are visible to all callers
        within the process.

    Notes
    -----
    - The returned object is the **actual** cache, not a copy. Callers
      are expected to mutate it directly (e.g.,
      `get_cache()["musicbrainz_country"][artist] = result`).
    - Not thread-safe; see module `Notes`.
    """
    return _CACHE


def get_http_sessions() -> Dict[str, requests.Session]:
    """
    Return the reusable per-source HTTP sessions.

    Returns
    -------
    dict of str -> requests.Session
        Dictionary keyed by source name: `"wikipedia"`, `"wikidata"`,
        `"musicbrainz"`. Values are module-level `requests.Session`
        singletons.

    Notes
    -----
    - Sessions are shared globally; do not mutate their headers per-call
      in concurrent code.
    - Each API client sets its own `User-Agent` and `timeout` per
      request; the sessions themselves carry no defaults.
    """
    return {
        "wikipedia": _SESSION_WIKIPEDIA,
        "wikidata": _SESSION_WIKIDATA,
        "musicbrainz": _SESSION_MUSICBRAINZ,
    }
