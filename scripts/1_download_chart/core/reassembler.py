"""
Row Cleanup and Reassembly
============================================================================
Filters extractor noise and reconstructs songs whose fields were split across
several DOM rows.

The DOM extractor can emit one song as two or three rows with shifted fields
when the chart layout changes: title and artist in one row, views and previous
rank in another. The split pattern is not stable, so reconstruction is
heuristic: a text title plus text artist starts a song, subsequent numeric rows
are folded into it while key metrics are still missing, and leftover numeric
rows are discarded because their title is unrecoverable.

Features
--------
- Drops metadata, date and duplicate rows.
- Renumbers duplicated or out-of-range ranks while preserving visual order.
- Idempotent reassembly: well-formed rows pass through unchanged.

Dependencies
------------
- Internal: utils.parsers.
- External: logging, re, typing (stdlib).
- Downstream: persistence.csv_handler.

Requirements
------------
- Python 3.10+

Notes
-----
- Reassembly logs the row count before and after; a large drop is the first
  signal that the site layout changed.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from ..utils.parsers import (
    clean_text,
    looks_like_period,
    looks_like_views,
    looks_numeric,
    parse_int,
    parse_views,
)

log = logging.getLogger("youtube_charts")

# ============================================================================
# CONSTANTS
# ============================================================================
_BLOCKED_TITLES = {
    "release date",
    "release dates",
    "last week",
    "weekly views",
    "weekly top songs",
    "weekly top artists",
    "top songs",
    "top artists",
    "views",
    "rank",
    "artist",
    "track name",
    "new",
    "same",
}

_DATE_PATTERN = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2},\s*\d{4}$",
    re.IGNORECASE,
)
_MONTH_DAY_PATTERN = re.compile(r"^\d{1,2},\s*\d{4}$")


# ============================================================================
# CLEANUP
# ============================================================================
def clean_extracted_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop metadata rows, date rows and duplicates left by the extractors."""
    cleaned: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        title = clean_text(row.get("Track Name"))
        artist = clean_text(row.get("Artist Names"))
        if not title or not artist:
            continue
        if title.lower().strip() in _BLOCKED_TITLES:
            continue
        if _DATE_PATTERN.match(title) or _DATE_PATTERN.match(artist):
            continue
        if _MONTH_DAY_PATTERN.match(artist):
            continue

        key = title.lower() + "|" + artist.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(row)

    # Renumber when the extracted ranks are duplicated or clearly out of range;
    # visual order is preserved by the extractor, so appearance order wins.
    try:
        ranks = [int(parse_int(row.get("Rank")) or 0) for row in cleaned]
        if len(set(ranks)) != len(ranks) or (
            ranks and (min(ranks) != 1 or max(ranks) > 120)
        ):
            for index, row in enumerate(cleaned, start=1):
                row["Rank"] = index
        else:
            cleaned.sort(key=lambda row: int(parse_int(row.get("Rank")) or 999))
    except Exception:
        pass

    return cleaned


# ============================================================================
# RECONSTRUCTION
# ============================================================================
def _is_complete(song: Dict[str, Any]) -> bool:
    has_views = bool(song.get("Views")) and str(song.get("Views")) not in ("", "0")
    has_previous = song.get("Previous Rank") not in (None, "", 0)
    has_periods = song.get("Periods on Chart") not in (None, "")
    return has_views and has_previous and has_periods


def reassemble_split_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fold numeric-only rows back into the song they belong to.

    Idempotent: when the extractor produced well-formed rows this returns them
    unchanged.
    """
    if not rows:
        return rows

    reassembled: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for row in rows:
        title = clean_text(row.get("Track Name"))
        artist = clean_text(row.get("Artist Names"))
        title_is_text = bool(title) and not looks_numeric(title)
        artist_is_text = bool(artist) and not looks_numeric(artist)

        if title_is_text and artist_is_text:
            if current is not None:
                reassembled.append(current)
            current = dict(row)
            # On the leading row, "Views" usually holds the periods counter.
            views_cell = parse_int(row.get("Views"))
            if views_cell is not None and 1 <= views_cell <= 300:
                current["Periods on Chart"] = views_cell
                current["Views"] = ""  # filled from a later row
            continue

        if current is None or _is_complete(current):
            # Orphan numeric row, or a song that already has every metric.
            continue

        if looks_like_views(title) and (
            not current.get("Views") or str(current.get("Views")) == "0"
        ):
            parsed = parse_views(title)
            if parsed:
                current["Views"] = parsed
                current["Views Raw"] = title
        elif looks_like_period(title) and not current.get("Periods on Chart"):
            periods = parse_int(title)
            if periods is not None:
                current["Periods on Chart"] = periods

        if looks_like_period(artist) and current.get("Previous Rank") in (None, ""):
            previous = parse_int(artist)
            if previous is not None and 1 <= previous <= 100:
                current["Previous Rank"] = previous
        elif looks_like_views(artist) and (
            not current.get("Views") or str(current.get("Views")) == "0"
        ):
            parsed = parse_views(artist)
            if parsed:
                current["Views"] = parsed
                current["Views Raw"] = artist

        if row.get("YouTube URL") and not current.get("YouTube URL"):
            current["YouTube URL"] = row.get("YouTube URL", "")
        if row.get("Growth") and not current.get("Growth"):
            current["Growth"] = row.get("Growth", "")

    if current is not None:
        reassembled.append(current)

    for index, row in enumerate(reassembled, start=1):
        row["Rank"] = index

    if len(reassembled) != len(rows):
        log.info(
            "Reassembly: %d rows -> %d songs (%d orphan rows dropped)",
            len(rows),
            len(reassembled),
            len(rows) - len(reassembled),
        )
    return reassembled
