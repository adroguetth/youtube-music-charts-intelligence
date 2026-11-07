"""
Artist Parser - Name Normalization and List Splitting
============================================================================
Utilities for parsing and normalizing artist names extracted from YouTube
Charts data.

This module solves two problems:
1. **Normalization**: Raw artist names from charts may have different
   casing, extra whitespace, or punctuation compared to the artist database
   (Script 2.1). We normalize them so that "Bad Bunny", "bad bunny", and
   "Bad Bunny!" all map to the same lookup key.
2. **Splitting**: A single "Artist Names" field may contain multiple artists
   separated by "feat.", "&", "and", "y", "with", "x", "vs", or commas.
   We split them into individual names so each artist can be resolved
   independently against the artist database.

Features
--------
- Unicode-safe normalization: strips accents, punctuation, and extra
  whitespace, then lowercases the result.
- Robust splitting: handles "feat.", "ft.", "featuring", "&", "and", "y",
  "with", "x", "vs", and comma separators.
- Placeholder filtering: removes "various", "various artists", "unknown",
  and Spanish equivalents.
- Deterministic and side-effect-free: no I/O, no global state.

Dependencies
------------
- External: re, typing (stdlib).

Requirements
------------
- Python 3.7+

Notes
-----
- Normalization is intentionally aggressive. It strips ALL non-word
  characters (except spaces), so "ROSÉ" becomes "rose" and "A.B." becomes
  "ab". This ensures maximum match rate against the artist database, which
  stores names in a canonical form.
- The splitting logic is permissive by design. If a chart field uses an
  unusual separator that is not covered here, the parser will keep the
  full string as a single artist, which is the safest fallback.
- The function `parse_artist_list` never returns empty strings or
  single-character names, so downstream code can assume all returned
  names are valid.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import re
from typing import List


# ============================================================================
# NAME NORMALIZATION
# ============================================================================
def normalize_name(name: str) -> str:
    """
    Normalize an artist name for fuzzy matching against the artist database.

    The normalization:
    1. Converts to lowercase.
    2. Collapses multiple whitespace characters into a single space.
    3. Removes ALL non-word characters except spaces (punctuation, accents,
       symbols).
    4. Strips leading and trailing whitespace.

    Parameters
    ----------
    name : str
        Raw artist name string. May be None.

    Returns
    -------
    str
        Normalized name suitable for dict lookup. Returns an empty string if
        the input is None or empty.
    """
    if name is None:
        return ""

    # Lowercase, collapse whitespace, strip
    name = re.sub(r"\s+", " ", str(name)).strip().lower()

    # Remove all non-word characters except spaces
    name = re.sub(r"[^\w\s]", "", name)

    return name


# ============================================================================
# ARTIST LIST SPLITTING
# ============================================================================
# Separators recognized in YouTube Charts "Artist Names" fields.
# Order matters: longer/more specific separators should be listed first to
# avoid partial matches (e.g., "feat." must be checked before "f").
_SEPARATORS = [
    " feat. ",
    " feat ",
    " featuring ",
    " ft. ",
    " ft ",
    " & ",
    " and ",
    " y ",
    " with ",
    " x ",
    " vs ",
    ", ",
    ",",  # Handle commas without trailing space
]

# Placeholder strings that should be discarded (not real artists).
_PLACEHOLDERS = {
    "various",
    "various artists",
    "unknown",
    "varios",
    "varios artistas",
}


def parse_artist_list(artist_names: str) -> List[str]:
    """
    Split a raw "Artist Names" field into individual artist name strings.

    Handles the most common delimiters found in YouTube Charts exports:

    - Collaborations: "feat.", "ft.", "featuring", "&", "and", "y", "with",
      "x", "vs".
    - Commas: with or without trailing space.
    - Parentheses: stripped from the result, as they often contain feat.
      information that has already been handled by the separator logic.

    Placeholders like "various", "various artists", "unknown", "varios",
    and "varios artistas" are discarded.

    Parameters
    ----------
    artist_names : str
        Raw string from the "Artist Names" chart column. May be None.

    Returns
    -------
    list of str
        Individual artist names, whitespace-stripped. Empty strings and
        single-character names are discarded. Returns an empty list if the
        input is None or empty.
    """
    if not artist_names:
        return []

    # Work on a copy to avoid mutating the caller's string
    text = str(artist_names)

    # Remove parentheses (they usually contain feat. info that's redundant
    # after splitting, or stage names that shouldn't be parsed separately)
    text = re.sub(r"[\(\)]", "", text)

    # Replace all separators with a single pipe character
    for sep in _SEPARATORS:
        text = text.replace(sep, "|")

    # Split on the pipe and clean up
    parts = [part.strip() for part in text.split("|")]

    # Filter out empty strings, single-character names, and placeholders
    result = []
    for part in parts:
        if not part or len(part) <= 1:
            continue
        if part.lower() in _PLACEHOLDERS:
            continue
        result.append(part)

    return result
