"""
Macro Genres - Canonical Genre Target Definitions
============================================================================
Canonical list of all recognized macro-genres used by the genre detection
and ranking pipeline. This module is the **single source of truth** for the
set of valid macro-genre targets: every macro-genre referenced elsewhere
(e.g., as the first element of `GENRE_MAPPINGS` tuples, in
`COUNTRY_GENRE_PRIORITY` lists, or in `force_macro` / `map_generic_to`
fields of `COUNTRY_SPECIFIC_RULES`) must be a member of `MACRO_GENRES`.

It also exposes `GENERIC_MACROS`, a subset of macro-genres considered
"generic" (Anglo-centric mainstream categories) that may be remapped to
region-specific genres when country context is available (e.g., `"Pop"` →
`"K-Pop/K-Rock"` for a South Korean artist).

Features
--------
- `MACRO_GENRES`: complete, alphabetically ordered list of all valid
  macro-genre targets, spanning global mainstream categories and regional
  scenes (Latin urban, East Asian pop idioms, African dance genres,
  European folk styles, Indigenous/Pacific scenes, etc.).
- `GENERIC_MACROS`: subset of mainstream macro-genres eligible for
  country-based remapping via `COUNTRY_SPECIFIC_RULES.map_generic_to`.
- Deterministic and side-effect-free: consumed at import time by
  `genre_detector`, `country_rules`, and `genres` modules.

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
- **Integrity invariant**: every string in `MACRO_GENRES` must be
  referenced consistently (exact spelling, exact spacing, exact
  capitalization, exact diacritics) by consumers. Common pitfalls:
  - Space around `/` matters: `"K-Pop/K-Rock"` ≠ `"K-Pop / K-Rock"`.
  - Diacritics matter: `"Reggaetón/Trap Latino"` ≠ `"Reggaeton/Trap Latino"`,
    `"Electrónica/Dance"` ≠ `"Electronica/Dance"`,
    `"Folklore/Raíces"` ≠ `"Folklore/Raices"`.
  - Hyphens vs. spaces matter: `"Afro-soul"` ≠ `"Afro Soul"`.
- `MACRO_GENRES` is a **list**, not a set, to preserve deterministic
  iteration order. If you need O(1) membership checks, build a local
  `set(MACRO_GENRES)` once at module load in the consumer.
- `GENERIC_MACROS` is a **set** because membership tests are the primary
  operation (`if macro in GENERIC_MACROS: ...`) and order is irrelevant.
- Adding a new macro-genre requires touching **four** modules in sync:
  1. This file (`MACRO_GENRES`).
  2. `genres.py` (the new macro becomes valid as a mapping target).
  3. `country_rules.py` (optional — only if a country priority list or a
     `force_macro` / `map_generic_to` rule references it).
  4. `country_rules.COUNTRY_SPECIFIC_RULES` (optional — as above).
  Forgetting one of these causes silent ranking failures, not import-time
  errors.
- Removing a macro-genre is **breaking**: existing references in
  `GENRE_MAPPINGS`, `COUNTRY_GENRE_PRIORITY`, and `COUNTRY_SPECIFIC_RULES`
  would silently drop candidates. Run a full integrity check before
  removal.
- This module is pure data: no I/O, no side effects, deterministic on
  import.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

from typing import List, Set


# ============================================================================
# MACRO GENRES — CANONICAL GENRE TARGETS
# ============================================================================
# Complete list of all macro-genres used in the system.
# Ordering is alphabetical to ease maintenance; it is NOT semantic
# (unlike COUNTRY_GENRE_PRIORITY, whose ordering carries ranking meaning).

MACRO_GENRES: List[str] = [
    'Aboriginal Australian Pop/Rock',
    'Afghan Pop/Rock',
    'Afrobeats',
    'Afro-soul',
    'Alpine Folk',
    'Alternative',
    'Amapiano',
    'Apala',
    'Arabic Pop/Rock',
    'Bachata',
    'Balochi Pop/Rock',
    'Bangladeshi Pop/Rock',
    'Benga',
    'Bhutanese Pop/Rock',
    'Bongo',
    'Bongo Flava',
    'Bruneian Pop/Rock',
    'Burmese Pop/Rock',
    'Calypso / Soca',
    'Cambodian Pop/Rock',
    'Canzone Italiana',
    'Chalga',
    'Chanson',
    'Classical',
    'Coladeira',
    'Country',
    'Coupé-Décalé',
    'Cumbia',
    'C-Pop/C-Rock',
    'Dancehall/Reggae',
    'Dansband',
    'Electrónica/Dance',
    'Electroswing',
    'Ethio-jazz',
    'Experimental/Prog/Art',
    'Flamenco / Copla',
    'Folklore/Raíces',
    'Fuji',
    'Funaná',
    'Funk Brasileiro',
    'Gengetone',
    'Gnawa',
    'Hawaiian Pop/Rock',
    'Highlife',
    'Hip-Hop/Rap',
    'HK-Pop/HK-Rock',
    'Hmong Pop/Rock',
    'Indian Pop',
    'Indonesian Pop/Dangdut',
    'Isicathamiya',
    'Iskelmä',
    'Israeli Pop/Rock',
    'Jazz/Blues',
    'Jùjú',
    'J-Pop/J-Rock',
    'Kapuka',
    'Karen Pop/Rock',
    'Kashmiri Pop/Rock',
    'Kizomba/Zouk',
    'Klezmer',
    'Kuduro',
    'Kurdish Pop/Rock',
    'Kwaito',
    'K-Pop/K-Rock',
    'Lao Pop/Rock',
    'Laïko',
    'Macanese Pop/Rock',
    'Malaysian Pop',
    'Maldivian Pop/Rock',
    'Manele',
    'Māori Pop/Rock',
    'Marrabenta',
    'Maskandi',
    'Mbaqanga',
    'Mbalax',
    'Mbube',
    'Metal',
    'Mongolian Pop/Rock/Metal',
    'Nepali Pop/Rock',
    'Northeast Indian Pop/Rock',
    'Ogene',
    'OPM',
    'Pacific Electronica',
    'Pakistani Pop',
    'Papuan Pop/Rock',
    'Pasifika Pop/Rock',
    'PNG Pop/Rock',
    'Pop',
    'Post-Punk/New Wave',
    'Punk',
    'Q-pop/Q-rock',
    'R&B/Soul',
    'Reggaetón/Trap Latino',
    'Regional Mexicano',
    'Rock',
    'Roma Music',
    'Sakara',
    'Schlager',
    'Sertanejo',
    'Shangaan Electro',
    'Siberian Indigenous Pop/Rock',
    'Singaporean Pop',
    'Soukous/Ndombolo',
    'Sri Lankan Pop/Rock',
    'Taarab',
    'Tallava',
    'Tibetan Pop/Rock',
    'Timorese Pop/Rock',
    'Torres Strait Islander Pop/Rock',
    'Tropical/Salsa/Merengue/Bolero',
    'Turkish Pop/Rock',
    'Turbo-folk',
    'T-Pop/T-Rock',
    'TW-Pop/TW-Rock',
    'Uyghur Pop/Rock',
    'Vallenato',
    'V-Pop/V-Rock',
    'Zim Dancehall',
]


# ============================================================================
# GENERIC MACROS — SUBJECT TO COUNTRY-BASED REMAPPING
# ============================================================================
# Subset of macro-genres considered "generic" (mainstream Anglo categories)
# and eligible for remapping to region-specific genres when country context
# is available via COUNTRY_SPECIFIC_RULES.map_generic_to.
#
# Example: a South Korean artist tagged as "Pop" may be remapped to
# "K-Pop/K-Rock" because "Pop" ∈ GENERIC_MACROS and South Korea defines
# map_generic_to = "K-Pop/K-Rock".

GENERIC_MACROS: Set[str] = {
    "Pop",
    "Rock",
    "Hip-Hop/Rap",
    "R&B/Soul",
    "Electrónica/Dance",
    "Alternative",
    "Metal",
    "Punk",
    "Country",
    "Jazz/Blues",
    "Folklore/Raíces",
    "Classical",
}
