"""
CSV Persistence
============================================================================
Canonical CSV serialization and normalized reads.

Rows are cleaned and reassembled before serialization, then written with the
exact canonical column order. Reads tolerate the three encodings emitted by the
legacy pipeline and by the official YouTube export.

Features
--------
- Canonical column order shared with SQLite.
- Encoding fallback chain: UTF-8, UTF-8 with BOM, Latin-1.
- Synthetic-flag detection on read.

Dependencies
------------
- Internal: config, core.reassembler, models.chart.
- External: csv, logging, pathlib (stdlib).
- Downstream: core.downloader, persistence.sqlite_handler, __main__.

Requirements
------------
- Python 3.10+

Notes
-----
- A partially-read file is cleared before the next encoding is attempted, so
  rows are never duplicated across fallback attempts.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List

from ..config import CANONICAL_COLUMNS
from ..core.reassembler import clean_extracted_rows, reassemble_split_rows
from ..models.chart import ChartData, ChartEntry

log = logging.getLogger("youtube_charts")


# ============================================================================
# CONSTANTS
# ============================================================================
SYNTHETIC_COLUMNS = ("is_synthetic", "is-synthetic")
_ENCODINGS = ("utf-8", "utf-8-sig", "latin-1")


# ============================================================================
# WRITE
# ============================================================================
def save_rows_to_csv(rows: List[Dict[str, Any]], path: Path) -> Path:
    """Clean, reassemble and normalize rows, then write the canonical CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = clean_extracted_rows(rows)
    rows = reassemble_split_rows(rows)
    entries = [
        ChartEntry.from_mapping(row, rank_fallback=index)
        for index, row in enumerate(rows, start=1)
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        writer.writerows(entry.to_row() for entry in entries)
    log.info("CSV written: %s (%d rows)", path, len(entries))
    return path


# ============================================================================
# READ
# ============================================================================
def read_csv_normalized(path: Path) -> ChartData:
    """Read a CSV into typed entries, tolerating the three common encodings."""
    entries: List[ChartEntry] = []
    has_synthetic_flag = False

    for encoding in _ENCODINGS:
        try:
            with open(path, "r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    return ChartData(source=str(path))
                has_synthetic_flag = any(
                    (name or "").strip().lower() in SYNTHETIC_COLUMNS
                    for name in reader.fieldnames
                )
                for index, raw in enumerate(reader, start=1):
                    entries.append(ChartEntry.from_mapping(raw, rank_fallback=index))
            break
        except UnicodeDecodeError:
            entries.clear()
            continue

    return ChartData(
        source=str(path),
        entries=entries,
        has_synthetic_flag=has_synthetic_flag,
    )
