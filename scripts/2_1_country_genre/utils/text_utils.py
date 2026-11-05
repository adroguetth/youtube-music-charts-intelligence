"""
Text Utils - Text Normalization and Artist Name Variations
============================================================================
Utility module for cleaning and transforming artist names to maximize match
rates across heterogeneous data sources. Chart data, external APIs, and AI
fallbacks rarely agree on the exact spelling of an artist name — accents
may be missing, dots may be added or dropped, prefixes (`"DJ"`, `"Lil"`,
`"The"`) may be present in one source and absent in another, and scripts
may differ entirely (Latin vs. Cyrillic vs. Devanagari).

This module provides the primitives that the rest of the pipeline uses to
cope with that variance:

1. `normalize_text()` — a fast, aggressive normalizer used for cache keys
   and equality comparisons.
2. `generate_name_variations()` — accent/dot/hyphen variants for fuzzy
   lookups.
3. `remove_artist_prefixes()` — prefix-stripped variants.
4. `generate_all_variations()` — the combined, ranked variation list.
5. `detect_script_from_name()` — script detection used to route lookups to
   the appropriate Wikipedia language edition.

Features
--------
- Unicode-aware accent removal via `unicodedata.normalize("NFD")` plus
  combining-mark filtering.
- Deterministic output ordering: variations are returned starting with the
  original name, then sorted by descending length for stability.
- Deduplication via `dict.fromkeys()` (order-preserving) rather than
  `set()` (unordered).
- Script detection covers Devanagari, Gujarati, Oriya, Tamil, Telugu,
  Kannada, Malayalam, Sinhala, Thai, Tibetan, Burmese, Khmer, Japanese,
  Chinese, Korean, Arabic, Urdu, Cyrillic (with Ukrainian/Bulgarian/
  Serbian refinements), Greek, and several Latin-accented languages
  (Spanish, Portuguese).
- No I/O, no global state, no external dependencies beyond the standard
  library.

Dependencies
------------
- Internal: none (leaf utility; consumed by `country_utils` and
  `artist_parser` indirectly).
- External: re, unicodedata, typing (stdlib).

Requirements
------------
- Python 3.7+
- No external packages or environment variables required.

Notes
-----
- **`normalize_text` is destructive by design**: it lowercases, collapses
  whitespace, and strips a fixed set of surrounding punctuation. It is
  intended for **comparison**, not for display or storage. Never use its
  output as a display name.
- **Punctuation stripping is edge-only**: `normalize_text` uses
  `strip()` with a punctuation character set, which removes leading and
  trailing punctuation but **preserves internal punctuation**. This means
  `"AC/DC"` stays `"ac/dc"` and `"Jay-Z"` stays `"jay-z"` (the internal
  `/` and `-` are untouched). This is intentional — internal punctuation
  is often semantically meaningful.
- **Accent removal preserves the base character**: `generate_name_variations`
  uses NFD decomposition and drops characters in Unicode category `Mn`
  (nonspacing marks), so `"Beyoncé"` → `"Beyonce"` and `"Motörhead"` →
  `"Motorhead"`. This is safe for Latin scripts but would strip vowel
  diacritics in languages where they are phonemic — the function is only
  used on Latin-script artist names in this pipeline.
- **Prefix removal is order-dependent and non-recursive**: each variant
  in `ARTIST_PREFIXES` is tested against the **original** name via
  `^prefix\s+`. A name like `"DJ Lil Wayne"` will produce **both**
  `"Lil Wayne"` (from DJ) and `"DJ Lil Wayne"` (unchanged for Lil, since
  Lil is not at the start). Multi-prefix chains are not collapsed by this
  function; that is why `generate_all_variations` iterates.
- **`generate_all_variations` caps at 15 entries** to bound the cost of
  downstream lookups. The original name is always first, then variations
  sorted by descending length (longer = more specific = more likely to
  match exactly).
- **Variation generation is combinatorial but bounded**: for each base
  variation, prefixes are removed and each prefix-stripped form is again
  passed through `generate_name_variations`. This two-pass approach
  catches cases like `"DJ Beyoncé"` → `"DJ Beyonce"` → `"Beyonce"`. The
  `[:15]` cap ensures the combinatorial explosion stays bounded.
- **`detect_script_from_name` returns a language code, not a script
  name**: it maps writing systems to ISO 639-1 codes that correspond to
  the **dominant language** of that script in the artist-name context
  (`"hi"` for Devanagari, `"ja"` for kana, `"zh"` for Han-only names,
  `"ko"` for Hangul or Han+Hangul, etc.). This is used to select a
  Wikipedia edition, not to classify the artist's nationality.
- **Script detection order matters**: the checks are ordered by script
  specificity (Devanagari before Thai before Han before Cyrillic). Han is
  checked **before** Hangul on purpose: a name containing both Han and
  Hangul is classified as Korean (`"ko"`), because Korean names commonly
  mix Hanja with Hangul. Pure Hangul (no Han) is also `"ko"`.
- **Cyrillic disambiguation** uses script-specific letters (`і`, `ї`,
  `є`, `ґ` for Ukrainian; `ъ` for Bulgarian; `ћ`, `ђ`, `џ`, `љ`, `њ` for
  Serbian) before defaulting to Russian. This is a heuristic — it will
  misclassify some names but is correct for the vast majority of
  artist-name cases.
- **Latin-accent heuristics are last-resort**: `ñ` → Spanish, `ç/ã/õ` →
  Portuguese, other accented vowels → Spanish. These are only reached
  when no non-Latin script is detected, and they are crude by design
  (they will misclassify French `"é"` as Spanish).
- All functions are **pure** and **deterministic**; given the same input,
  they always return the same output. `normalize_text` and
  `detect_script_from_name` are called on **every** artist in the
  pipeline, so their hot paths are kept allocation-light.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import re
import unicodedata
from typing import List, Optional

# ============================================================================
# CONSTANTS
# ============================================================================
_EDGE_PUNCTUATION = '.,;:¿?¡!()[]"\'«»…–—'
_MAX_VARIATIONS = 15
_MIN_VARIATION_LENGTH = 2

# Common prefixes in artist names that may be removed for broader matching.
# Maps prefix base (lowercase) to the casing variants to recognize.
ARTIST_PREFIXES = {
    "dj": ["DJ", "Dj", "dj"],
    "mc": ["MC", "Mc", "mc"],
    "lil": ["Lil", "lil", "LIL"],
    "young": ["Young", "young"],
    "big": ["Big", "big"],
    "the": ["The", "the", "THE"],
    "los": ["Los", "los"],
    "las": ["Las", "las"],
    "el": ["El", "el"],
    "la": ["La", "la"],
}


# ============================================================================
# TEXT NORMALIZATION
# ============================================================================
def normalize_text(text: str) -> str:
    """
    Normalize a text string for comparison and lookup.

    Lowercases, collapses whitespace, and strips a fixed set of leading and
    trailing punctuation. Internal punctuation is **preserved** so that
    names like `"AC/DC"` and `"Jay-Z"` remain distinguishable.

    Parameters
    ----------
    text : str
        Raw input string.

    Returns
    -------
    str
        Cleaned and normalized string. Empty string for falsy input.

    Notes
    -----
    - The output is intended for **comparison**, not display. Never store
      or display it as an artist name.
    - Whitespace runs (including tabs and newlines) are collapsed to a
      single space.
    - Edge punctuation is stripped via `str.strip()` with a fixed
      character set (`_EDGE_PUNCTUATION`); internal punctuation is
      untouched.
    """
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = text.strip(_EDGE_PUNCTUATION)
    return text


# ============================================================================
# NAME VARIATION GENERATION
# ============================================================================
def generate_name_variations(name: str) -> List[str]:
    """
    Generate basic typographic variations of an artist name.

    The variations are:

    - The original name.
    - Accent-stripped form (if different).
    - Dot-stripped form (if different).
    - Dot- and space-stripped form (compact, if dot-stripped differs).
    - Hyphen-replaced-by-space form (if different).

    Parameters
    ----------
    name : str
        Original artist name.

    Returns
    -------
    list of str
        Unique name variations, starting with the original.

    Notes
    -----
    - Accent removal uses Unicode NFD decomposition and drops characters
      in category `Mn` (nonspacing marks). Safe for Latin scripts; see
      module `Notes`.
    - Deduplication uses `dict.fromkeys()` to preserve order.
    """
    variations = [name]

    # --- Accent removal ---
    no_accents = "".join(
        c
        for c in unicodedata.normalize("NFD", name)
        if unicodedata.category(c) != "Mn"
    )
    if no_accents != name:
        variations.append(no_accents)

    # --- Dot removal (with and without internal spaces) ---
    no_dots = name.replace(".", "")
    if no_dots != name:
        variations.append(no_dots)
        variations.append(no_dots.replace(" ", ""))

    # --- Hyphen replacement ---
    no_hyphens = name.replace("-", " ")
    if no_hyphens != name:
        variations.append(no_hyphens)

    return list(dict.fromkeys(variations))


def remove_artist_prefixes(name: str) -> List[str]:
    """
    Remove common prefixes (DJ, MC, Lil, The, etc.) from a name.

    Each prefix variant in `ARTIST_PREFIXES` is matched at the **start**
    of the name via `^prefix\\s+`, and a variation is emitted without it.

    Parameters
    ----------
    name : str
        Artist name.

    Returns
    -------
    list of str
        Unique variations with prefixes removed, starting with the
        original name.

    Notes
    -----
    - Prefix removal is **non-recursive**: `"DJ Lil Wayne"` yields
      `"Lil Wayne"` (DJ removed) but does not further remove `"Lil"`.
      Callers needing full chains should use `generate_all_variations()`.
    - The prefix must be followed by whitespace; `"LilWayne"` (no space)
      is not modified.
    """
    variations = [name]

    for prefix_base, variants in ARTIST_PREFIXES.items():
        for variant in variants:
            pattern = r"^" + re.escape(variant) + r"\s+"
            if re.match(pattern, name):
                without_prefix = re.sub(pattern, "", name)
                if without_prefix:
                    variations.append(without_prefix)

    return list(dict.fromkeys(variations))


def generate_all_variations(name: str) -> List[str]:
    """
    Generate an extensive ranked list of name variations.

    Combines accent removal, dot removal, hyphen replacement, and prefix
    removal in a two-pass fashion: each base variation is generated, then
    prefixes are removed from it, then variations are regenerated on the
    prefix-stripped form.

    Parameters
    ----------
    name : str
        Original artist name.

    Returns
    -------
    list of str
        Up to `_MAX_VARIATIONS` (15) unique variations, starting with the
        original name, then all others sorted by descending length.

    Notes
    -----
    - The two-pass iteration catches chains like
      `"DJ Beyoncé"` → `"DJ Beyonce"` → `"Beyonce"`.
    - The list is capped at 15 entries to bound downstream lookup cost.
    - Variations shorter than `_MIN_VARIATION_LENGTH` (2) are dropped to
      avoid single-character noise.
    - Ordering after the original is by descending length, so longer
      (more specific) variations appear first.
    """
    all_vars = set()

    # --- Pass 1: typographic variations + prefix removal + re-variation ---
    for var in generate_name_variations(name):
        all_vars.add(var)
        for no_prefix in remove_artist_prefixes(var):
            all_vars.add(no_prefix)
            for var2 in generate_name_variations(no_prefix):
                all_vars.add(var2)

    # --- Rank: original first, then by descending length ---
    result = [name]
    for var in sorted(all_vars - {name}, key=len, reverse=True):
        if var and len(var) >= _MIN_VARIATION_LENGTH:
            result.append(var)

    return result[:_MAX_VARIATIONS]


# ============================================================================
# SCRIPT DETECTION
# ============================================================================
def detect_script_from_name(name: str) -> Optional[str]:
    """
    Detect the writing system of an artist name and return an ISO 639-1
    language code.

    Used to prioritize the correct Wikipedia language edition during
    lookups (e.g., `"ja"` for a name written in kana).

    Parameters
    ----------
    name : str
        Artist name string.

    Returns
    -------
    str or None
        Two-letter language code (e.g., `'ru'`, `'hi'`, `'ja'`, `'ko'`,
        `'ar'`, `'uk'`, `'es'`, `'pt'`, …), or `None` if no specific
        script or Latin-accent heuristic matched.

    Notes
    -----
    - Checks are ordered by **script specificity**; the first match wins.
    - Han characters are checked **before** Hangul on purpose: a name
      mixing Han and Hangul is classified as Korean (`"ko"`), because
      Korean names commonly mix Hanja with Hangul. Pure Hangul is also
      `"ko"`.
    - Cyrillic disambiguation uses script-specific letters before
      defaulting to Russian (`і/ї/є/ґ` → Ukrainian; `ъ` → Bulgarian;
      `ћ/ђ/џ/љ/њ` → Serbian).
    - Latin-accent heuristics are **last-resort** and crude by design:
      `ñ` → Spanish; `ç/ã/õ` → Portuguese; other accented vowels →
      Spanish. This will misclassify some French and Italian names as
      Spanish, but is acceptable for its purpose (edition selection).
    - The function returns `None` for plain ASCII Latin names so callers
      default to the English edition.
    """
    # --- South Asian scripts ---
    if re.search(r"[\u0900-\u097F]", name):
        return "hi"  # Devanagari (Hindi, Marathi, Nepali, …)
    if re.search(r"[\u0A80-\u0AFF]", name):
        return "gu"  # Gujarati
    if re.search(r"[\u0B00-\u0B7F]", name):
        return "or"  # Oriya
    if re.search(r"[\u0B80-\u0BFF]", name):
        return "ta"  # Tamil
    if re.search(r"[\u0C00-\u0C7F]", name):
        return "te"  # Telugu
    if re.search(r"[\u0C80-\u0CFF]", name):
        return "kn"  # Kannada
    if re.search(r"[\u0D00-\u0D7F]", name):
        return "ml"  # Malayalam
    if re.search(r"[\u0D80-\u0DFF]", name):
        return "si"  # Sinhala

    # --- Southeast Asian scripts ---
    if re.search(r"[\u0E00-\u0E7F]", name):
        return "th"  # Thai
    if re.search(r"[\u0F00-\u0FFF]", name):
        return "bo"  # Tibetan
    if re.search(r"[\u1000-\u109F]", name):
        return "my"  # Burmese
    if re.search(r"[\u1780-\u17FF]", name):
        return "km"  # Khmer

    # --- East Asian scripts ---
    if re.search(r"[\u3040-\u309F\u30A0-\u30FF]", name):
        return "ja"  # Japanese (Hiragana / Katakana)
    if re.search(r"[\u4E00-\u9FFF]", name):
        # Han characters: distinguish Korean (Hanja) from Chinese
        if re.search(r"[\uAC00-\uD7AF]", name):
            return "ko"
        return "zh"
    if re.search(r"[\uAC00-\uD7AF]", name):
        return "ko"  # Pure Hangul

    # --- Middle Eastern scripts ---
    if (
        re.search(r"[\u0600-\u06FF]", name)
        or re.search(r"[\u0750-\u077F]", name)
    ):
        # Urdu-specific letters: گ چ پ ژ
        if re.search(r"[گچپژ]", name):
            return "ur"
        return "ar"

    # --- Cyrillic (with language disambiguation) ---
    if re.search(r"[\u0400-\u04FF]", name):
        if re.search(r"[іїєґ]", name, re.IGNORECASE):
            return "uk"  # Ukrainian
        if re.search(r"ъ", name, re.IGNORECASE):
            return "bg"  # Bulgarian
        if re.search(r"[ћђџљњ]", name, re.IGNORECASE):
            return "sr"  # Serbian
        return "ru"  # Default Cyrillic

    # --- Greek ---
    if re.search(r"[\u0370-\u03FF]", name):
        return "el"

    # --- Latin-accent heuristics (last resort) ---
    if re.search(r"ñ", name, re.IGNORECASE):
        return "es"  # Spanish ñ
    if re.search(r"[çãõ]", name, re.IGNORECASE):
        return "pt"  # Portuguese
    if re.search(r"[áéíóúâêôàèìòùäëïöü]", name, re.IGNORECASE):
        return "es"  # Other Latin accents (crude heuristic)

    return None
