"""
Dictionaries - Static Data for Song Catalog Enrichment
============================================================================
Package initialization and public API surface for the static data used by
the song catalog builder.

This package aggregates two independent dictionaries:
1. `continent_map` — Country → Continent mapping.
2. `genre_hierarchy` — Country → ordered list of macro-genre priorities.

The separation allows the static data to be updated independently of the
codebase (e.g., adding a new country or reordering genre priorities) without
touching any logic.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from .continent_map import COUNTRY_TO_CONTINENT
from .genre_hierarchy import DEFAULT_COUNTRY, DEFAULT_GENRE, GENRE_HIERARCHY

__all__ = [
    "COUNTRY_TO_CONTINENT",
    "GENRE_HIERARCHY",
    "DEFAULT_GENRE",
    "DEFAULT_COUNTRY",
]
