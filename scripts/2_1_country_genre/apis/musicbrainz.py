"""
MusicBrainz API Client - Country and Genre Lookup
============================================================================
Structured-source detection module for musical artist metadata. Queries the
MusicBrainz REST API (`/ws/2/artist/`) to resolve an artist's country of
origin and primary musical genre tags. Provides fuzzy name matching against
candidate artists, normalized country extraction, and cached results to
avoid redundant network calls.

This module is the first structured source in the metadata detection
pipeline and is invoked before Wikidata, Wikipedia, and the AI fallbacks.
It relies on shared HTTP sessions and an in-memory cache provided by the
`utils` package.

Features
--------
- Fuzzy artist matching via `difflib.SequenceMatcher` with substring bonus.
- Country extraction from `area` / `begin-area` fields with normalization.
- Genre extraction from `genres` tags (fallback to `tags` when empty).
- Cached results for both country and genre lookups.
- Shared HTTP session reuse via `utils.cache.get_http_sessions`.
- Graceful degradation: network errors and missing fields return
  `(None, "Not found")` or an empty candidate list.

Dependencies
------------
- Internal: `..config` (logger), `..utils.cache` (get_cache,
  get_http_sessions), `..utils.country_utils`
  (validate_and_normalize_country).
- External: difflib, time, typing (stdlib).

Requirements
------------
- Python 3.7+
- Network access to `https://musicbrainz.org`.
- MusicBrainz requests must include a valid `User-Agent` header (rate
  limit: 1 request per second per IP).

Notes
-----
- Match acceptance threshold is 0.55 on the combined similarity score;
  matches below this threshold are discarded as not found.
- A substring bonus of 0.3 is applied when one name contains the other,
  which helps disambiguate common short names.
- Genre candidates are returned as `(name, count, source)` tuples sorted
  by MusicBrainz's own ordering (top 5), so downstream selection logic can
  re-rank them.
- `genres` takes precedence over `tags`; `tags` is only used when no
  `genres` entries are available.
- All exceptions are logged at debug level and swallowed to keep the
  pipeline resilient.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/Chilean-Presidential-Elections-2025-Analysis
Email: adroguett.consultor@gmail.com
"""

import time
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from ..config import logger
from ..utils.cache import get_cache, get_http_sessions
from ..utils.country_utils import validate_and_normalize_country

# ============================================================================
# CONSTANTS
# ============================================================================
_API_URL = "https://musicbrainz.org/ws/2/artist/"
_USER_AGENT = "ArtistDB/5.0 (contact@example.com)"
_REQUEST_TIMEOUT_SECONDS = 10
_QUERY_LIMIT_COUNTRY = 5
_QUERY_LIMIT_GENRE = 1
_MAX_GENRE_CANDIDATES = 5
_MATCH_THRESHOLD = 0.55
_SUBSTRING_BONUS = 0.3


# ============================================================================
# GENRE EXTRACTION
# ============================================================================
def extract_genre_from_musicbrainz(mb_data: dict) -> List[Tuple[str, int, str]]:
    """
    Extract genre tags from a MusicBrainz artist record.

    Parameters
    ----------
    mb_data : dict
        MusicBrainz artist JSON data for a single artist.

    Returns
    -------
    list of (str, int, str)
        List of `(genre_name, count, source)` tuples. `source` is either
        `"musicbrainz_genres"` or `"musicbrainz_tags"`, indicating which
        field the candidate came from.

    Notes
    -----
    - `genres` takes precedence over `tags`; the latter is only used when
      no `genres` entries are available.
    - At most `_MAX_GENRE_CANDIDATES` (5) entries are returned, in the
      order provided by MusicBrainz.
    - Genre names are lowercased for downstream consistency.
    """
    candidates = []

    # --- Primary source: structured `genres` field ---
    if "genres" in mb_data:
        for genre in mb_data["genres"][:_MAX_GENRE_CANDIDATES]:
            name = genre.get("name", "")
            count = genre.get("count", 1)
            if name:
                candidates.append((name.lower(), count, "musicbrainz_genres"))

    # --- Fallback source: free-form `tags` field ---
    if "tags" in mb_data and not candidates:
        for tag in mb_data["tags"][:_MAX_GENRE_CANDIDATES]:
            name = tag.get("name", "")
            count = tag.get("count", 1)
            if name:
                candidates.append((name.lower(), count, "musicbrainz_tags"))

    return candidates


# ============================================================================
# COUNTRY LOOKUP
# ============================================================================
def search_musicbrainz_country_cached(artist: str) -> Tuple[Optional[str], str]:
    """
    Search MusicBrainz for an artist's country of origin.

    Uses fuzzy name matching and scoring to select the best candidate
    artist, then extracts the country from the `area` or `begin-area`
    field.

    Parameters
    ----------
    artist : str
        Artist name to search.

    Returns
    -------
    tuple of (str or None, str)
        A tuple `(country, source)` where:
        - `country` is the normalized country name, or None.
        - `source` describes the outcome (e.g., "MusicBrainz (artist)",
          "Not found").

    Notes
    -----
    - Results (including negative ones) are cached to avoid repeated
      network calls.
    - Candidate scoring combines `SequenceMatcher` ratio with a substring
      bonus of `_SUBSTRING_BONUS` when one name contains the other.
    - Matches scoring below `_MATCH_THRESHOLD` (0.55) are discarded.
    - All exceptions are logged at debug level and treated as "Not found".
    """
    cache = get_cache()
    if artist in cache["musicbrainz_country"]:
        return cache["musicbrainz_country"][artist]

    sessions = get_http_sessions()
    session = sessions["musicbrainz"]

    try:
        # --- Query MusicBrainz for candidate artists ---
        headers = {"User-Agent": _USER_AGENT}
        params = {
            "query": artist,
            "fmt": "json",
            "limit": _QUERY_LIMIT_COUNTRY,
        }
        resp = session.get(
            _API_URL,
            headers=headers,
            params=params,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )

        if resp.status_code != 200:
            cache["musicbrainz_country"][artist] = (None, "Not found")
            return None, "Not found"

        data = resp.json()
        if not data.get("artists"):
            cache["musicbrainz_country"][artist] = (None, "Not found")
            return None, "Not found"

        # --- Score candidates and pick the best match ---
        artist_lower = artist.lower()
        best_score = 0.0
        best_artist = None

        for mb_artist in data["artists"][:_QUERY_LIMIT_COUNTRY]:
            mb_name = mb_artist.get("name", "").lower()
            bonus = (
                _SUBSTRING_BONUS
                if (artist_lower in mb_name or mb_name in artist_lower)
                else 0.0
            )
            score = SequenceMatcher(None, artist_lower, mb_name).ratio() + bonus
            if score > best_score:
                best_score = score
                best_artist = mb_artist

        if best_score < _MATCH_THRESHOLD:
            cache["musicbrainz_country"][artist] = (None, "Not found")
            return None, "Not found"

        # --- Extract country from area fields ---
        for field in ["area", "begin-area"]:
            if field in best_artist:
                country_raw = best_artist[field].get("name", "")
                if country_raw:
                    country_norm = validate_and_normalize_country(country_raw)
                    if country_norm:
                        result = (country_norm, f"MusicBrainz ({artist})")
                        cache["musicbrainz_country"][artist] = result
                        return result

        cache["musicbrainz_country"][artist] = (None, "Not found")
        return None, "Not found"

    except Exception as e:
        logger.debug(f"MusicBrainz country error for {artist}: {e}")
        cache["musicbrainz_country"][artist] = (None, "Not found")
        return None, "Not found"


# ============================================================================
# GENRE LOOKUP
# ============================================================================
def search_musicbrainz_genre_cached(artist: str) -> List[Tuple[str, int, str]]:
    """
    Search MusicBrainz for genre tags associated with an artist.

    Fetches the top result and delegates tag extraction to
    `extract_genre_from_musicbrainz`.

    Parameters
    ----------
    artist : str
        Artist name.

    Returns
    -------
    list of (str, int, str)
        List of `(genre_name, count, source)` tuples. Returns an empty list
        when the artist is not found or the request fails.

    Notes
    -----
    - Results (including empty lists) are cached to avoid repeated network
      calls.
    - Unlike the country lookup, this uses only the first result
      (`_QUERY_LIMIT_GENRE = 1`) because genre tags are typically attached
      to the canonical artist record.
    - Exceptions are logged at debug level and yield an empty list.
    """
    cache = get_cache()
    if artist in cache["musicbrainz_genre"]:
        return cache["musicbrainz_genre"][artist]

    sessions = get_http_sessions()
    session = sessions["musicbrainz"]
    candidates = []

    try:
        # --- Query MusicBrainz for the top artist match ---
        headers = {"User-Agent": _USER_AGENT}
        params = {
            "query": artist,
            "fmt": "json",
            "limit": _QUERY_LIMIT_GENRE,
        }
        resp = session.get(
            _API_URL,
            headers=headers,
            params=params,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )

        if resp.status_code == 200:
            data = resp.json()
            if data.get("artists"):
                mb_data = data["artists"][0]
                candidates = extract_genre_from_musicbrainz(mb_data)

    except Exception as e:
        logger.debug(f"MusicBrainz genre error for {artist}: {e}")

    cache["musicbrainz_genre"][artist] = candidates
    return candidates
