"""
Wikipedia API Client - Country and Genre Extraction
============================================================================
Structured-source detection module for musical artist metadata. Uses the
MediaWiki API to resolve an artist's country of origin and primary musical
genre by parsing infobox fields and page summaries. Supports multiple
language editions (`lang` parameter) with per-language caching.

This module is the third structured source in the metadata detection
pipeline, invoked after MusicBrainz and Wikidata and before the AI
fallbacks. It relies on shared HTTP sessions and an in-memory cache
provided by the `utils` package.

Features
--------
- Country extraction from infobox fields (`origin`, `birth_place`,
  `location`, `from`, `country`).
- Country extraction from page summaries via regex patterns.
- Genre extraction from infobox fields (`genre`, `género`, `genres`,
  `géneros`).
- Genre extraction from page summaries via multiple regex patterns plus
  keyword matching.
- Multi-language support (`lang='en'` by default).
- Cached results for both country and genre lookups, keyed by
  `(artist, lang)`.
- Stopword filtering to discard nationality/adjective false positives.

Dependencies
------------
- Internal: `..config` (logger), `..utils.cache` (get_cache,
  get_http_sessions), `..utils.country_utils`
  (validate_and_normalize_country).
- External: requests, re, typing (stdlib + requests).

Requirements
------------
- Python 3.7+
- Network access to `https://{lang}.wikipedia.org/w/api.php` and
  `https://{lang}.wikipedia.org/api/rest_v1/page/summary/`.
- A descriptive `User-Agent` header is required by the Wikimedia REST
  API; a default is set inline for summary requests.

Notes
-----
- The infobox regex targets `Infobox musical artist` and `Infobox band`
  templates only; other infobox types are ignored.
- Field values are cleaned of wiki markup (`[[link|label]]` → `label`,
  HTML tags, and `{{template}}` placeholders) before normalization.
- Genre candidates carry a weight that reflects source reliability:
  infobox → 2, summary/keyword → 1 or 0.5.
- `GENRE_STOPWORDS_FOR_WIKIPEDIA` filters out nationality adjectives and
  generic praise words that commonly precede the actual genre in prose
  (e.g., "American", "award-winning").
- All exceptions are logged at debug level and yield None or an empty
  list, keeping the pipeline resilient.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

import re
from typing import List, Optional, Tuple

import requests

from ..config import logger
from ..utils.cache import get_cache, get_http_sessions
from ..utils.country_utils import validate_and_normalize_country

# ============================================================================
# CONSTANTS
# ============================================================================
_USER_AGENT = "ArtistDB/5.0"
_API_URL_TEMPLATE = "https://{lang}.wikipedia.org/w/api.php"
_SUMMARY_URL_TEMPLATE = (
    "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
)
_QUERY_TIMEOUT_SECONDS = 8
_PARSE_TIMEOUT_SECONDS = 10
_INFOBOX_PATTERN = r"\{\{\s*Infobox (?:musical artist|band)[\s\S]*?\}\}"

_COUNTRY_INFOBOX_FIELDS = ["origin", "birth_place", "location", "from", "country"]
_GENRE_INFOBOX_FIELDS = ["genre", "género", "genres", "géneros"]

_INFOBOX_GENRE_WEIGHT = 2
_SUMMARY_GENRE_WEIGHT = 1
_KEYWORD_GENRE_WEIGHT = 0.5

# Stopwords to filter out false positives in genre extraction
GENRE_STOPWORDS_FOR_WIKIPEDIA = {
    # Nationalities and demonyms
    "american", "british", "canadian", "australian", "indian", "korean",
    "japanese", "mexican", "spanish", "french", "german", "italian",
    "brazilian", "argentine", "colombian", "chilean", "peruvian",
    "venezuelan", "cuban", "dominican", "african", "nigerian",
    "south african", "kenyan", "egyptian", "moroccan", "israeli",
    "turkish", "russian", "ukrainian", "polish", "swedish", "norwegian",
    "danish", "finnish", "dutch", "belgian", "swiss", "austrian",
    "portuguese", "greek", "irish", "scottish", "welsh", "english",
    # Generic praise / award adjectives
    "famous", "popular", "well-known", "acclaimed", "award-winning",
    "multi-platinum", "grammy", "grammy-winning", "oscar", "oscar-winning",
    "best-selling", "successful", "influential", "legendary", "iconic",
}

_GENRE_KEYWORDS = [
    "pop", "rock", "hip hop", "rap", "trap", "reggaeton", "reggaetón",
    "cumbia", "bachata", "salsa", "metal", "punk", "indie", "alternative",
    "electrónica", "dance", "k-pop", "j-pop", "bollywood", "country",
    "folk", "reggae", "dancehall", "afrobeats", "edm", "house", "techno",
    "pakistani pop", "bangladeshi pop", "urdu", "punjabi", "bhangra",
    "sertanejo", "funk brasileiro", "amapiano", "afrobeat",
]


# ============================================================================
# SHARED HELPERS
# ============================================================================
def _clean_wiki_value(value: str) -> str:
    """
    Remove common wiki markup from an infobox field value.

    Parameters
    ----------
    value : str
        Raw infobox field value.

    Returns
    -------
    str
        The value with `[[link|label]]` → `label`, HTML tags stripped, and
        `{{template}}` placeholders removed.

    Notes
    -----
    This is the same cleanup applied to country and genre infobox fields,
    so it is centralized here to guarantee consistent behavior.
    """
    value = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\{\{[^}]+\}\}", "", value)
    return value.strip()


def _fetch_infobox(session, lang: str, artist: str) -> Optional[str]:
    """
    Fetch the wikitext of an artist's page and return the first infobox.

    Parameters
    ----------
    session : requests.Session
        Shared HTTP session for Wikipedia.
    lang : str
        Wikipedia language code.
    artist : str
        Artist name.

    Returns
    -------
    str or None
        The matched infobox wikitext, or None if the page or infobox is
        missing.

    Notes
    -----
    - First resolves redirects via `action=query` to get the canonical
      title, then fetches the wikitext via `action=parse`.
    - Only `Infobox musical artist` and `Infobox band` templates are
      matched.
    - All errors are logged at debug level and yield None.
    """
    try:
        # --- Resolve canonical title via query (follows redirects) ---
        query_params = {
            "action": "query",
            "titles": artist,
            "redirects": 1,
            "format": "json",
        }
        resp = session.get(
            _API_URL_TEMPLATE.format(lang=lang),
            params=query_params,
            timeout=_QUERY_TIMEOUT_SECONDS,
        )
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        if not pages:
            return None
        page_id = next(iter(pages))
        title = pages[page_id].get("title", artist)

        # --- Fetch wikitext for the resolved title ---
        parse_params = {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "format": "json",
            "redirects": True,
        }
        resp = session.get(
            _API_URL_TEMPLATE.format(lang=lang),
            params=parse_params,
            timeout=_PARSE_TIMEOUT_SECONDS,
        )
        data = resp.json()

        if "parse" not in data:
            return None

        wikitext = data["parse"]["wikitext"]["*"]
        infobox_match = re.search(_INFOBOX_PATTERN, wikitext, re.IGNORECASE)
        if not infobox_match:
            return None

        return infobox_match.group()

    except Exception as e:
        logger.debug(f"Wikipedia infobox fetch error for {artist} ({lang}): {e}")
        return None


def _fetch_summary(session, lang: str, artist: str) -> Optional[str]:
    """
    Fetch the page summary extract for an artist.

    Parameters
    ----------
    session : requests.Session
        Shared HTTP session for Wikipedia.
    lang : str
        Wikipedia language code.
    artist : str
        Artist name.

    Returns
    -------
    str or None
        The lowercased summary extract, or None if the request failed or
        the extract is empty.

    Notes
    -----
    Uses the Wikimedia REST API (`/api/rest_v1/page/summary/`), which
    requires a descriptive `User-Agent`. Errors and non-200 responses
    yield None.
    """
    url = _SUMMARY_URL_TEMPLATE.format(
        lang=lang, title=requests.utils.quote(artist)
    )
    headers = {"User-Agent": _USER_AGENT}

    try:
        resp = session.get(
            url, headers=headers, timeout=_QUERY_TIMEOUT_SECONDS
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        extract = data.get("extract", "").lower()
        return extract or None

    except Exception as e:
        logger.debug(f"Wikipedia summary fetch error for {artist} ({lang}): {e}")
        return None


def _extract_infobox_field(infobox: str, fields: List[str]) -> Optional[str]:
    """
    Return the raw value of the first matching infobox field.

    Parameters
    ----------
    infobox : str
        Wikitext of the artist's infobox.
    fields : list of str
        Ordered list of field names to try.

    Returns
    -------
    str or None
        The raw field value if found, otherwise None.

    Notes
    -----
    The value is returned **uncleaned**; callers should pass it through
    `_clean_wiki_value` before further processing.
    """
    for field in fields:
        field_pattern = r"\|?\s*" + field + r"\s*=\s*([^\n|]+)"
        field_match = re.search(field_pattern, infobox, re.IGNORECASE)
        if field_match:
            return field_match.group(1).strip()
    return None


def _split_genre_list(value: str) -> List[str]:
    """
    Split a genre field value into individual genre candidates.

    Parameters
    ----------
    value : str
        Cleaned infobox genre value.

    Returns
    -------
    list of str
        Lowercased, trimmed genre tokens with length > 2 that are not in
        `GENRE_STOPWORDS_FOR_WIKIPEDIA`.

    Notes
    -----
    Splits on commas, semicolons, `" and "`, and `" y "` (Spanish).
    """
    separators = r",|;|\sand\s|\sy\s"
    genres = re.split(separators, value)
    return [
        g.strip().lower()
        for g in genres
        if g.strip()
        and len(g.strip()) > 2
        and g.strip().lower() not in GENRE_STOPWORDS_FOR_WIKIPEDIA
    ]


def _append_summary_genres(
    candidates: List[Tuple[str, float, str]],
    extract: str,
    pattern: str,
    lang: str,
    weight: float,
) -> None:
    """
    Apply a regex pattern to the summary and append genre candidates.

    Parameters
    ----------
    candidates : list of tuple
        Accumulator list to append results to (mutated in place).
    extract : str
        Lowercased summary extract.
    pattern : str
        Regex pattern whose first capture group is the candidate genre
        expression.
    lang : str
        Wikipedia language code (used to build the source tag).
    weight : float
        Weight assigned to the resulting candidates.

    Returns
    -------
    None
        The `candidates` list is mutated in place.

    Notes
    -----
    Each capture is further split on `" and "`, `" y "`, and commas, and
    filtered against `GENRE_STOPWORDS_FOR_WIKIPEDIA`.
    """
    matches = re.findall(pattern, extract)
    for match in matches:
        candidate = match.strip()
        subgenres = re.split(r"\s+(?:and|y)\s+|\s*,\s*", candidate)
        for sub in subgenres:
            sub = sub.strip()
            if (
                sub
                and len(sub) > 2
                and sub not in GENRE_STOPWORDS_FOR_WIKIPEDIA
            ):
                candidates.append(
                    (sub, weight, f"wikipedia_{lang}_summary")
                )


# ============================================================================
# COUNTRY LOOKUP
# ============================================================================
def search_wikipedia_infobox_country_cached(
    artist: str, lang: str = "en"
) -> Optional[str]:
    """
    Extract country from Wikipedia infobox fields.

    Tries, in order: `origin`, `birth_place`, `location`, `from`,
    `country`.

    Parameters
    ----------
    artist : str
        Artist name.
    lang : str, optional
        Wikipedia language code (default: "en").

    Returns
    -------
    str or None
        Canonical country name, or None if no country could be resolved.

    Notes
    -----
    - Results (including negative ones) are cached under
      `cache["wikipedia_country"][(artist, lang)]`.
    - Field values are cleaned of wiki markup and normalized via
      `validate_and_normalize_country`.
    - All exceptions are logged at debug level and treated as not found.
    """
    cache = get_cache()
    key = (artist, lang)
    if key in cache["wikipedia_country"]:
        return cache["wikipedia_country"][key]

    sessions = get_http_sessions()
    session = sessions["wikipedia"]

    try:
        infobox = _fetch_infobox(session, lang, artist)
        if not infobox:
            cache["wikipedia_country"][key] = None
            return None

        # --- Try each country-related field in order ---
        for field in _COUNTRY_INFOBOX_FIELDS:
            raw_value = _extract_infobox_field(infobox, [field])
            if not raw_value:
                continue

            cleaned = _clean_wiki_value(raw_value)
            country_norm = validate_and_normalize_country(cleaned)
            if country_norm:
                cache["wikipedia_country"][key] = country_norm
                return country_norm

        cache["wikipedia_country"][key] = None
        return None

    except Exception as e:
        logger.debug(
            f"Wikipedia infobox {lang} country error for {artist}: {e}"
        )
        cache["wikipedia_country"][key] = None
        return None


def search_wikipedia_summary_country_cached(
    artist: str, lang: str = "en"
) -> Optional[str]:
    """
    Extract country from a Wikipedia page summary using regex patterns.

    Parameters
    ----------
    artist : str
        Artist name.
    lang : str, optional
        Wikipedia language code (default: "en").

    Returns
    -------
    str or None
        Canonical country name, or None if no country could be resolved.

    Notes
    -----
    - Results (including negative ones) are cached under
      `cache["wikipedia_country"][(artist, lang)]`.
    - Candidate strings between 2 and 35 characters are normalized via
      `validate_and_normalize_country`.
    - Patterns cover singer/rapper/musician descriptions, `"from ..."`,
      `"born in ..."`, and `"formed in ..."`.
    - All exceptions are logged at debug level and treated as not found.
    """
    cache = get_cache()
    key = (artist, lang)
    if key in cache["wikipedia_country"]:
        return cache["wikipedia_country"][key]

    sessions = get_http_sessions()
    session = sessions["wikipedia"]

    try:
        extract = _fetch_summary(session, lang, artist)
        if not extract:
            cache["wikipedia_country"][key] = None
            return None

        patterns = [
            r"is\s+(?:a|an)\s+([a-z\s]+?)\s+(?:singer|rapper|musician|artist|songwriter|producer|dj|band|group)",
            r"was\s+(?:a|an)\s+([a-z\s]+?)\s+(?:singer|rapper|musician|artist|songwriter|producer|dj|band|group)",
            r"are\s+(?:a|an)\s+([a-z\s]+?)\s+(?:band|group|duo)",
            r"from\s+([a-z\s]+?)(?:\.|,|\s+who|\s+is|\s+was)",
            r"born\s+in\s+([^,]+?)(?:\.|,)",
            r"formed\s+in\s+([^,]+?)(?:\.|,)",
        ]

        for pattern in patterns:
            match = re.search(pattern, extract)
            if not match:
                continue

            candidate = match.group(1).strip()
            if not 2 <= len(candidate) <= 35:
                continue

            country = validate_and_normalize_country(candidate)
            if country:
                cache["wikipedia_country"][key] = country
                return country

        cache["wikipedia_country"][key] = None
        return None

    except Exception as e:
        logger.debug(
            f"Wikipedia summary {lang} country error for {artist}: {e}"
        )
        cache["wikipedia_country"][key] = None
        return None


# ============================================================================
# GENRE LOOKUP
# ============================================================================
def search_wikipedia_infobox_genre_cached(
    artist: str, lang: str = "en"
) -> List[Tuple[str, int, str]]:
    """
    Extract genre from Wikipedia infobox `genre` / `género` fields.

    Parameters
    ----------
    artist : str
        Artist name.
    lang : str, optional
        Wikipedia language code (default: "en").

    Returns
    -------
    list of (str, int, str)
        List of `(genre_name, weight, source)` tuples where `weight` is
        `_INFOBOX_GENRE_WEIGHT` (2) and `source` is
        `"wikipedia_{lang}_infobox"`. Returns an empty list when no genres
        are found.

    Notes
    -----
    - Results (including empty lists) are cached under
      `cache["wikipedia_genre"][(artist, lang)]`.
    - Field values are cleaned of wiki markup, split on common separators,
      and filtered against `GENRE_STOPWORDS_FOR_WIKIPEDIA`.
    - Exceptions are logged at debug level and yield an empty list.
    """
    cache = get_cache()
    key = (artist, lang)
    if key in cache["wikipedia_genre"]:
        return cache["wikipedia_genre"][key]

    sessions = get_http_sessions()
    session = sessions["wikipedia"]
    candidates = []

    try:
        infobox = _fetch_infobox(session, lang, artist)
        if not infobox:
            cache["wikipedia_genre"][key] = candidates
            return candidates

        # --- Try each genre-related field in order ---
        for field in _GENRE_INFOBOX_FIELDS:
            raw_value = _extract_infobox_field(infobox, [field])
            if not raw_value:
                continue

            cleaned = _clean_wiki_value(raw_value)
            for genre in _split_genre_list(cleaned):
                candidates.append(
                    (genre, _INFOBOX_GENRE_WEIGHT, f"wikipedia_{lang}_infobox")
                )

    except Exception as e:
        logger.debug(
            f"Wikipedia infobox genre error for {artist} ({lang}): {e}"
        )

    cache["wikipedia_genre"][key] = candidates
    return candidates


def search_wikipedia_summary_genre_cached(
    artist: str, lang: str = "en"
) -> List[Tuple[str, float, str]]:
    """
    Extract genre hints from a Wikipedia page summary.

    Applies several regex patterns covering common English phrasings
    (e.g., "is a [genre] singer", "are a [genre] band", "playing [genre]
    music", "known for their [genre] music", "genre is [genre]") plus a
    keyword-matching pass with lower weight.

    Parameters
    ----------
    artist : str
        Artist name.
    lang : str, optional
        Wikipedia language code (default: "en").

    Returns
    -------
    list of (str, float, str)
        List of `(genre_name, weight, source)` tuples where `weight` is
        `_SUMMARY_GENRE_WEIGHT` (1) for regex matches or
        `_KEYWORD_GENRE_WEIGHT` (0.5) for keyword matches. Returns an
        empty list when no genres are found.

    Notes
    -----
    - Results (including empty lists) are cached under
      `cache["wikipedia_genre"][(artist, lang)]`.
    - Regex-derived candidates are further split on `" and "`, `" y "`,
      and commas.
    - Keyword matching uses `_GENRE_KEYWORDS` with word-boundary matching
      to avoid substring false positives.
    - Exceptions are logged at debug level and yield an empty list.
    """
    cache = get_cache()
    key = (artist, lang)
    if key in cache["wikipedia_genre"]:
        return cache["wikipedia_genre"][key]

    sessions = get_http_sessions()
    session = sessions["wikipedia"]
    candidates = []

    try:
        extract = _fetch_summary(session, lang, artist)
        if not extract:
            cache["wikipedia_genre"][key] = candidates
            return candidates

        # --- Pattern 1: "is a [genre] singer/rapper/musician..." ---
        _append_summary_genres(
            candidates,
            extract,
            r"is\s+(?:a|an)\s+([a-z\s\-]+?)\s+(?:singer|rapper|musician|artist|songwriter|producer|dj|band|group|duo|trio)",
            lang,
            _SUMMARY_GENRE_WEIGHT,
        )

        # --- Pattern 2: "[nationality] [genre] singer..." ---
        _append_summary_genres(
            candidates,
            extract,
            r"(?:american|british|canadian|australian|indian|korean|japanese|mexican|spanish|french|german|italian|brazilian|argentine|colombian|chilean|peruvian|venezuelan|puerto rican|cuban|dominican|african|nigerian|south african|kenyan|egyptian|moroccan|israeli|turkish|russian|ukrainian|polish|swedish|norwegian|danish|finnish|dutch|belgian|swiss|austrian|portuguese|greek|irish|scottish|welsh|english)\s+([a-z\s\-]+?)\s+(?:singer|rapper|musician|artist|songwriter|producer|dj|band|group|duo)",
            lang,
            _SUMMARY_GENRE_WEIGHT,
        )

        # --- Pattern 3: "are a [genre] band/group" ---
        _append_summary_genres(
            candidates,
            extract,
            r"are\s+(?:a|an)\s+([a-z\s\-]+?)\s+(?:band|group|duo)",
            lang,
            _SUMMARY_GENRE_WEIGHT,
        )

        # --- Patterns 4-6: free-standing genre expressions ---
        for pattern in (
            r"playing\s+([a-z\s\-]+?)\s+music",
            r"known\s+for\s+their\s+([a-z\s\-]+?)\s+music",
            r"genre\s+is\s+([a-z\s\-]+?)(?:\.|,|$)",
        ):
            matches = re.findall(pattern, extract)
            for match in matches:
                candidate = match.strip()
                if (
                    candidate
                    and len(candidate) > 2
                    and candidate not in GENRE_STOPWORDS_FOR_WIKIPEDIA
                ):
                    candidates.append(
                        (
                            candidate,
                            _SUMMARY_GENRE_WEIGHT,
                            f"wikipedia_{lang}_summary",
                        )
                    )

        # --- Keyword matching (lower weight) ---
        for keyword in _GENRE_KEYWORDS:
            if keyword in GENRE_STOPWORDS_FOR_WIKIPEDIA:
                continue
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, extract):
                candidates.append(
                    (
                        keyword,
                        _KEYWORD_GENRE_WEIGHT,
                        f"wikipedia_{lang}_keyword",
                    )
                )

    except Exception as e:
        logger.debug(
            f"Wikipedia summary genre error for {artist} ({lang}): {e}"
        )

    cache["wikipedia_genre"][key] = candidates
    return candidates
