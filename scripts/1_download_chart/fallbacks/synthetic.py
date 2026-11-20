"""
Synthetic Fallback Data
============================================================================
Deterministic placeholder rows for pipeline tests and explicit offline runs.

Synthetic data is never written to ``latest_chart.csv`` and every row is flagged
``is_synthetic=1`` so downstream consumers can exclude it.

Features
--------
- 100 deterministic rows matching the canonical schema.
- Explicit synthetic flag on every row.
- Guarded by ``--allow-fallback`` at the CLI level.

Dependencies
------------
- Internal: config, models.chart.
- External: csv, logging, pathlib (stdlib).
- Downstream: __main__ (only when ``--allow-fallback`` is set).

Requirements
------------
- Python 3.10+

Notes
-----
- The file name includes the week id, so fallback runs never masquerade as a
  real weekly download.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

from ..config import ARCHIVE_DIR, CANONICAL_COLUMNS, ensure_directories
from ..models.chart import ChartEntry

log = logging.getLogger("youtube_charts")


# ============================================================================
# CONSTANTS
# ============================================================================
FALLBACK_COLUMNS = CANONICAL_COLUMNS + ["is_synthetic"]


# ============================================================================
# GENERATION
# ============================================================================
def create_fallback_file(week_id: str, reason: str = "") -> Optional[Path]:
    """Write 100 deterministic placeholder rows for ``week_id``.

    Parameters
    ----------
    week_id : str
        ISO week identifier used in the file name.
    reason : str, optional
        Human-readable reason, logged with the warning.

    Returns
    -------
    Path or None
        Path to the generated CSV.

    Notes
    -----
    Every row is flagged ``is_synthetic=1``. The file name is distinct from
    ``latest_chart.csv`` so a fallback can never be mistaken for real data.
    """
    log.warning(
        "Creating SYNTHETIC fallback (not real data). Reason: %s",
        reason or "download failed",
    )
    ensure_directories()
    filename = ARCHIVE_DIR / f"fallback_chart_{week_id}.csv"

    with open(filename, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FALLBACK_COLUMNS)
        writer.writeheader()
        for rank in range(1, 101):
            raw = {
                "Rank": rank,
                "Previous Rank": max(1, rank - 1) if rank > 1 else 1,
                "Track Name": f"Popular Song {rank}",
                "Artist Names": f"Artist {chr(65 + ((rank - 1) % 26))} and Collaborators",
                "Periods on Chart": 10 + (rank % 40),
                "Views": 5_000_000 + (100 - rank) * 50_000,
                "Growth": f"{((101 - rank) / 100):.2f}%",
                "YouTube URL": f"https://www.youtube.com/watch?v=example{rank:03d}",
            }
            entry = ChartEntry.from_mapping(
                raw, rank_fallback=rank, is_synthetic=1
            )
            writer.writerow({**entry.to_row(), "is_synthetic": 1})

    log.warning("Fallback written to %s (100 SYNTHETIC rows)", filename)
    return filename
