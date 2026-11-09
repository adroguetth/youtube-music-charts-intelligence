"""
Main - Entry Point for Report Generator
============================================================================
Command-line entry point for the `4_report_generator` package.

This module orchestrates the report generation pipeline:
1. Parses CLI arguments (period, language).
2. Loads the enriched data from the most recent database (Script 3 output).
3. Generates AI insights using DeepSeek (optional, based on API key).
4. Renders the final reports using Quarto (HTML and/or PDF).

Features
--------
- Executable as a module (`python -m scripts.4_report_generator`).
- Proper exit codes for CI/CD integration.
- Handles missing data or API failures gracefully.

Dependencies
------------
- Internal: `.config` (logger), `.utils.db_loader`, `.ai.insights`,
  `.builder.renderer`.
- External: argparse, sys (stdlib).

Requirements
------------
- Python 3.7+
- Quarto CLI installed and in the system PATH.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import argparse
import sys

from .config import logger
from .utils.db_loader import load_data_for_period
from .ai.insights import generate_insights
from .builder.renderer import render_report


def main() -> int:
    """
    Execute the report generation pipeline.

    Returns
    -------
    int
        Exit code (0 = success, 1 = error).
    """
    parser = argparse.ArgumentParser(
        description="Generate weekly music charts reports with AI insights."
    )
    parser.add_argument(
        "--period",
        type=str,
        choices=["weekly", "monthly", "quarterly", "yearly"],
        default="weekly",
        help="Time period for the report (default: weekly)"
    )
    parser.add_argument(
        "--lang",
        type=str,
        choices=["en", "es", "both"],
        default="both",
        help="Language for the report (default: both)"
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["html", "pdf", "both"],
        default="both",
        help="Output format (default: both)"
    )
    
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("📊 YOUTUBE CHARTS - REPORT GENERATOR")
    logger.info(f"   Period: {args.period.upper()} | Language: {args.lang.upper()} | Format: {args.format.upper()}")
    logger.info("=" * 70)

    # 1. Load Data
    try:
        logger.info(f"\n1. 📀 LOADING DATA FOR {args.period.upper()}...")
        df, week_str = load_data_for_period(args.period)
        logger.info(f"   ✅ Data loaded for week: {week_str}")
    except Exception as e:
        logger.error(f"   ❌ Failed to load data: {e}")
        return 1

    # 2. Determine output formats
    formats_to_render = ["html", "pdf"] if args.format == "both" else [args.format]

    # 3. Generate and Render for each language
    languages_to_render = ["en", "es"] if args.lang == "both" else [args.lang]

    for lang in languages_to_render:
        logger.info(f"\n2. 🤖 GENERATING AI INSIGHTS ({lang.upper()})...")
        ai_data = generate_insights(df, week_str, lang)
        
        if "error" in ai_data:
            logger.warning(f"   ⚠️ AI generation warning: {ai_data['error']}")
        else:
            logger.info("   ✅ AI insights generated successfully.")

        logger.info(f"\n3. 🎨 RENDERING REPORT ({lang.upper()})...")
        try:
            generated_files = render_report(
                week_str=week_str,
                ai_data=ai_data,
                language=lang,
                formats=formats_to_render
            )
            
            for file_path in generated_files:
                logger.info(f"   📄 Output: {file_path}")
                
        except Exception as e:
            logger.error(f"   ❌ Rendering failed for {lang.upper()}: {e}")
            return 1

    logger.info("\n" + "=" * 70)
    logger.info("✅ REPORT GENERATION COMPLETED SUCCESSFULLY")
    logger.info("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
