"""
Stopwords - False-Positive Filter for Genre Extraction
============================================================================
Canonical set of stopwords used by the genre extraction pipeline to filter
out false-positive candidates. These tokens are common descriptors or
nationality adjectives that frequently precede a real genre in prose
(e.g., "American pop singer", "award-winning rock band") but are **not**
themselves musical genres.

The set is consumed by `genre_detector` (and by `wikipedia.py` via a local
mirror) during regex and keyword extraction, before candidates are passed
to `GENRE_MAPPINGS` for normalization.

Features
--------
- Nationality and demonym stopwords (English adjectives such as
  `"american"`, `"british"`, `"korean"`, `"brazilian"`, `"nigerian"`,
  etc.) covering the most common origins encountered in artist metadata.
- Generic praise and award descriptors (`"famous"`, `"award-winning"`,
  `"grammy-winning"`, `"best-selling"`, `"legendary"`, `"iconic"`, etc.)
  that appear in descriptive prose but never name a genre.
- Single lowercase-token entries, so membership tests can be performed
  directly on regex captures without normalization.

Dependencies
------------
- Internal: none (this is a leaf data module).
- External: none (pure Python data).

Requirements
------------
- Python 3.7+
- No external packages or environment variables required.

Notes
-----
- All entries are **lowercase** and **stripped**. Consumers must lowercase
  candidate strings before testing membership; this module does not
  perform any normalization on its own.
- Multi-word entries (`"south african"`, `"award-winning"`,
  `"best-selling"`) are preserved as single strings with internal spaces
  or hyphens. Consumers doing token-level filtering must therefore test
  both individual tokens and joined n-grams (e.g., `" ".join(pair)`).
- This set is a **curated subset**, not an exhaustive list of all
  demonyms and praise words. It targets the adjectives most commonly
  encountered in English-language Wikipedia summaries and infoboxes.
  Adding entries is safe; removing them may re-introduce false positives
  in genre extraction.
- `wikipedia.py` currently maintains a **local superset**
  (`GENRE_STOPWORDS_FOR_WIKIPEDIA`) that duplicates these entries plus
  additional regional and scene-specific terms. Any change to this module
  should be mirrored in that local set until the duplication is
  consolidated into a single shared module.
- Purely descriptive musical terms that could plausibly name a genre
  (e.g., `"classical"`, `"traditional"`) are **intentionally excluded**
  from this set; only unambiguous non-genre tokens belong here.
- This module is pure data: no I/O, no side effects, deterministic on
  import.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

from typing import Set


# ============================================================================
# STOPWORDS — FALSE-POSITIVE FILTER
# ============================================================================
# All entries are lowercase and stripped. Multi-word entries are preserved
# as single strings (e.g., 'south african', 'award-winning').

GENRE_STOPWORDS: Set[str] = {
    # =========================================================================
    # NATIONALITIES / DEMONYMS
    # =========================================================================
    'american',
    'british',
    'canadian',
    'australian',
    'indian',
    'korean',
    'japanese',
    'mexican',
    'spanish',
    'french',
    'german',
    'italian',
    'brazilian',
    'argentine',
    'colombian',
    'chilean',
    'peruvian',
    'venezuelan',
    'cuban',
    'dominican',
    'african',
    'nigerian',
    'south african',
    'kenyan',
    'egyptian',
    'moroccan',
    'israeli',
    'turkish',
    'russian',
    'ukrainian',
    'polish',
    'swedish',
    'norwegian',
    'danish',
    'finnish',
    'dutch',
    'belgian',
    'swiss',
    'austrian',
    'portuguese',
    'greek',
    'irish',
    'scottish',
    'welsh',
    'english',

    # =========================================================================
    # GENERAL DESCRIPTORS (NOT GENRES)
    # =========================================================================
    'famous',
    'popular',
    'well-known',
    'acclaimed',
    'award-winning',
    'multi-platinum',
    'grammy',
    'grammy-winning',
    'oscar',
    'oscar-winning',
    'best-selling',
    'successful',
    'influential',
    'legendary',
    'iconic',
}
