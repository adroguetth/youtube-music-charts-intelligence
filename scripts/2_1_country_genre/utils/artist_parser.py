"""
Artist Parser - Collaborator String Splitting
============================================================================
Utility module for parsing artist strings that contain multiple names
(featuring, collaborations, duets, etc.) into individual artist entries.
Chart data commonly concatenates collaborators with heterogeneous
separators and conventions, which must be normalized before names can be
matched against external APIs or stored individually.

This module is a leaf utility: it has no internal dependencies and no
side effects. It is consumed by `utils/__init__.py` and by the database
builder when inserting artists.

Features
--------
- Normalizes featuring markers (`feat.`, `ft.`, `featuring`) to a common
  comma separator.
- Replaces conjunction separators (`&`, `y`, `and`) with commas.
- Strips parentheses, which typically wrap featuring information rather
  than contributing a distinct artist.
- Filters out empty tokens, single-character tokens, and placeholder
  strings (e.g., `"various"`, `"unknown"`, `"varios artistas"`).

Dependencies
------------
- Internal: none (leaf utility).
- External: re, typing (stdlib).

Requirements
------------
- Python 3.7+
- No external packages or environment variables required.

Notes
-----
- The input is assumed to be a single concatenated artist string as found
  in chart CSV columns (e.g., `"Artist A feat. Artist B & Artist C"`).
  Passing an already-split list is out of scope.
- Splitting is applied **once** on commas after all normalizations.
  Multi-comma artist strings are handled correctly, but the function does
  not attempt to resolve ambiguous cases where a comma is part of a stage
  name (rare in practice; a known trade-off for simplicity).
- The `&` and `y` replacements are applied **without** a case-insensitive
  flag to avoid mangling names that contain those letters as part of a
  larger token (e.g., `"Yandel"`, `"A&B"`). The `and` replacement **is**
  case-insensitive because `"and"` as a standalone word is virtually never
  part of a proper name.
- Parentheses are stripped **before** splitting so their contents (often
  `"(feat. X)"`) do not end up as separate tokens. However, this also
  flattens any parenthetical stage names; consumers requiring exact name
  preservation should not use this function on such inputs.
- Placeholder filtering uses a lowercase comparison against a small
  curated set. Adding new placeholders is safe; consumers downstream
  should also guard against empty results.
- The function is pure and deterministic: given the same input, it always
  returns the same list, and it never mutates global state.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import re
from typing import List

# ============================================================================
# CONSTANTS
# ============================================================================
_FEAT_PATTERNS = [
    r"\s+feat\.?\s+",
    r"\s+ft\.?\s+",
    r"\s+featuring\s+",
]

_CONJUNCTION_PATTERNS_CASE_SENSITIVE = [
    r"\s+&\s+",
    r"\s+y\s+",
]

_CONJUNCTION_PATTERNS_CASE_INSENSITIVE = [
    r"\s+and\s+",
]

_PLACEHOLDER_NAMES = {
    "various",
    "various artists",
    "unknown",
    "varios",
    "varios artistas",
}

_MIN_ARTIST_LENGTH = 2


# ============================================================================
# ARTIST PARSING
# ============================================================================
def split_artists(artist_str: str) -> List[str]:
    """
    Split a string containing multiple artists into individual names.

    Handles common separators found in chart data:
    - Featuring markers: `feat.`, `ft.`, `featuring`.
    - Conjunctions: `&`, `and`, `y`.
    - Comma separators.
    - Parentheses (contents stripped along with the delimiters).

    Parameters
    ----------
    artist_str : str
        Raw artist string from chart data (e.g.,
        `"Artist A feat. Artist B & Artist C"`).

    Returns
    -------
    list of str
        Cleaned individual artist names, in the order they appear in the
        input. Returns an empty list when the input is empty, not a string,
        or consists entirely of placeholders.

    Notes
    -----
    - Featuring markers and conjunctions are normalized to commas before a
      single split, so the resulting order matches the source order.
    - Parentheses are removed **before** splitting to avoid their contents
      leaking into the output as spurious artists.
    - Single-character tokens and placeholders (`"various"`, `"unknown"`,
      `"varios artistas"`, etc.) are filtered out.
    - The `y` conjunction is matched **case-sensitively** to avoid
      mangling names containing that letter (e.g., `"Yandel"`). The `and`
      conjunction is matched case-insensitively because it is virtually
      never part of a proper name.
    """
    if not artist_str or not isinstance(artist_str, str):
        return []

    # --- Normalize featuring markers to commas ---
    for pattern in _FEAT_PATTERNS:
        artist_str = re.sub(pattern, ", ", artist_str, flags=re.IGNORECASE)

    # --- Replace case-sensitive conjunctions (`&`, `y`) ---
    for pattern in _CONJUNCTION_PATTERNS_CASE_SENSITIVE:
        artist_str = re.sub(pattern, ", ", artist_str)

    # --- Replace case-insensitive conjunctions (`and`) ---
    for pattern in _CONJUNCTION_PATTERNS_CASE_INSENSITIVE:
        artist_str = re.sub(pattern, ", ", artist_str, flags=re.IGNORECASE)

    # --- Strip parentheses (contents often contain feat. info) ---
    artist_str = re.sub(r"[\(\)]", "", artist_str)

    # --- Split on commas and strip whitespace ---
    artists = [a.strip() for a in artist_str.split(",")]

    # --- Filter empty and too-short entries ---
    artists = [a for a in artists if a and len(a) >= _MIN_ARTIST_LENGTH]

    # --- Filter placeholder names ---
    artists = [a for a in artists if a.lower() not in _PLACEHOLDER_NAMES]

    return artists
