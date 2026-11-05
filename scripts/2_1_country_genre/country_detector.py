"""
Country Detector - Multi-Source Artist Country Resolution
============================================================================
Orchestration module for resolving an artist's country of origin. Implements
the layered fallback cascade that drives the country half of the metadata
enrichment pipeline: structured sources first (MusicBrainz → Wikidata →
Wikipedia), then AI fallbacks in increasing cost order (DeepSeek → Groq →
Muse Spark).

The module itself contains no per-source logic — that lives in the
`apis.*` clients. Its only responsibility is **ordering, iteration over
name variations, rate limiting, and source attribution** for the returned
result.

Features
--------
- Iterates over typographic name variations (via `generate_all_variations`)
  to maximize match rates against each structured source.
- Per-source variation caps to bound network cost:
  - MusicBrainz: 3 variations.
  - Wikidata: 3 variations.
  - Wikipedia EN: 3 variations (summary + infobox per variation).
  - Wikipedia other languages: 2 variations per language.
- Script-aware Wikipedia fallback: the detected script's language edition
  is tried first, followed by a fixed priority list of common editions.
- Layered AI fallback (DeepSeek → Groq → Muse Spark) invoked only when all
  structured sources miss.
- Explicit rate limiting between source families (`time.sleep`) and per
  language iteration for Wikipedia.
- Source attribution: the returned source string records both the winning
  source and, when applicable, the name variation that matched
  (`"MusicBrainz (var: Beyonce)"`).

Dependencies
------------
- Internal: `.config` (logger), `.utils.text_utils`
  (generate_all_variations, detect_script_from_name), `.apis.musicbrainz`,
  `.apis.wikidata`, `.apis.wikipedia`, `.apis.deepseek`, `.apis.groq`,
  `.apis.muse`.
- External: time, typing (stdlib).

Requirements
------------
- Python 3.7+
- Network access to MusicBrainz, Wikidata, and Wikipedia.
- Optional: `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `MODEL_API_KEY` for the
  AI fallbacks. Absence of these keys degrades gracefully (the
  corresponding fallback returns `None`).

Notes
-----
- **Caching is inherited, not implemented here**: every `search_*_cached`
  function caches results (including negative results) internally via
  `config.get_cache()`. This orchestrator can therefore be called
  repeatedly for the same artist without incurring duplicate network
  calls. **Do not add an external cache here** — it would duplicate the
  per-source caches and obscure the source attribution logic.
- **Rate limiting is coarse-grained and linear**: `time.sleep(0.8)` after
  MusicBrainz, `time.sleep(0.3)` after Wikipedia EN, `time.sleep(0.2)`
  per language in the non-English Wikipedia loop. These delays are tuned
  for MusicBrainz's 1 req/s limit and Wikimedia's burst limits. They are
  **not adaptive** — a large batch will be slow. The trade-off favors
  robustness over speed; increasing concurrency would require per-source
  rate-limit tokens, which is out of scope for this module.
- **Variation caps are deliberate**: `variations[:3]` for structured
  sources and `variations[:2]` for non-English Wikipedia. Without caps,
  a name with 15 variations × 12 languages would trigger 180 Wikipedia
  requests per artist. The caps bound the worst case to
  `3 + 3 + 3×2 + 12×2 = 36` structured requests plus up to 3 AI calls.
- **The winning source string includes the variation only when it differs
  from the original**: if `var == artist`, the info suffix is empty. This
  keeps the common case (`"MusicBrainz"`) clean while preserving
  traceability for fuzzy matches (`"MusicBrainz (var: Beyonce)"`).
- **Wikipedia EN is tried before other languages**: the English edition
  has the highest coverage for globally charting artists. The non-English
  pass is a fallback for artists whose English page is missing or whose
  name has non-Latin script.
- **Non-English language priority order**: detected script language first
  (via `detect_script_from_name`), then a fixed list
  `['es', 'pt', 'fr', 'de', 'it', 'hi', 'ko', 'ja', 'zh', 'ar', 'tr', 'ru']`.
  The fixed list reflects typical chart demographics in the target
  dataset (Chilean/Latin American charts, with broad coverage of major
  music markets). Adjusting this list is a data-driven decision, not a
  code-quality one.
- **AI fallbacks are not variation-aware**: DeepSeek, Groq, and Muse
  Spark are called with the **original** artist name only. Variations are
  a typographic-matching tool for exact-match sources; AI models already
  handle minor spelling differences natively. Sending variations to the
  AIs would multiply cost without meaningful benefit.
- **AI fallbacks are not chained on partial results**: if DeepSeek
  returns a country, the pipeline short-circuits and Groq/Muse are not
  called. This is intentional — once we have a country, additional AI
  calls add cost without improving confidence.
- **Return contract**: `(country, source)` where `country` is `None` when
  no source matched and `source` is `"Not found"` in that case. Callers
  should treat `country is None` as "unresolved" and can log the source
  string for diagnostics.
- **Idempotent and side-effect-free within the process**: no global state
  is mutated by this module. All caching happens inside the per-source
  clients. The only observable side effect is network I/O and the
  corresponding cache writes in `config._CACHE`.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import time
from typing import Optional, Tuple

from .apis.deepseek import search_deepseek_fallback
from .apis.groq import search_groq_fallback
from .apis.musicbrainz import search_musicbrainz_country_cached
from .apis.muse import search_muse_fallback
from .apis.wikidata import search_wikidata_country_cached
from .apis.wikipedia import (
    search_wikipedia_infobox_country_cached,
    search_wikipedia_summary_country_cached,
)
from .config import logger
from .utils.text_utils import detect_script_from_name, generate_all_variations

# ============================================================================
# CONSTANTS
# ============================================================================
_MAX_VARIATIONS_STRUCTURED = 3
_MAX_VARIATIONS_WIKIPEDIA_OTHER = 2

_MUSICBRAINZ_RATE_LIMIT_SECONDS = 0.8
_WIKIPEDIA_EN_RATE_LIMIT_SECONDS = 0.3
_WIKIPEDIA_OTHER_RATE_LIMIT_SECONDS = 0.2

# Default language priority for non-English Wikipedia lookups.
# The detected script's language (if any) is prepended at runtime.
_PRIORITY_LANGUAGES = [
    "es",
    "pt",
    "fr",
    "de",
    "it",
    "hi",
    "ko",
    "ja",
    "zh",
    "ar",
    "tr",
    "ru",
]


# ============================================================================
# COUNTRY DETECTION
# ============================================================================
def search_country(artist: str) -> Tuple[Optional[str], str]:
    """
    Determine the country of origin for an artist using multiple sources.

    Search order:

    1. MusicBrainz (up to 3 name variations).
    2. Wikidata (up to 3 name variations).
    3. Wikipedia EN (summary, then infobox, per variation).
    4. Wikipedia in priority languages based on script detection.
    5. DeepSeek API fallback.
    6. Groq API fallback (Llama 3.3 70B).
    7. Muse Spark API fallback (Meta).

    The first source that returns a non-`None` country wins and the
    cascade short-circuits.

    Parameters
    ----------
    artist : str
        Artist name to search for.

    Returns
    -------
    tuple of (str or None, str)
        A tuple `(country, source)` where:
        - `country` is the canonical country name, or `None` if
          unresolved.
        - `source` is a human-readable description of the winning source
          (e.g., `"MusicBrainz"`, `"MusicBrainz (var: Beyonce)"`,
          `"Wikipedia ES"`, `"DeepSeek API"`, `"Not found"`).

    Notes
    -----
    - **Caching is inherited from the per-source clients**, not
      implemented here. Repeated calls for the same artist do not incur
      duplicate network requests.
    - **Variation caps** (`_MAX_VARIATIONS_STRUCTURED`,
      `_MAX_VARIATIONS_WIKIPEDIA_OTHER`) bound the worst-case request
      count. Do not raise them without understanding the cost
      implications.
    - **The `(var: ...)` suffix** is appended to the source string only
      when the winning variation differs from the original artist name.
    - **AI fallbacks use the original name only** — variations are not
      sent to the AIs because they handle spelling variance natively.
    - **Sleeps are coarse-grained** and tuned for MusicBrainz (1 req/s)
      and Wikimedia burst limits. See module `Notes`.
    """
    variations = generate_all_variations(artist)

    # --- 1. MusicBrainz ---
    for var in variations[:_MAX_VARIATIONS_STRUCTURED]:
        country, source = search_musicbrainz_country_cached(var)
        if country:
            info = f" (var: {var})" if var != artist else ""
            return country, f"MusicBrainz{info}"
    time.sleep(_MUSICBRAINZ_RATE_LIMIT_SECONDS)

    # --- 2. Wikidata ---
    for var in variations[:_MAX_VARIATIONS_STRUCTURED]:
        country = search_wikidata_country_cached(var)
        if country:
            info = f" (var: {var})" if var != artist else ""
            return country, f"Wikidata{info}"

    # --- 3. Wikipedia EN (summary, then infobox) ---
    for var in variations[:_MAX_VARIATIONS_STRUCTURED]:
        country = search_wikipedia_summary_country_cached(var, "en")
        if country:
            info = f" (var: {var})" if var != artist else ""
            return country, f"Wikipedia EN summary{info}"

        country = search_wikipedia_infobox_country_cached(var, "en")
        if country:
            info = f" (var: {var})" if var != artist else ""
            return country, f"Wikipedia EN infobox{info}"
    time.sleep(_WIKIPEDIA_EN_RATE_LIMIT_SECONDS)

    # --- 4. Wikipedia in priority languages (script-aware) ---
    detected_lang = detect_script_from_name(artist)
    priority_langs = []
    if detected_lang:
        priority_langs.append(detected_lang)
    priority_langs.extend(_PRIORITY_LANGUAGES)

    # Deduplicate while preserving order (dict.fromkeys is O(n))
    priority_langs = list(dict.fromkeys(priority_langs))

    for lang in priority_langs:
        for var in variations[:_MAX_VARIATIONS_WIKIPEDIA_OTHER]:
            country = search_wikipedia_summary_country_cached(var, lang)
            if country:
                info = f" (var: {var})" if var != artist else ""
                return country, f"Wikipedia {lang.upper()}{info}"
            time.sleep(_WIKIPEDIA_OTHER_RATE_LIMIT_SECONDS)

    # --- 5. DeepSeek fallback ---
    logger.debug(f"  🔍 Using DeepSeek fallback for country: {artist}")
    deepseek_country, _, _ = search_deepseek_fallback(artist)
    if deepseek_country:
        return deepseek_country, "DeepSeek API"

    # --- 6. Groq fallback (Llama 3.3) ---
    logger.debug(f"  🔍 Using Groq fallback for country: {artist}")
    groq_country, _, _ = search_groq_fallback(artist)
    if groq_country:
        return groq_country, "Groq API"

    # --- 7. Muse Spark fallback (Meta) ---
    logger.debug(f"  🔍 Using Muse Spark fallback for country: {artist}")
    muse_country, _, _ = search_muse_fallback(artist)
    if muse_country:
        return muse_country, "Muse Spark API"

    return None, "Not found"
