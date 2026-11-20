"""
Typed Chart Models
============================================================================
Typed chart rows and the single normalization boundary of the pipeline.

Extractors emit heterogeneous dictionaries; ``ChartEntry.from_mapping`` is the
only place where those dictionaries are coerced into canonical columns. The
persistence layers consume ``ChartEntry`` instances, so CSV and SQLite can never
drift apart.

Features
--------
- Canonical column set with alias resolution.
- Numeric parsing for ranks, periods and abbreviated view counts.
- Explicit synthetic-data flag preserved through every layer.
- Row serialization for CSV and parameterized SQLite inserts.

Dependencies
------------
- Internal: config (schema, aliases), utils.parsers.
- External: dataclasses, typing (stdlib).
- Downstream: persistence.csv_handler, persistence.sqlite_handler, fallbacks.

Requirements
------------
- Python 3.10+

Notes
-----
- ``rank_fallback`` is applied when the source has no usable rank; every
  visual-order-only extractor relies on it.
- Preserved quirk: ``"5.2M"`` in a periods column parses as 52, matching the
  behaviour of the legacy script.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from ..config import CANONICAL_COLUMNS, COLUMN_ALIASES
from ..utils.parsers import clean_text, parse_int, parse_views

SYNTHETIC_KEYS = ("is_synthetic", "_is_synthetic")


# ============================================================================
# ENTRY MODEL
# ============================================================================
@dataclass(slots=True)
class ChartEntry:
    """A single chart position, normalized to the canonical schema."""

    rank: Optional[int] = None
    previous_rank: Optional[int] = None
    track_name: str = ""
    artist_names: str = ""
    periods_on_chart: Optional[int] = None
    views: Optional[int] = None
    views_raw: str = ""
    growth: str = ""
    youtube_url: str = ""
    is_synthetic: int = 0

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any],
        rank_fallback: int = 0,
        is_synthetic: int = 0,
    ) -> "ChartEntry":
        """Normalize an extractor row.

        ``rank_fallback`` is applied when the source has no usable rank, which
        is the case for every extractor that preserves visual order only.
        """
        values: Dict[str, Any] = {column: "" for column in CANONICAL_COLUMNS}
        for key, value in raw.items():
            alias = str(key).strip().lower()
            canonical = COLUMN_ALIASES.get(alias, str(key).strip())
            if canonical in values:
                values[canonical] = value

        rank = parse_int(values.get("Rank")) or rank_fallback

        views_raw = clean_text(values.get("Views Raw") or values.get("Views"))
        views = parse_views(values.get("Views"))
        if views is not None:
            values["Views"] = views
            if not values.get("Views Raw"):
                values["Views Raw"] = views_raw
        else:
            views = None
            values["Views Raw"] = views_raw

        url = clean_text(values.get("YouTube URL"))
        if not url:
            video_id = raw.get("videoId") or raw.get("video_id")
            if video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"

        flag = is_synthetic
        for key in SYNTHETIC_KEYS:
            if key in raw:
                flag = _coerce_flag(raw[key])
                break

        return cls(
            rank=rank,
            previous_rank=parse_int(values.get("Previous Rank")),
            track_name=clean_text(values.get("Track Name")),
            artist_names=clean_text(values.get("Artist Names")),
            periods_on_chart=parse_int(values.get("Periods on Chart")),
            views=views,
            views_raw=clean_text(values.get("Views Raw")),
            growth=clean_text(values.get("Growth")),
            youtube_url=url,
            is_synthetic=flag,
        )

    def to_row(self) -> Dict[str, Any]:
        """Render the entry as a canonical CSV row (missing metrics as ``""``)."""
        return {
            "Rank": "" if self.rank is None else self.rank,
            "Previous Rank": "" if self.previous_rank is None else self.previous_rank,
            "Track Name": self.track_name,
            "Artist Names": self.artist_names,
            "Periods on Chart": (
                "" if self.periods_on_chart is None else self.periods_on_chart
            ),
            "Views": "" if self.views is None else self.views,
            "Views Raw": self.views_raw,
            "Growth": self.growth,
            "YouTube URL": self.youtube_url,
        }

    def to_db_values(self) -> List[Any]:
        """Values ordered as ``CANONICAL_COLUMNS`` for parameterized INSERTs."""
        return [
            self.rank,
            self.previous_rank,
            self.track_name,
            self.artist_names,
            self.periods_on_chart,
            self.views,
            self.views_raw,
            self.growth,
            self.youtube_url,
        ]


# ============================================================================
# WEEK MODEL
# ============================================================================
@dataclass(slots=True)
class ChartData:
    """A week's chart as read back from disk or produced by an extractor."""

    week_id: str = ""
    chart: str = "TopSongs"
    country: str = "global"
    source: str = ""
    entries: List[ChartEntry] = field(default_factory=list)
    has_synthetic_flag: bool = False

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def to_rows(self) -> List[Dict[str, Any]]:
        return [entry.to_row() for entry in self.entries]

    @property
    def real_count(self) -> int:
        """Number of rows that are not synthetic placeholders."""
        return sum(1 for entry in self.entries if not entry.is_synthetic)


# ============================================================================
# INTERNAL HELPERS
# ============================================================================
def _coerce_flag(value: Any) -> int:
    """Interpret the synthetic flag as written by CSV producers."""
    if isinstance(value, (int, float)):
        return int(value)
    text = clean_text(value).lower()
    if not text:
        return 0
    if text in ("1", "true", "yes", "y"):
        return 1
    try:
        return int(float(text))
    except ValueError:
        return 0
