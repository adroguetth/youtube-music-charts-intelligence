"""
Configuration - Paths, Logger and Language Helpers
============================================================================
Centralised configuration for the `4_report_generator` package.

Responsibilities
----------------
- Resolve repository paths (archive dir, notebook outputs, caches).
- Configure a package-level logger with a consistent output format.
- Provide helpers to resolve language-specific directories.

Notes
-----
- Paths are resolved relative to the repository root, computed from this
  file's location. Do not hardcode absolute paths.
- The logger is created here and imported by every submodule to guarantee
  a single, consistent output stream. Importing this module multiple
  times does not duplicate handlers.
- This module contains no business logic. Only paths, logging setup and
  small path helpers.
- The cache directories are declared even though v1.0 does not use them.
  They will hold AI-generated insights in v2.0. Declaring them now keeps
  every output path centralised in one file.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path

# ============================================================================
# REPOSITORY ROOT
# ============================================================================
# config.py → 4_report_generator → scripts → <repo root>
REPO_ROOT: Path = Path(__file__).resolve().parents[3]

# ============================================================================
# PATHS
# ============================================================================
# Input: enriched weekly DBs produced by `3_enrich_chart_data`
ARCHIVE_DIR: Path = REPO_ROOT / "charts_archive" / "3_enrich-chart-data"

# Output: notebooks per language
NOTEBOOK_DIR_EN: Path = REPO_ROOT / "Notebook_EN" / "weekly"
NOTEBOOK_DIR_ES: Path = REPO_ROOT / "Notebook_ES" / "weekly"

# Cache: reserved for v2.0 (AI insights). Declared here so that every
# output path is centralised in one file.
CACHE_DIR_EN: Path = NOTEBOOK_DIR_EN / "cache"
CACHE_DIR_ES: Path = NOTEBOOK_DIR_ES / "cache"

# ============================================================================
# LOGGER
# ============================================================================
logger = logging.getLogger("report_generator")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

# ============================================================================
# HELPERS
# ============================================================================
def notebook_dir(language: str) -> Path:
    """
    Return the output directory for a given language.

    Parameters
    ----------
    language : str
        ``"en"`` or ``"es"``.

    Returns
    -------
    Path
        Directory where the notebook for that language must be written.

    Raises
    ------
    ValueError
        If `language` is not supported.
    """
    if language == "en":
        return NOTEBOOK_DIR_EN
    if language == "es":
        return NOTEBOOK_DIR_ES
    raise ValueError(f"Unsupported language: {language}")


def cache_dir(language: str) -> Path:
    """
    Return the cache directory for a given language.

    Parameters
    ----------
    language : str
        ``"en"`` or ``"es"``.

    Returns
    -------
    Path
        Directory reserved for cached artifacts (AI insights in v2.0).

    Raises
    ------
    ValueError
        If `language` is not supported.
    """
    if language == "en":
        return CACHE_DIR_EN
    if language == "es":
        return CACHE_DIR_ES
    raise ValueError(f"Unsupported language: {language}")
