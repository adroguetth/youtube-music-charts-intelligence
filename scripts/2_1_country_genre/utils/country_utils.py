"""
Country Utils - Country Validation and Normalization
============================================================================
Utility module for validating and normalizing raw country strings (names,
cities, demonyms, regional variants) to canonical country names. It is the
single entry point for country normalization across the pipeline: every
external source (MusicBrainz, Wikidata, Wikipedia) and every AI fallback
(DeepSeek, Groq, Muse Spark) routes its country output through
`validate_and_normalize_country()` before persisting or using it.

The canonicalization relies on two data structures from
`dictionaries.countries`:

- `VARIANT_TO_COUNTRY` — flat variant → canonical index for O(1) lookups.
- `COUNTRIES_CANONICAL` — canonical → set of variants, used for
  canonical-name comparison.

This module is deliberately separated from `country_detector.py` to avoid
circular imports with the API client modules (which import
`validate_and_normalize_country` from here).

Features
--------
- Direct lookup in `VARIANT_TO_COUNTRY` for exact matches (names, cities,
  demonyms) in O(1) average time.
- Comma-separated location handling (e.g., `"Brooklyn, United States"`),
  checking parts from right to left (country typically last).
- Substring matching for longer variants (length > 3) to catch cases like
  `"American singer"` → `"United States"`.
- Canonical-name fallback that ignores spacing differences
  (e.g., `"UnitedStates"` matches `"United States"`).
- Accepts accents, punctuation, and mixed casing via `normalize_text()`.

Dependencies
------------
- Internal: `..dictionaries.countries` (VARIANT_TO_COUNTRY,
  COUNTRIES_CANONICAL), `.text_utils` (normalize_text).
- External: re, typing (stdlib).

Requirements
------------
- Python 3.7+
- No external packages or environment variables required.

Notes
-----
- The function returns the **canonical** country name (as it appears as a
  key in `COUNTRIES_CANONICAL`), or `None` if no match is found. It never
  raises on invalid input — falsy input yields `None`.
- Matching is performed on the **normalized** version of the input
  (lowercased, punctuation stripped, whitespace collapsed via
  `normalize_text`). This means `"USA"`, `"u.s.a."`, and `"  Usa  "` all
  resolve to `"United States"`.
- Substring matching uses a **length > 3** guard to avoid false positives
  from short variants (e.g., `"us"`, `"uk"`, `"la"`) accidentally
  matching longer inputs. This is a recall/precision trade-off: longer
  variants are matched more aggressively.
- Substring matching iterates over `VARIANT_TO_COUNTRY.items()`, so
  worst-case performance is **O(number of variants)** — roughly 2,000+
  entries. This is acceptable for typical pipeline volumes but should not
  be called in a hot loop on large batches without caching upstream
  (`country_detector` caches results per artist).
- **Ambiguous variants resolve to the last country that defines them.**
  Because `VARIANT_TO_COUNTRY` is built by iterating
  `COUNTRIES_CANONICAL` in declaration order and assigning each variant
  without collision checks, a variant appearing in multiple countries is
  silently overwritten (later wins). Known historical collisions include
  `"santiago"` (Chile, Cuba, Dominican Republic, Panama) and `"georgia"`
  (US state vs. country). Audit `COUNTRIES_CANONICAL` for collisions
  before relying on ambiguous variants.
- The canonical-name fallback (with and without spaces) exists to handle
  edge cases where the input matches a canonical name but not any of its
  registered variants (e.g., spelling differences). It is **last** in the
  cascade so it does not shadow the faster direct and substring lookups.
- This function is **pure** and **deterministic** with respect to the
  current contents of `dictionaries.countries`. It does not perform I/O
  or mutate global state.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

import re
from typing import Optional

from ..dictionaries.countries import COUNTRIES_CANONICAL, VARIANT_TO_COUNTRY
from .text_utils import normalize_text

# ============================================================================
# CONSTANTS
# ============================================================================
_MIN_SUBSTRING_VARIANT_LENGTH = 4  # Minimum length for substring match (exclusive)


# ============================================================================
# COUNTRY NORMALIZATION
# ============================================================================
def validate_and_normalize_country(text: str) -> Optional[str]:
    """
    Validate and normalize a raw country string to a canonical country name.

    The function applies a cascade of matching strategies, in order of
    increasing cost:

    1. Direct lookup in `VARIANT_TO_COUNTRY` (O(1) average).
    2. Comma-separated location handling (right-to-left part lookup).
    3. Substring matching for variants longer than
       `_MIN_SUBSTRING_VARIANT_LENGTH`.
    4. Canonical-name fallback (with and without spaces).

    The first successful match wins.

    Parameters
    ----------
    text : str
        Raw country name, city, demonym, or location string. May contain
        accents, punctuation, and mixed casing.

    Returns
    -------
    str or None
        Canonical country name (a key of `COUNTRIES_CANONICAL`) if a match
        is found, `None` otherwise. Falsy input yields `None`.

    Examples
    --------
    >>> validate_and_normalize_country("USA")
    'United States'
    >>> validate_and_normalize_country("Brooklyn, New York")
    'United States'
    >>> validate_and_normalize_country("british")
    'United Kingdom'
    >>> validate_and_normalize_country("nowhere")
    None

    Notes
    -----
    - Input is normalized via `normalize_text` (lowercase, punctuation
      stripped, whitespace collapsed) before any lookup, so all matching
      is case- and punctuation-insensitive.
    - Comma-separated locations are checked **from right to left** because
      the country typically appears last in `"City, Country"` and
      `"City, State, Country"` formats.
    - The substring guard (`len(variant) > 3`) prevents short variants
      like `"us"`, `"uk"`, `"la"` from matching longer unrelated strings.
    - Worst-case complexity is O(number of variants) when falling through
      to substring matching. `country_detector` caches results per artist
      to amortize this cost across pipeline runs.
    - Ambiguous variants resolve to the last country that defines them in
      `COUNTRIES_CANONICAL` (see module `Notes`).
    """
    if not text:
        return None

    # --- Normalize input: lowercase, strip punctuation, collapse spaces ---
    text_norm = normalize_text(text)

    # --- Strategy 1: direct variant lookup (O(1) average) ---
    if text_norm in VARIANT_TO_COUNTRY:
        return VARIANT_TO_COUNTRY[text_norm]

    # --- Strategy 2: comma-separated location, right-to-left ---
    parts = [p.strip() for p in text_norm.split(",")]
    for part in reversed(parts):
        if part in VARIANT_TO_COUNTRY:
            return VARIANT_TO_COUNTRY[part]

    # --- Strategy 3: substring match for longer variants ---
    # Guards against false positives on short strings like "us", "uk", "la".
    for variant, country in VARIANT_TO_COUNTRY.items():
        if (
            variant in text_norm
            and len(variant) >= _MIN_SUBSTRING_VARIANT_LENGTH
        ):
            return country

    # --- Strategy 4: canonical-name fallback (spacing-insensitive) ---
    for country_canonical in COUNTRIES_CANONICAL.keys():
        canonical_lower = country_canonical.lower()
        if text_norm == canonical_lower:
            return country_canonical
        if text_norm.replace(" ", "") == canonical_lower.replace(" ", ""):
            return country_canonical

    return None
