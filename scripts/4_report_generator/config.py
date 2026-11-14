"""
Configuration - Paths, Logger and Environment Flags
============================================================================
Centralised configuration for the `4_report_generator` package.

Responsibilities
----------------
- Resolve repository paths (archive dir, notebook outputs, caches).
- Configure a package-level logger with a consistent output format.
- Provide helpers to resolve language-specific directories.
- Load environment variables for AI services (Groq, Google, DeepSeek, Meta).

Notes
-----
- Paths are resolved relative to the repository root, computed from this
  file's location. Do not hardcode absolute paths.
- The repository root is computed with `parents[2]`, not `parents[3]`.
  `config.py` lives inside `4_report_generator/`, so:
      parents[0] = 4_report_generator/
      parents[1] = scripts/
      parents[2] = <repo root>
- API keys are read from environment variables. If they are not set, the
  AI generation will be skipped gracefully (the report will still be
  generated with charts and tables).
- The `ai_budget.json` file lives at the root of the repository.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

# ============================================================================
# REPOSITORY ROOT
# ============================================================================
# config.py → 4_report_generator → scripts → <repo root>
# parents[0] = 4_report_generator/
# parents[1] = scripts/
# parents[2] = <repo root>
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

# ============================================================================
# PATHS
# ============================================================================
# Input: enriched weekly DBs produced by `3_enrich_chart_data`
ARCHIVE_DIR: Path = REPO_ROOT / "charts_archive" / "3_enrich-chart-data"

# Output: notebooks per language
NOTEBOOK_DIR_EN: Path = REPO_ROOT / "notebook_en" / "weekly"
NOTEBOOK_DIR_ES: Path = REPO_ROOT / "notebook_es" / "weekly"

# Cache for AI responses
CACHE_AI_DIR: Path = REPO_ROOT / "cache_ai"

# AI Budget file
AI_BUDGET_FILE: Path = REPO_ROOT / "ai_budget.json"

# ============================================================================
# AI ENVIRONMENT VARIABLES
# ============================================================================
GROQ_API_KEY: str | None = os.environ.get("GROQ_API_KEY")
GOOGLE_API_KEY: str | None = os.environ.get("GOOGLE_API_KEY")
DEEPSEEK_API_KEY: str | None = os.environ.get("DEEPSEEK_API_KEY")
META_API_KEY: str | None = os.environ.get("META_API_KEY")

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
