"""
Genre Detector - Multi-Source Artist Genre Resolution and Voting
============================================================================
Core orchestration module for resolving an artist's primary musical genre.
Implements the layered fallback cascade that drives the genre half of the
metadata enrichment pipeline, plus the weighted voting system that selects
a single macro-genre from candidates gathered across multiple sources.

The module has two distinct responsibilities:

1. **Resolution** (`search_artist_genre`): gathers genre candidates from
   structured sources (MusicBrainz → Wikidata → Wikipedia) and, when they
   yield too few candidates, falls back to AI sources in increasing cost
   order (DeepSeek → GPT-OSS → Qwen → Muse Spark) and finally to the country
   priority list.
2. **Voting** (`select_primary_genre`): combines candidate votes with
   source-based multipliers, scene-specific term bonuses, country priority
   weights, country-specific rules, and script-aware bonuses to produce a
   single winning macro-genre.

A third function, `normalize_genre`, is the public normalization entry
point consumed by every AI client (imported locally inside the fallback
modules to avoid circular imports) and by the voting logic itself.

Features
--------
- Raw genre → `(macro_genre, subgenre)` normalization with stopword
  filtering, direct lookup, substring fallback, and hyphen/space variants.
- Weighted voting across heterogeneous sources with per-source
  multipliers (`musicbrainz` ×1.5, `wikidata` ×1.3, `infobox` ×1.2).
- Scene-specific term bonuses that both boost weight and force the correct
  macro (`reggaeton`/`trap latino` → `Reggaetón/Trap Latino`, `k-pop` →
  `K-Pop/K-Rock`, `j-pop` → `J-Pop/J-Rock`, `sertanejo`/`funk brasileiro`
  → `Sertanejo`/`Funk Brasileiro`, `afrobeats`/`amapiano` →
  `Afrobeats`/`Amapiano`, etc.).
- Country priority boost via `COUNTRY_GENRE_PRIORITY` with rank-based
  multipliers (rank 1 ×2.0, rank 2 ×1.5, others ×1.2).
- Country-specific keyword rules via `COUNTRY_SPECIFIC_RULES`: `force_macro`
  (override), `prefer_genre` (boost), `map_generic_to` (remap), and
  `bonus_extra` (multiplier).
- Script-aware bonuses when the detected script is consistent with the
  resolved country (e.g., `ko` + `South Korea` → boost `K-Pop/K-Rock`).
- Adaptive Wikipedia language priority based on country, with a fixed
  fallback list when the country is unknown.
- Early-exit candidate threshold (`MIN_CANDIDATES = 3`) to avoid
  unnecessary Wikipedia calls once enough candidates have been collected.

Dependencies
------------
- Internal: `.config` (logger), `.utils.text_utils`
  (generate_all_variations, detect_script_from_name, normalize_text),
  `.apis.musicbrainz`, `.apis.wikidata`, `.apis.wikipedia`,
  `.apis.deepseek`, `.apis.gpt_oss`, `.apis.qwen`, `.apis.muse`,
  `.dictionaries.genres` (GENRE_MAPPINGS),
  `.dictionaries.macro_genres` (MACRO_GENRES, GENERIC_MACROS),
  `.dictionaries.country_rules` (COUNTRY_GENRE_PRIORITY,
  COUNTRY_SPECIFIC_RULES, DEFAULT_GENRE_PRIORITY),
  `.dictionaries.stopwords` (GENRE_STOPWORDS).
- External: time, collections, typing (stdlib).

Requirements
------------
- Python 3.7+
- Network access to MusicBrainz, Wikidata, and Wikipedia.
- Optional: `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `MODEL_API_KEY` for the
  AI fallbacks. Absence of these keys degrades gracefully.

Notes
-----
- **`normalize_genre` is the public normalization contract**: every AI
  client imports it locally (inside the function body) to avoid the
  circular import `api_clients.deepseek → genre_detector → apis.deepseek`.
  Do not move this import to module level.
- **`normalize_genre` substring matching is O(n) over all mappings**:
  the `sorted_mappings` list is recomputed on every call.
- **The voting system is additive and multiplicative**: base weights come
  from the source tuples `(subgenre, weight, source)`; source multipliers
  and scene bonuses are **multiplicative**; country priority boosts are
  **multiplicative**; `force_macro` remapping moves a vote to a different
  macro **at a multiplied weight**.
- **AI fallbacks are only invoked when `all_candidates` is empty**: unlike
  `country_detector` which chains AI fallbacks unconditionally, this
  module skips AI when structured sources returned **any** candidates.
- **Country fallback is last**: when no candidates are found but a country
  is known, the top entry of `COUNTRY_GENRE_PRIORITY[country]` is returned.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

import time
from collections import defaultdict
from typing import List, Optional, Tuple

from .apis.deepseek import search_deepseek_fallback
from .apis.gpt_oss import search_groq_fallback  # Opción A: Importamos el nombre original
from .apis.qwen import search_qwen_fallback
from .apis.muse import search_muse_fallback
from .apis.musicbrainz import search_musicbrainz_genre_cached
from .apis.wikidata import search_wikidata_genre_cached
from .apis.wikipedia import (
    search_wikipedia_infobox_genre_cached,
    search_wikipedia_summary_genre_cached,
)
from .config import logger
from .dictionaries.country_rules import (
    COUNTRY_GENRE_PRIORITY,
    COUNTRY_SPECIFIC_RULES,
    DEFAULT_GENRE_PRIORITY,
)
from .dictionaries.genres import GENRE_MAPPINGS
from .dictionaries.macro_genres import GENERIC_MACROS, MACRO_GENRES
from .dictionaries.stopwords import GENRE_STOPWORDS
from .utils.text_utils import (
    detect_script_from_name,
    generate_all_variations,
    normalize_text,
)

# ============================================================================
# CONSTANTS
# ============================================================================
_MAX_VARIATIONS_STRUCTURED = 2
_MAX_VARIATIONS_WIKIPEDIA = 1
_MIN_CANDIDATES = 3

_MUSICBRAINZ_RATE_LIMIT_SECONDS = 0.5
_WIKIDATA_RATE_LIMIT_SECONDS = 0.5
_WIKIPEDIA_RATE_LIMIT_SECONDS = 0.3

_SOURCE_MULTIPLIERS = {
    "musicbrainz": 1.5,
    "wikidata": 1.3,
    "infobox": 1.2,
}

_SCENE_BONUSES = [
    (
        ["reggaeton", "reggaetón", "regueton", "reguetón", "trap latino",
         "urbano", "dembow", "perreo"],
        1.4,
        "Reggaetón/Trap Latino",
    ),
    (
        ["k-pop", "kpop", "korean pop", "k-rap", "k-r&b"],
        1.4,
        "K-Pop/K-Rock",
    ),
    (
        ["j-pop", "jpop", "japanese pop"],
        1.4,
        "J-Pop/J-Rock",
    ),
    (
        ["indian", "bollywood", "punjabi", "bhangra"],
        1.3,
        None,
    ),
    (
        ["pakistani pop", "urdu", "lollywood"],
        1.3,
        None,
    ),
    (
        ["bangladeshi pop", "bengali"],
        1.3,
        None,
    ),
    (
        ["sertanejo", "funk brasileiro", "funk carioca", "funk"],
        1.4,
        None,
    ),
    (
        ["afrobeats", "naija", "amapiano"],
        1.4,
        None,
    ),
]

_COUNTRY_LANG_MAP = {
    "India": ["hi", "ta", "te", "ml", "kn", "gu", "or", "bn", "en"],
    "Pakistan": ["ur", "en"],
    "Bangladesh": ["bn", "en"],
    "South Korea": ["ko", "en"],
    "Japan": ["ja", "en"],
    "China": ["zh", "en"],
    "Mongolia": ["mn", "en"],
    "Kazakhstan": ["kk", "ru", "en"],
    "Nepal": ["ne", "en"],
    "Russia": ["ru", "en"],
    "Ukraine": ["uk", "ru", "en"],
    "Brazil": ["pt", "en"],
    "Mexico": ["es", "en"],
    "Spain": ["es", "en"],
    "France": ["fr", "en"],
    "Germany": ["de", "en"],
    "Italy": ["it", "en"],
    "Turkey": ["tr", "en"],
    "Egypt": ["ar", "en"],
    "Israel": ["he", "en"],
}

_OTHER_LANGUAGES = ["es", "pt", "fr", "de", "it", "ru", "ar", "zh", "ja", "ko"]

_SCRIPT_COUNTRY_BOOSTS = [
    (["hi", "ta", "te", "ml", "kn", "gu", "or", "bn"],
     ["India", "Pakistan", "Bangladesh"],
     ["Indian Pop", "Pakistani Pop", "Bangladeshi Pop/Rock"],
     1.2),
    (["ko"], ["South Korea"], ["K-Pop/K-Rock"], 1.2),
    (["ja"], ["Japan"], ["J-Pop/J-Rock"], 1.2),
    (["zh"], ["China"], ["C-Pop/C-Rock"], 1.2),
    (["mn"], ["Mongolia"], ["Mongolian Pop/Rock/Metal"], 1.2),
    (["ar"],
     ["Egypt", "Saudi Arabia", "UAE", "Morocco", "Algeria", "Tunisia"],
     ["Arabic Pop/Rock"],
     1.2),
    (["tr"], ["Turkey"], ["Turkish Pop/Rock"], 1.2),
    (["kk"], ["Kazakhstan"], ["Q-pop/Q-rock"], 1.2),
]

_COUNTRY_PRIORITY_MULTIPLIERS = {0: 2.0, 1: 1.5}
_COUNTRY_PRIORITY_DEFAULT_MULTIPLIER = 1.2


# ============================================================================
# GENRE NORMALIZATION
# ============================================================================
def normalize_genre(genre_text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize a raw genre string to `(macro_genre, subgenre)`.
    """
    if not genre_text:
        return None, None

    text_norm = normalize_text(genre_text)

    if text_norm in GENRE_STOPWORDS:
        return None, None

    if text_norm in GENRE_MAPPINGS:
        return GENRE_MAPPINGS[text_norm]

    sorted_mappings = sorted(GENRE_MAPPINGS.keys(), key=len, reverse=True)
    for genre_variant in sorted_mappings:
        if genre_variant in text_norm and len(genre_variant) > 3:
            return GENRE_MAPPINGS[genre_variant]

    text_no_hyphen = text_norm.replace("-", " ")
    if text_no_hyphen != text_norm and text_no_hyphen in GENRE_MAPPINGS:
        return GENRE_MAPPINGS[text_no_hyphen]

    text_with_hyphen = text_norm.replace(" ", "-")
    if text_with_hyphen != text_norm and text_with_hyphen in GENRE_MAPPINGS:
        return GENRE_MAPPINGS[text_with_hyphen]

    return None, None


# ============================================================================
# WEIGHTED VOTING
# ============================================================================
def _apply_source_multipliers(subgenre: str, source: str, weight: float) -> float:
    for source_key, multiplier in _SOURCE_MULTIPLIERS.items():
        if source_key in source:
            weight *= multiplier
    return weight


def _apply_scene_bonuses(
    subgenre: str, weight: float
) -> Tuple[float, Optional[str]]:
    sub_lower = subgenre.lower()
    override = None

    for keywords, multiplier, override_macro in _SCENE_BONUSES:
        if any(term in sub_lower for term in keywords):
            weight *= multiplier
            if override_macro:
                override = override_macro
            break

    return weight, override


def select_primary_genre(
    artist: str,
    genre_candidates: List[Tuple[str, int, str]],
    country: Optional[str] = None,
    detected_lang: Optional[str] = None,
) -> Optional[str]:
    if not genre_candidates:
        return None

    macro_votes: defaultdict[str, float] = defaultdict(float)

    for subgenre, weight, source in genre_candidates:
        macro, _ = normalize_genre(subgenre)

        if macro:
            final_weight = _apply_source_multipliers(
                subgenre, source, float(weight)
            )
            final_weight, override = _apply_scene_bonuses(
                subgenre, final_weight
            )
            if override:
                macro = override
            macro_votes[macro] += final_weight
        else:
            for known_macro in MACRO_GENRES:
                if subgenre.lower() == known_macro.lower():
                    macro_votes[known_macro] += float(weight)
                    break

    if country and country in COUNTRY_SPECIFIC_RULES:
        rule = COUNTRY_SPECIFIC_RULES[country]
        map_to = rule.get("map_generic_to")
        if map_to:
            for subgenre, weight, _ in genre_candidates:
                macro, _ = normalize_genre(subgenre)
                if macro and macro in GENERIC_MACROS:
                    macro_votes[map_to] += float(weight)

    if country and macro_votes:
        priority = COUNTRY_GENRE_PRIORITY.get(country, DEFAULT_GENRE_PRIORITY)
        for macro in list(macro_votes.keys()):
            if macro in priority:
                idx = priority.index(macro)
                multiplier = _COUNTRY_PRIORITY_MULTIPLIERS.get(
                    idx, _COUNTRY_PRIORITY_DEFAULT_MULTIPLIER
                )
                macro_votes[macro] *= multiplier

    if country and macro_votes and country in COUNTRY_SPECIFIC_RULES:
        rule = COUNTRY_SPECIFIC_RULES[country]
        for macro in list(macro_votes.keys()):
            for subgenre, _, _ in genre_candidates:
                sub_lower = subgenre.lower()
                if any(kw in sub_lower for kw in rule["keywords"]):
                    if "force_macro" in rule and macro != rule["force_macro"]:
                        peso = macro_votes.pop(macro, 0.0)
                        macro_votes[rule["force_macro"]] += (
                            peso * rule["bonus_extra"]
                        )
                    elif "prefer_genre" in rule and macro == rule["prefer_genre"]:
                        macro_votes[macro] *= rule["bonus_extra"]
                    else:
                        macro_votes[macro] *= rule["bonus_extra"]
                    break

    if detected_lang and country:
        for scripts, countries, macros, multiplier in _SCRIPT_COUNTRY_BOOSTS:
            if detected_lang in scripts and country in countries:
                for m in macros:
                    if m in macro_votes:
                        macro_votes[m] *= multiplier

    if macro_votes:
        return max(macro_votes.items(), key=lambda x: x[1])[0]

    return None


# ============================================================================
# GENRE RESOLUTION
# ============================================================================
def _collect_wikipedia_candidates(
    variations: List[str],
    priority_langs: List[str],
    all_candidates: List[Tuple[str, int, str]],
) -> None:
    for var in variations[:_MAX_VARIATIONS_WIKIPEDIA]:
        for lang in priority_langs:
            candidates = search_wikipedia_infobox_genre_cached(var, lang)
            all_candidates.extend(candidates)
            if len(all_candidates) >= _MIN_CANDIDATES:
                return

            if not candidates:
                candidates = search_wikipedia_summary_genre_cached(var, lang)
                all_candidates.extend(candidates)
            if len(all_candidates) >= _MIN_CANDIDATES:
                return

            time.sleep(_WIKIPEDIA_RATE_LIMIT_SECONDS)


def _try_ai_fallback(
    artist: str,
    country: Optional[str],
    fallback_name: str,
    fallback_fn,
    source_label: str,
) -> Optional[Tuple[str, str]]:
    logger.debug(
        f"  🔍 Using {fallback_name} fallback for genre: {artist} "
        f"(country: {country})"
    )
    _, genre, _ = fallback_fn(artist, context_country=country)
    if not genre:
        return None

    macro, _ = normalize_genre(genre)
    if macro:
        logger.info(
            f"  🤖 {fallback_name} genre for {artist}: {macro} "
            f"(from: {genre})"
        )
        return macro, f"{source_label} (genre: {genre})"

    logger.info(
        f"  🤖 {fallback_name} raw genre for {artist}: {genre}"
    )
    return genre, f"{source_label} (raw: {genre})"


def search_artist_genre(
    artist: str, country: Optional[str] = None
) -> Tuple[Optional[str], str]:
    all_candidates: List[Tuple[str, int, str]] = []
    variations = generate_all_variations(artist)
    detected_lang = detect_script_from_name(artist)

    # --- 1. MusicBrainz ---
    for var in variations[:_MAX_VARIATIONS_STRUCTURED]:
        candidates = search_musicbrainz_genre_cached(var)
        all_candidates.extend(candidates)
        if candidates:
            break
        time.sleep(_MUSICBRAINZ_RATE_LIMIT_SECONDS)

    # --- 2. Wikidata ---
    if not all_candidates:
        for var in variations[:_MAX_VARIATIONS_STRUCTURED]:
            candidates = search_wikidata_genre_cached(var)
            all_candidates.extend(candidates)
            if candidates:
                break
            time.sleep(_WIKIDATA_RATE_LIMIT_SECONDS)

    # --- 3. Wikipedia ---
    priority_langs: List[str] = []
    if country:
        priority_langs.extend(
            _COUNTRY_LANG_MAP.get(country, ["en", "es"])
        )
    else:
        if detected_lang:
            priority_langs.append(detected_lang)
        priority_langs.append("en")

    priority_langs = list(dict.fromkeys(priority_langs))

    if len(all_candidates) < _MIN_CANDIDATES:
        _collect_wikipedia_candidates(
            variations, priority_langs, all_candidates
        )

    if len(all_candidates) < _MIN_CANDIDATES:
        other_langs = [
            lang for lang in _OTHER_LANGUAGES if lang not in priority_langs
        ]
        _collect_wikipedia_candidates(
            variations, other_langs, all_candidates
        )

    # --- 4-7. AI fallbacks ---
    if not all_candidates:
        result = _try_ai_fallback(
            artist,
            country,
            "DeepSeek",
            search_deepseek_fallback,
            "DeepSeek API",
        )
        if result:
            return result

        result = _try_ai_fallback(
            artist,
            country,
            "GPT-OSS",
            search_groq_fallback,  # Opción A: Llamada original
            "GPT-OSS API",
        )
        if result:
            return result

        result = _try_ai_fallback(
            artist,
            country,
            "Qwen",
            search_qwen_fallback,
            "Qwen API",
        )
        if result:
            return result

        result = _try_ai_fallback(
            artist,
            country,
            "Muse Spark",
            search_muse_fallback,
            "Muse Spark API",
        )
        if result:
            return result

    # --- 8. Country priority fallback ---
    if not all_candidates and country:
        priority = COUNTRY_GENRE_PRIORITY.get(
            country, DEFAULT_GENRE_PRIORITY
        )
        if priority:
            return priority[0], f"Genre: country fallback ({country})"

    # --- 9. Weighted voting ---
    if all_candidates:
        primary_genre = select_primary_genre(
            artist, all_candidates, country, detected_lang
        )
        sources = set(s for _, _, s in all_candidates)
        return primary_genre, f"Genre: {', '.join(sources)}"

    return None, "Genre not found"
