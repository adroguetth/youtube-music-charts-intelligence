"""
Primitive Parsers
============================================================================
Pure parsing and heuristic helpers used by every extractor and persistence
layer. No I/O, no logging, no global state: every function is deterministic and
safe to unit-test in isolation.

Features
--------
- View-count parsing for ``1,234,567``, ``5.2M``, ``1.1B`` and ``850K``.
- Lenient integer parsing that strips currency, separators and noise.
- Cell heuristics used to reassemble rows split by the DOM extractor.

Dependencies
------------
- Internal: none (leaf module).
- External: re, typing (stdlib).
- Downstream: models.chart, core.reassembler.

Requirements
------------
- Python 3.10+

Notes
-----
- ``parse_views`` accepts the Spanish UI suffixes ``views``,
  ``reproducciones`` and ``vistas`` used by charts.youtube.com.
- Preserved quirk: ``"5.2M"`` parses as 52 when fed to ``parse_int``, which is
  what the legacy script did for the periods column.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import re
from typing import Any, Optional


# ============================================================================
# REGULAR EXPRESSIONS AND CONSTANTS
# ============================================================================
_VIEWS_SUFFIX_RE = re.compile(r"(views|reproducciones|vistas)$", re.IGNORECASE)
_FIRST_NUMBER_RE = re.compile(r"[\d.]+")
_NON_DIGITS_RE = re.compile(r"[^0-9-]")

_MULTIPLIERS = {
    "k": 1_000,
    "m": 1_000_000,
    "b": 1_000_000_000,
}


# ============================================================================
# PARSERS
# ============================================================================
def clean_text(value: Any) -> str:
    """Return a stripped string, mapping ``None`` to an empty string."""
    if value is None:
        return ""
    return str(value).strip()


def parse_views(value: Any) -> Optional[int]:
    """Parse ``1,234,567``, ``5.2M``, ``1.1B`` or ``850K`` into an integer."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip().replace(",", "").replace(" ", "")
    text = _VIEWS_SUFFIX_RE.sub("", text).strip()
    if not text:
        return None

    multiplier = 1
    suffix = text[-1].lower()
    if suffix in _MULTIPLIERS:
        multiplier = _MULTIPLIERS[suffix]
        text = text[:-1]

    try:
        return int(float(text) * multiplier)
    except ValueError:
        match = _FIRST_NUMBER_RE.search(text)
        if not match:
            return None
        try:
            return int(float(match.group(0)) * multiplier)
        except ValueError:
            return None


def parse_int(value: Any) -> Optional[int]:
    """Parse a loosely formatted integer, dropping any non-numeric noise."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    digits = _NON_DIGITS_RE.sub("", str(value))
    if not digits or digits == "-":
        return None
    try:
        return int(digits)
    except ValueError:
        return None


# ============================================================================
# CELL HEURISTICS
# ============================================================================
def looks_numeric(value: str) -> bool:
    """True when the cell is a metric (views, rank, periods) and not a name."""
    if not value:
        return False
    compact = value.replace(",", "").replace(".", "").strip()
    if compact.isdigit():
        return True
    if (
        len(compact) >= 2
        and compact[-1].lower() in _MULTIPLIERS
        and compact[:-1].isdigit()
    ):
        return True
    return False


def looks_like_views(value: str) -> bool:
    """True when the cell parses as a view count of at least 100k."""
    if not value:
        return False
    parsed = parse_views(value)
    return parsed is not None and parsed >= 100_000


def looks_like_period(value: str) -> bool:
    """True when the cell is a plausible weeks-on-chart counter."""
    if not value:
        return False
    try:
        number = int(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return False
    return 1 <= number <= 300
