"""
Resolver - Country and Genre Resolution for Collaborations
============================================================================
Core resolution logic for the song catalog builder. Given a list of artists
(with their known countries and genres from Script 2.1), determines the
single country and genre that best represents the track as a whole.

Implements the **collaboration weight algorithm**, which uses a decision
tree based on the distribution of countries among collaborators:

    Rule 1 — Absolute majority (>50%): assign the majority country and
             its inferred genre.
    Rule 2 — Exact 50/50 split between 2 countries: assign the majority
             country and its inferred genre.
    Rule 3 — Relative majority (<50%) with same continent and ≤2
             countries: assign the majority country and its genre.
    Rule 4 — Everything else: assign "Multi-country" and "Multi-genre".

Genre inference uses the `GENRE_HIERARCHY` dictionary: if a single genre
holds an absolute majority among the artists from the winning country, that
genre wins. Otherwise, the hierarchy is walked from top to bottom and the
first genre present in the known set wins.

Features
--------
- Handles single-artist tracks (trivial case).
- Handles unknown countries and genres gracefully.
- Handles mixed-continent collaborations (returns "Multi-country").
- Handles ties (exact 50/50 between 2 countries) deterministically.
- Country inference falls back to continent when needed.
- Deterministic: the same input always produces the same output.

Dependencies
------------
- Internal: `.config` (logger), `.dictionaries.continent_map`
  (COUNTRY_TO_CONTINENT), `.dictionaries.genre_hierarchy` (GENRE_HIERARCHY,
  DEFAULT_GENRE, DEFAULT_COUNTRY), `.utils.artist_parser` (parse_artist_list).
- External: collections (Counter), typing (stdlib).

Requirements
------------
- Python 3.7+

Notes
-----
- **Rule 1 vs Rule 2**: Rule 1 requires strictly >50%. Rule 2 covers the
  exact 50/50 case, which happens with 2-artist collaborations. This is
  important because 50% is not a "majority" but it is still a strong signal.
- **Rule 3 continent check**: the continent check uses the *known* countries
  only. If 2 of 3 artists are from South America and 1 is from Europe, the
  majority is still South American and Rule 3 applies (distinct_continents
  = 2, so it actually fails the same-continent check and returns Multi).
- **Genre hierarchy is country-specific**: `GENRE_HIERARCHY[country]` is
  ordered from most to least dominant. This means that for a Brazilian
  track with genres {"Sertanejo", "Forró"}, the hierarchy ["Brazilian
  Regional", "Funk Brasileiro", ...] will pick "Brazilian Regional"
  because it's higher in the list, even if "Sertanejo" has more absolute
  votes.
- **No side effects**: this module is pure. It reads from the two static
  dictionaries and returns a tuple. It does not touch the database.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from collections import Counter
from typing import Dict, List, Optional, Tuple

from .config import logger
from .dictionaries.continent_map import COUNTRY_TO_CONTINENT
from .dictionaries.genre_hierarchy import (
    DEFAULT_COUNTRY,
    DEFAULT_GENRE,
    GENRE_HIERARCHY,
)
from .utils.artist_parser import parse_artist_list, normalize_name


# ============================================================================
# CONTINENT LOOKUP
# ============================================================================
def get_continent(country: str) -> str:
    """
    Map a canonical country name to its continent identifier.

    Parameters
    ----------
    country : str
        Full country name (e.g., `'Brazil'`).

    Returns
    -------
    str
        Continent label (`'Asia'`, `'America'`, `'Europe'`, `'Africa'`,
        `'Oceania'`), or `'Unknown'` if the country is not in the map.
    """
    return COUNTRY_TO_CONTINENT.get(country, "Unknown")


# ============================================================================
# GENRE INFERENCE
# ============================================================================
def infer_genre_by_country(artists_info: List[Dict]) -> str:
    """
    Infer the most representative genre for artists from a single country.

    Logic:
    1. If a single genre holds an absolute majority (>50%), use it.
    2. Otherwise, walk the country's `GENRE_HIERARCHY` and return the first
       genre that appears in the known set.
    3. Fall back to the top of the hierarchy if no genre matches.

    Parameters
    ----------
    artists_info : list of dict
        List of dicts with keys `'name'`, `'country'`, `'genre'`.

    Returns
    -------
    str
        The resolved genre label.
    """
    if not artists_info:
        return DEFAULT_GENRE

    # Anchor to the primary (first) artist's country
    country = artists_info[0]["country"]
    hierarchy = GENRE_HIERARCHY.get(country, [DEFAULT_GENRE])

    known_genres = [a["genre"] for a in artists_info if a["genre"]]
    if not known_genres:
        return hierarchy[0] if hierarchy else DEFAULT_GENRE

    counter = Counter(known_genres)
    most_common_genre, most_common_count = counter.most_common(1)[0]

    # Absolute majority check
    if most_common_count > len(known_genres) / 2:
        return most_common_genre

    # Hierarchy-guided tiebreaker
    for priority_genre in hierarchy:
        if priority_genre in known_genres:
            return priority_genre

    return hierarchy[0] if hierarchy else DEFAULT_GENRE


# ============================================================================
# COUNTRY AND GENRE RESOLUTION
# ============================================================================
def resolve_country_and_genre(artists_info: List[Dict]) -> Tuple[str, str]:
    """
    Apply the collaboration weight algorithm to determine the country and
    genre for a potentially multi-artist track.

    Decision tree:

    Rule 1 — Absolute majority (>50%): assign the majority country and its
             inferred genre.
    Rule 2 — Exact 50/50 split between 2 countries: assign the majority
             country and its inferred genre.
    Rule 3 — Relative majority (<50%) with same continent and ≤2 distinct
             countries: assign the majority country and its genre.
    Rule 4 — Everything else: assign `'Multi-country'` / `'Multi-genre'`.

    Parameters
    ----------
    artists_info : list of dict
        List of dicts with keys `'name'`, `'country'`, `'genre'`.

    Returns
    -------
    tuple of (str, str)
        `(country, genre)` resolved for the track. If no information is
        available, returns `(DEFAULT_COUNTRY, DEFAULT_GENRE)`.
    """
    total_artists = len(artists_info)

    if total_artists == 0:
        return DEFAULT_COUNTRY, DEFAULT_GENRE

    # Single artist — trivial case
    if total_artists == 1:
        info = artists_info[0]
        return (
            info["country"] or DEFAULT_COUNTRY,
            info["genre"] or DEFAULT_GENRE,
        )

    # Filter artists with a known country
    known = [a for a in artists_info if a["country"] is not None]
    if not known:
        return DEFAULT_COUNTRY, DEFAULT_GENRE

    known_countries = [a["country"] for a in known]
    country_counter = Counter(known_countries)
    majority_country, majority_count = country_counter.most_common(1)[0]
    majority_pct = majority_count / total_artists

    # Continent analysis
    continents = [get_continent(c) for c in known_countries if c]
    continent_counter = Counter(continents)
    distinct_continents = len(continent_counter)
    distinct_countries = len(country_counter)

    # -------------------------------------------------------------------------
    # Rule 1: Absolute majority (>50%)
    # -------------------------------------------------------------------------
    if majority_pct > 0.5:
        # Fill unknown-country slots with the majority country for genre inference
        filled: List[Dict] = []
        for a in artists_info:
            if a["country"] is None:
                filled.append({"country": majority_country, "genre": None})
            else:
                filled.append(a)

        majority_artists = [a for a in filled if a["country"] == majority_country]
        genre = infer_genre_by_country(majority_artists)
        return majority_country, genre

    # -------------------------------------------------------------------------
    # Rule 2: Exact 50/50 split between 2 countries
    # -------------------------------------------------------------------------
    if majority_pct == 0.5:
        if distinct_countries == 2:
            majority_artists = [a for a in known if a["country"] == majority_country]
            genre = infer_genre_by_country(majority_artists)
            return majority_country, genre
        return "Multi-country", "Multi-genre"

    # -------------------------------------------------------------------------
    # Rule 3: Relative majority (<50%), same continent, ≤2 countries
    # -------------------------------------------------------------------------
    if distinct_continents == 1 and distinct_countries <= 2:
        majority_artists = [a for a in known if a["country"] == majority_country]
        genre = infer_genre_by_country(majority_artists)
        return majority_country, genre

    # -------------------------------------------------------------------------
    # Rule 4: Everything else
    # -------------------------------------------------------------------------
    return "Multi-country", "Multi-genre"


# ============================================================================
# ARTIST INFO RESOLUTION
# ============================================================================
def get_artist_info(
    artist_names: str,
    artist_lookup: Dict[str, Tuple[str, str]],
) -> List[Dict]:
    """
    Resolve each artist in a track's "Artist Names" field against the lookup
    dict.

    Parameters
    ----------
    artist_names : str
        Raw "Artist Names" string from the chart row.
    artist_lookup : dict
        Dict returned by `load_artist_lookup()`, mapping normalized names to
        `(country, macro_genre)`.

    Returns
    -------
    list of dict
        One entry per artist with keys `'name'`, `'country'`, `'genre'`.
        Artists not found in the lookup get `None` for country and genre.
    """
    names = parse_artist_list(artist_names)
    if not names:
        return []

    result = []
    for name in names:
        key = normalize_name(name)
        country, genre = artist_lookup.get(key, (None, None))
        result.append({"name": name, "country": country, "genre": genre})
    return result
