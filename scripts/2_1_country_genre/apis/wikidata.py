"""
Wikidata API Client - Country and Genre Lookup
============================================================================
Structured-source detection module for musical artist metadata. Queries
Wikidata entities via the `wbsearchentities` and `wbgetentities` actions to
resolve an artist's country of origin (via P27 citizenship or P19 place of
birth) and primary musical genre tags (via P136). Results are cached to
avoid redundant network calls.

This module is the second structured source in the metadata detection
pipeline, invoked after MusicBrainz and before Wikipedia and the AI
fallbacks. It relies on shared HTTP sessions and an in-memory cache
provided by the `utils` package.

Features
--------
- Country resolution via P27 (citizenship) then P19 (place of birth).
- Genre resolution via P136 claims (top 3 per artist).
- Multi-language label lookup (English preferred, Spanish fallback).
- Cached results for both country and genre lookups.
- Shared HTTP session reuse via `utils.cache.get_http_sessions`.
- Graceful degradation: network errors, missing claims, and missing
  labels all yield `None` or an empty candidate list.

Dependencies
------------
- Internal: `..config` (logger), `..utils.cache` (get_cache,
  get_http_sessions), `..utils.country_utils`
  (validate_and_normalize_country).
- External: typing (stdlib).

Requirements
------------
- Python 3.7+
- Network access to `https://www.wikidata.org/w/api.php`.
- A descriptive `User-Agent` is recommended by Wikidata; the shared
  session is expected to provide one.

Notes
-----
- Two properties are consulted for country, in order: P27 (country of
  citizenship) then P19 (place of birth). The first resolvable label wins.
- Genre candidates are returned as `(name, weight, source)` tuples with a
  fixed weight of `3`, which downstream selection logic uses to rank
  Wikidata above weaker sources.
- Label lookup requests English and Spanish in a single call
  (`languages=en|es`); English is preferred, Spanish is used as fallback.
- Up to 3 search results are probed per query; the first one that yields
  a valid country/genre label is returned.
- All exceptions are logged at debug level and swallowed to keep the
  pipeline resilient.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/Chilean-Presidential-Elections-2025-Analysis
Email: adroguett.consultor@gmail.com
"""

from typing import List, Optional, Tuple

from ..config import logger
from ..utils.cache import get_cache, get_http_sessions
from ..utils.country_utils import validate_and_normalize_country

# ============================================================================
# CONSTANTS
# ============================================================================
_API_URL = "https://www.wikidata.org/w/api.php"
_SEARCH_LIMIT = 3
_MAX_GENRE_CLAIMS = 3
_GENRE_WEIGHT = 3
_REQUEST_TIMEOUT_SECONDS = 10
_LABEL_TIMEOUT_SECONDS = 8
_LABEL_LANGUAGES = "en|es"
_COUNTRY_PROPERTIES = ["P27", "P19"]  # P27: citizenship, P19: place of birth
_GENRE_PROPERTY = "P136"  # P136: genre


# ============================================================================
# SHARED HELPERS
# ============================================================================
def _extract_label(entity: dict) -> Optional[str]:
    """
    Extract a human-readable label from a Wikidata entity.

    Parameters
    ----------
    entity : dict
        Wikidata entity record containing a `labels` mapping.

    Returns
    -------
    str or None
        The English label if present, otherwise the Spanish label,
        otherwise None.

    Notes
    -----
    Multi-language labels are requested in a single call
    (`languages=en|es`); this helper enforces the English-first preference
    consistently across country and genre resolution.
    """
    labels = entity.get("labels", {})
    if "en" in labels:
        return labels["en"]["value"]
    if "es" in labels:
        return labels["es"]["value"]
    return None


def _search_entity_ids(session, artist: str) -> List[str]:
    """
    Search Wikidata for entity IDs matching an artist name.

    Parameters
    ----------
    session : requests.Session
        Shared HTTP session for Wikidata.
    artist : str
        Artist name to search.

    Returns
    -------
    list of str
        List of QIDs for candidate entities (up to `_SEARCH_LIMIT`), or an
        empty list if no matches were found.

    Notes
    -----
    Uses the `wbsearchentities` action with English as the search
    language. All errors are logged at debug level and yield an empty
    list.
    """
    params = {
        "action": "wbsearchentities",
        "search": artist,
        "language": "en",
        "format": "json",
        "limit": _SEARCH_LIMIT,
    }

    try:
        resp = session.get(
            _API_URL,
            params=params,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        data = resp.json()
    except Exception as e:
        logger.debug(f"Wikidata search error for {artist}: {e}")
        return []

    return [result["id"] for result in data.get("search", [])]


def _fetch_entity_claims(session, qid: str) -> Optional[dict]:
    """
    Fetch the claims block for a Wikidata entity.

    Parameters
    ----------
    session : requests.Session
        Shared HTTP session for Wikidata.
    qid : str
        Wikidata entity ID (e.g., "Q12345").

    Returns
    -------
    dict or None
        The entity's `claims` mapping, or None if the entity could not be
        retrieved or has no claims.

    Notes
    -----
    Uses the `wbgetentities` action with `props=claims`. All errors are
    logged at debug level and yield None.
    """
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "claims",
        "format": "json",
    }

    try:
        resp = session.get(
            _API_URL,
            params=params,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        data = resp.json()
    except Exception as e:
        logger.debug(f"Wikidata claims fetch error for {qid}: {e}")
        return None

    if "entities" not in data or qid not in data["entities"]:
        return None

    return data["entities"][qid].get("claims", {})


def _fetch_entity_label(session, qid: str) -> Optional[str]:
    """
    Fetch the preferred label for a Wikidata entity.

    Parameters
    ----------
    session : requests.Session
        Shared HTTP session for Wikidata.
    qid : str
        Wikidata entity ID (e.g., "Q12345").

    Returns
    -------
    str or None
        The English label if present, otherwise the Spanish label,
        otherwise None.

    Notes
    -----
    Uses the `wbgetentities` action with `props=labels` and
    `languages=en|es`. All errors are logged at debug level and yield None.
    """
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "labels",
        "languages": _LABEL_LANGUAGES,
        "format": "json",
    }

    try:
        resp = session.get(
            _API_URL,
            params=params,
            timeout=_LABEL_TIMEOUT_SECONDS,
        )
        data = resp.json()
    except Exception as e:
        logger.debug(f"Wikidata label fetch error for {qid}: {e}")
        return None

    if "entities" not in data or qid not in data["entities"]:
        return None

    return _extract_label(data["entities"][qid])


def _extract_claim_qids(claims: dict, prop: str, limit: int) -> List[str]:
    """
    Extract referenced entity QIDs from a Wikidata claim property.

    Parameters
    ----------
    claims : dict
        Entity's `claims` mapping.
    prop : str
        Wikidata property ID (e.g., "P27", "P136").
    limit : int
        Maximum number of QIDs to return.

    Returns
    -------
    list of str
        Referenced entity QIDs, up to `limit` items. Malformed claims are
        skipped silently.

    Notes
    -----
    Only claims with a `mainsnak.datavalue.value.id` structure (i.e.,
    entity references) are considered; literal or string values are
    ignored.
    """
    qids = []

    if prop not in claims:
        return qids

    for claim in claims[prop][:limit]:
        try:
            mainsnak = claim.get("mainsnak", {})
            datavalue = mainsnak.get("datavalue", {})
            value = datavalue.get("value", {})
            qid = value.get("id")
            if qid:
                qids.append(qid)
        except Exception:
            continue

    return qids


# ============================================================================
# COUNTRY LOOKUP
# ============================================================================
def search_wikidata_country_cached(artist: str) -> Optional[str]:
    """
    Search Wikidata for an artist's country of origin.

    Consults P27 (country of citizenship) first, then P19 (place of
    birth). The first resolvable country label wins.

    Parameters
    ----------
    artist : str
        Artist name.

    Returns
    -------
    str or None
        Canonical country name, or None if no country could be resolved.

    Notes
    -----
    - Results (including negative ones) are cached to avoid repeated
      network calls.
    - Up to `_SEARCH_LIMIT` (3) candidate entities are probed; the first
      one yielding a valid country label is returned.
    - Country names are validated and normalized via
      `validate_and_normalize_country` before being returned.
    - All exceptions are logged at debug level and treated as not found.
    """
    cache = get_cache()
    if artist in cache["wikidata_country"]:
        return cache["wikidata_country"][artist]

    sessions = get_http_sessions()
    session = sessions["wikidata"]

    try:
        qids = _search_entity_ids(session, artist)
        if not qids:
            cache["wikidata_country"][artist] = None
            return None

        # --- Probe each candidate entity until a country is resolved ---
        for qid in qids:
            claims = _fetch_entity_claims(session, qid)
            if not claims:
                continue

            for prop in _COUNTRY_PROPERTIES:
                country_qids = _extract_claim_qids(
                    claims, prop, limit=_SEARCH_LIMIT
                )
                for country_qid in country_qids:
                    country_name = _fetch_entity_label(session, country_qid)
                    if not country_name:
                        continue

                    country_canonical = validate_and_normalize_country(
                        country_name
                    )
                    if country_canonical:
                        cache["wikidata_country"][artist] = country_canonical
                        return country_canonical

        cache["wikidata_country"][artist] = None
        return None

    except Exception as e:
        logger.debug(f"Wikidata country error for {artist}: {e}")
        cache["wikidata_country"][artist] = None
        return None


# ============================================================================
# GENRE LOOKUP
# ============================================================================
def search_wikidata_genre_cached(artist: str) -> List[Tuple[str, int, str]]:
    """
    Search Wikidata for genre claims (P136) associated with an artist.

    Parameters
    ----------
    artist : str
        Artist name.

    Returns
    -------
    list of (str, int, str)
        List of `(genre_name, weight, source)` tuples where `weight` is
        `_GENRE_WEIGHT` (3) and `source` is `"wikidata"`. Returns an empty
        list when no genres are found.

    Notes
    -----
    - Results (including empty lists) are cached to avoid repeated network
      calls.
    - Up to `_MAX_GENRE_CLAIMS` (3) genre claims are collected per
      candidate entity, and up to `_SEARCH_LIMIT` (3) candidate entities
      are probed.
    - The fixed weight of 3 lets downstream selection logic rank Wikidata
      above weaker sources.
    - Genre names are lowercased for downstream consistency.
    - Per-claim errors are logged at debug level and skipped without
      aborting the whole lookup.
    """
    cache = get_cache()
    if artist in cache["wikidata_genre"]:
        return cache["wikidata_genre"][artist]

    sessions = get_http_sessions()
    session = sessions["wikidata"]
    candidates = []

    try:
        qids = _search_entity_ids(session, artist)
        if not qids:
            cache["wikidata_genre"][artist] = candidates
            return candidates

        # --- Collect genre labels across all candidate entities ---
        for qid in qids:
            claims = _fetch_entity_claims(session, qid)
            if not claims:
                continue

            genre_qids = _extract_claim_qids(
                claims, _GENRE_PROPERTY, limit=_MAX_GENRE_CLAIMS
            )
            for genre_qid in genre_qids:
                genre_name = _fetch_entity_label(session, genre_qid)
                if genre_name:
                    candidates.append(
                        (genre_name.lower(), _GENRE_WEIGHT, "wikidata")
                    )

    except Exception as e:
        logger.debug(f"Wikidata genre error for {artist}: {e}")

    cache["wikidata_genre"][artist] = candidates
    return candidates
