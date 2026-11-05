"""
Cache - In-Memory Cache and Shared HTTP Session Re-Exports
============================================================================
Convenience re-export module for the global in-memory cache and shared HTTP
sessions used across all API clients. The actual cache and session
factories are defined in `config.py` to avoid circular imports between
`utils` and `config`; this module simply exposes them under the `utils`
package namespace so consumers can import from a single location.

This module exists purely to break a circular dependency chain:

    config → defines cache and sessions
    utils.cache → re-exports them from config
    api_clients.* → import from utils.cache

Without this indirection, `api_clients` would need to import from
`config` directly, creating tighter coupling and making it harder to
relocate the cache/session logic later.

Features
--------
- Re-exports `get_cache` and `get_http_sessions` from `config`.
- Provides a stable import path (`utils.cache`) that decouples API clients
  from the current location of the cache implementation.
- No logic is implemented here — this module is a pure facade.

Dependencies
------------
- Internal: `..config` (get_cache, get_http_sessions).
- External: none.

Requirements
------------
- Python 3.7+
- No external packages or environment variables required.

Notes
-----
- **No side effects on import**: importing this module does not
  initialize the cache or create any HTTP session. Both `get_cache` and
  `get_http_sessions` are **factory functions**; sessions and cache state
  are created lazily on first call.
- **Shared state**: `get_cache()` returns the same in-memory cache object
  across all callers within a process, so mutations are visible globally.
  This is intentional — it lets `api_clients` avoid redundant lookups for
  the same artist against the same source. It also means tests should
  reset the cache between runs if isolation is required.
- **Session reuse**: `get_http_sessions()` returns a dict of pre-built
  `requests.Session` objects keyed by source (`"musicbrainz"`,
  `"wikidata"`, `"wikipedia"`, etc.). Reusing sessions preserves
  connection pools and TLS state, reducing per-request overhead and
  keeping rate-limit behavior consistent.
- **Circular import avoidance**: the docstring of the source module in
  `config.py` explains why the factories live there. Do not move them
  into this module without resolving the circular import first
  (`api_clients` → `utils.cache` → `config` → `api_clients`).
- The `__all__` list makes the public surface explicit and prevents
  accidental re-exports if the underlying `config` module adds new
  factories in the future.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

# ============================================================================
# RE-EXPORTS FROM CONFIG
# ============================================================================
# Imported from `config` rather than defined here to avoid a circular
# dependency: api_clients → utils.cache → config → api_clients.

from ..config import get_cache, get_http_sessions


# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = [
    "get_cache",
    "get_http_sessions",
]
