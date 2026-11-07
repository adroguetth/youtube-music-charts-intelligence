"""
API Clients - External Data Source Integrations
============================================================================
Package initialization and public API surface for all external data source
clients used in the artist metadata detection pipeline. This package
exposes cached accessors and fallback AI clients that resolve country of
origin and primary musical genre for a given artist name.

The package aggregates seven independent clients, each targeting a different
data source with different trade-offs (coverage, latency, reliability):

1. MusicBrainz — structured open music database (country + genre).
2. Wikidata — structured knowledge base (country + genre).
3. Wikipedia — free-text encyclopedia parsed via infobox and summary.
4. DeepSeek — primary AI fallback (country + genre).
5. GPT-OSS — secondary AI fallback (via Groq, 120B model).
6. Qwen — tertiary AI fallback (via Groq, 27B model, Asian specialist).
7. Muse Spark (Meta) — final AI fallback (country + genre, deep reasoning).

Features
--------
- Single import surface for all detection clients.
- Cached accessors for network-bound sources (MusicBrainz, Wikidata,
  Wikipedia) to avoid redundant requests.
- Layered fallback strategy: structured sources first, then AI fallbacks
  in increasing order of cost (DeepSeek → GPT-OSS → Qwen → Muse).
- Explicit `__all__` export list grouped by source for discoverability.

Dependencies
------------
- Internal: `.musicbrainz`, `.wikidata`, `.wikipedia`, `.deepseek`,
  `.gpt_oss`, `.qwen`, `.muse` (sibling modules within the `apis` package).
- External: none directly (re-export only; imports are resolved by each
  sibling module).

Requirements
------------
- Python 3.7+
- All dependencies required by the sibling modules must be installed
  (requests, groq SDK, openai SDK, etc.) and their corresponding API keys
  set as environment variables.

Notes
-----
- This module performs **re-exports only**; no logic is implemented here.
  Keeping it side-effect-free ensures importing `apis` never triggers
  network calls or API initialization.
- The `_get_deepseek_client` helper is re-exported with a leading
  underscore for testability, but is not part of the stable public API.
- The layering order (DeepSeek → GPT-OSS → Qwen → Muse) reflects increasing
  cost per call and should be preserved by consumers when chaining fallbacks.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

# ============================================================================
# MUSICBRAINZ — STRUCTURED MUSIC DATABASE
# ============================================================================
from .musicbrainz import (
    extract_genre_from_musicbrainz,
    search_musicbrainz_country_cached,
    search_musicbrainz_genre_cached,
)

# ============================================================================
# WIKIDATA — STRUCTURED KNOWLEDGE BASE
# ============================================================================
from .wikidata import (
    search_wikidata_country_cached,
    search_wikidata_genre_cached,
)

# ============================================================================
# WIKIPEDIA — FREE-TEXT ENCYCLOPEDIA (INFOBOX + SUMMARY)
# ============================================================================
from .wikipedia import (
    search_wikipedia_infobox_country_cached,
    search_wikipedia_infobox_genre_cached,
    search_wikipedia_summary_country_cached,
    search_wikipedia_summary_genre_cached,
)

# ============================================================================
# AI FALLBACKS — DEEPSEEK → GPT-OSS → QWEN → MUSE SPARK
# ============================================================================
from .deepseek import _get_deepseek_client, search_deepseek_fallback

# Opción A: El archivo se llama gpt_oss.py, pero la función interna sigue llamándose search_groq_fallback
from .gpt_oss import search_groq_fallback

from .qwen import search_qwen_fallback
from .muse import search_muse_fallback


# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = [
    # --- MusicBrainz ---
    "search_musicbrainz_country_cached",
    "search_musicbrainz_genre_cached",
    "extract_genre_from_musicbrainz",
    # --- Wikidata ---
    "search_wikidata_country_cached",
    "search_wikidata_genre_cached",
    # --- Wikipedia ---
    "search_wikipedia_infobox_country_cached",
    "search_wikipedia_summary_country_cached",
    "search_wikipedia_infobox_genre_cached",
    "search_wikipedia_summary_genre_cached",
    # --- DeepSeek (primary AI fallback) ---
    "search_deepseek_fallback",
    "_get_deepseek_client",
    # --- GPT-OSS via Groq (secondary AI fallback) ---
    "search_groq_fallback",  # <-- Mantenemos el nombre original
    # --- Qwen via Groq (tertiary AI fallback) ---
    "search_qwen_fallback",
    # --- Muse Spark / Meta (final AI fallback) ---
    "search_muse_fallback",
]
