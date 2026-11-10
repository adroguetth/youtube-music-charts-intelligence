"""
Main - Entry Point for the Weekly Report Generator
============================================================================
Command-line entry point for the `4_report_generator` package.

This module acts as a thin orchestrator. It coordinates the pipeline by
calling the appropriate `core` and `report` modules, without containing
any business logic itself.

Workflow:
    1. Resolve the reporting period (explicit --week, or the most recent
       enriched DB available in the archive directory).
    2. Load the enriched chart DB for that week.
    3. For each requested language (en, es):
        3a. Generate the notebook via `report.notebook.generate_notebook`.
        3b. Save it under `Notebook_<LANG>/weekly/`.
    4. Print summary statistics.

Features
--------
- Executable as a script:
      python scripts/4_report_generator/main.py --language both
- Proper exit codes for CI/CD integration (0 = success, 1 = error).

Dependencies
------------
- Internal: `.config` (paths, logger), `.core.periods` (previous_week,
  week_from_label), `.core.db` (latest_week_label, load_week),
  `.report.notebook` (generate_notebook).
- External: argparse, sys, datetime (stdlib).

Notes
-----
- No AI integration in v1.0. The `insights` hook exists in
  `generate_notebook` and will be wired here in v2.0 via a
  `--with-ai` flag.
- The directory name `4_report_generator` starts with a digit, so this
  file is meant to be run in script mode, not as `-m`. It bootstraps
  `sys.path` at the top so that absolute imports (`from core...`,
  `from report...`, `from config...`) work regardless of the current
  working directory.
- This module is deliberately kept minimal. New logic belongs in the
  appropriate submodule.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# sys.path bootstrap (script-mode execution)
# ---------------------------------------------------------------------------
# When this file is executed as `python scripts/4_report_generator/main.py`,
# Python adds `scripts/4_report_generator/` to sys.path automatically, so
# `from core...`, `from report...` and `from config...` resolve. The insert
# below is a safety net for cases where the file is exec'd via runpy or a
# wrapper that does not set sys.path.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import argparse
from datetime import date, datetime

from config import ARCHIVE_DIR, logger, notebook_dir
from core.db import latest_week_label, load_week
from core.periods import previous_week, week_from_label
from report.notebook import generate_notebook

# ============================================================================
# CONSTANTS
# ============================================================================
LANGUAGES: tuple[str, ...] = ("en", "es")


# ============================================================================
# ARGUMENT PARSING
# ============================================================================
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="4_report_generator",
        description="Generate the weekly music charts report notebook(s).",
    )
    parser.add_argument(
        "--language",
        choices=["en", "es", "both"],
        default="both",
        help="Language(s) to generate. Default: both.",
    )
    parser.add_argument(
        "--week",
        type=str,
        default=None,
        metavar="YYYY-WXX",
        help="Explicit ISO week to report (e.g. 2026-W46). "
             "If omitted, the most recent enriched DB is used.",
    )
    parser.add_argument(
        "--ref-date",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="Reference date. Resolves the ISO week immediately before it. "
             "Ignored if --week is given. Defaults to the most recent DB.",
    )
    return parser.parse_args(argv)


def _resolve_week_label(args: argparse.Namespace) -> str:
    """
    Resolve which week label to report.

    Priority:
        1. --week (explicit label)
        2. --ref-date (week before the given date)
        3. most recent enriched DB in ARCHIVE_DIR
    """
    if args.week:
        return args.week
    if args.ref_date:
        return previous_week(args.ref_date).label
    return latest_week_label(ARCHIVE_DIR)


# ============================================================================
# MAIN
# ============================================================================
def main(argv: list[str] | None = None) -> int:
    """
    Execute the weekly report generation pipeline.

    Returns
    -------
    int
        Exit code (0 = success, 1 = critical error).
    """
    logger.info("\n" + "=" * 70)
    logger.info("📊 WEEKLY MUSIC CHARTS REPORT GENERATOR (v1.0 — no AI)")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    args = _parse_args(argv)

    # -------------------------------------------------------------------------
    # Phase 1: Resolve week label and period
    # -------------------------------------------------------------------------
    logger.info("\n1. 📅 RESOLVING WEEK...")
    try:
        label = _resolve_week_label(args)
        period = week_from_label(label)
        logger.info(f"   ✅ Week: {period.label} ({period.start} → {period.end})")
    except Exception as e:
        logger.error(f"   ❌ {e}")
        return 1

    # -------------------------------------------------------------------------
    # Phase 2: Load enriched data
    # -------------------------------------------------------------------------
    logger.info(f"\n2. 📖 LOADING ENRICHED DATA FOR {period.label}...")
    try:
        df = load_week(period.label, ARCHIVE_DIR)
        logger.info(f"   ✅ {len(df)} songs loaded, {df.shape[1]} columns")
    except Exception as e:
        logger.error(f"   ❌ {e}")
        return 1

    # -------------------------------------------------------------------------
    # Phase 3: Generate notebooks per language
    # -------------------------------------------------------------------------
    languages = LANGUAGES if args.language == "both" else (args.language,)
    logger.info(f"\n3. 📝 GENERATING NOTEBOOKS ({', '.join(languages)})...")

    for lang in languages:
        out_path = notebook_dir(lang) / f"youtube_charts_{period.label}.ipynb"
        try:
            generate_notebook(df, period, out_path, lang)
            logger.info(f"   ✅ {lang.upper()}: {out_path}")
        except Exception as e:
            logger.error(f"   ❌ {lang.upper()}: {e}")
            return 1

    # -------------------------------------------------------------------------
    # Phase 4: Summary
    # -------------------------------------------------------------------------
    logger.info("\n4. 📊 FINAL SUMMARY:")
    logger.info(f"   📅 Week:      {period.label}")
    logger.info(f"   🎵 Songs:     {len(df)}")
    logger.info(f"   🌍 Countries: {df['artist_country'].nunique()}")
    logger.info(f"   🎼 Genres:    {df['macro_genre'].nunique()}")
    logger.info(f"   📝 Notebooks: {', '.join(languages)}")

    logger.info("\n" + "=" * 70)
    logger.info("✅ REPORT GENERATION COMPLETED SUCCESSFULLY")
    logger.info("=" * 70)

    return 0


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    sys.exit(main())
