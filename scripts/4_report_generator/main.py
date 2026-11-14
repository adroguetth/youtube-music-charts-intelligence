"""
Main - Entry Point for the Weekly Report Generator
============================================================================
Command-line entry point for the `4_report_generator` package.

Workflow:
    1. Resolve the reporting period.
    2. Load the enriched chart DB.
    3. For each requested language (en, es):
        3a. Generate AI insights (if API keys are configured).
        3b. Generate the notebook.
    4. Print summary statistics.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap for script mode
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import argparse
from datetime import date, datetime

import pandas as pd

from config import (
    ARCHIVE_DIR,
    DEEPSEEK_API_KEY,
    GOOGLE_API_KEY,
    GROQ_API_KEY,
    logger,
    notebook_dir,
)
from core.db import latest_week_label, load_week
from core.periods import previous_week, week_from_label
from core.ai.budget_manager import BudgetManager
from core.ai.cache import AICache
from core.ai.summarizer import TableSummarizer
from core.ai.writer import DeepSeekWriter
from report.notebook import generate_notebook
from report.sections import WEEKLY_SECTIONS

# ============================================================================
# CONSTANTS
# ============================================================================
LANGUAGES: tuple[str, ...] = ("en", "es")


# ============================================================================
# ARGUMENT PARSING
# ============================================================================
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the weekly report.")
    parser.add_argument("--language", choices=["en", "es", "both"], default="both")
    parser.add_argument("--week", type=str, default=None, help="YYYY-WXX")
    parser.add_argument("--ref-date", type=date.fromisoformat, default=None)
    parser.add_argument("--no-ai", action="store_true", help="Disable AI insights generation.")
    return parser.parse_args(argv)


def _resolve_week_label(args: argparse.Namespace) -> str:
    if args.week:
        return args.week
    if args.ref_date:
        return previous_week(args.ref_date).label
    return latest_week_label(ARCHIVE_DIR)


# ============================================================================
# AI INSIGHTS GENERATION
# ============================================================================
def _generate_ai_insights(df: pd.DataFrame, period_label: str, language: str, use_ai: bool) -> dict[str, str]:
    """
    Generates the AI insights for each section.
    Returns a dictionary mapping section_id -> markdown_text.
    """
    if not use_ai:
        return {}

    logger.info(f"   🧠 Generating AI insights ({language.upper()})...")
    
    # Initialize components
    cache = AICache()
    budget = BudgetManager()
    summarizer = TableSummarizer(groq_api_key=GROQ_API_KEY, google_api_key=GOOGLE_API_KEY)
    writer = DeepSeekWriter(api_key=DEEPSEEK_API_KEY)

    insights = {}

    # Sections that will have AI analysis (including top_songs)
    ai_sections = [
        "general_stats", "continents", "countries", "genre_analysis", 
        "top_songs", "video_metrics", "temporal_analysis", "collaborations"
    ]

    for section in ai_sections:
        if section not in WEEKLY_SECTIONS:
            continue

        # 1. Check Cache
        cached_data = cache.get(period_label, section, language)
        if cached_data:
            logger.info(f"      [Cache] {section}")
            insights[section] = cached_data["final_text"]
            continue

        # 2. Generate Markdown table (limited to save tokens)
        table_md = _get_table_markdown_for_section(df, section)
        if not table_md:
            logger.warning(f"      [AI] No table generated for {section}. Skipping.")
            continue

        # 3. Decide model and summarize
        model_name = budget.get_light_model()
        if not model_name:
            logger.warning(f"      [Budget] No models available for {section}.")
            continue

        raw_summary, model_used, tokens_summary = summarizer.summarize(table_md, model_name, language)
        
        if not raw_summary:
            logger.warning(f"      [AI] Failed to summarize {section}. Skipping.")
            continue

        # 4. Polish with DeepSeek
        final_text, tokens_writer = writer.polish(raw_summary, language)
        
        # 5. Record usage and save to cache
        budget.record_usage(model_used, tokens_summary, success=True)
        cache.save(period_label, section, language, {
            "summary": raw_summary,
            "final_text": final_text,
            "model_used": model_used
        })
        
        insights[section] = final_text
        logger.info(f"      ✅ {section} (via {model_used})")

    return insights


def _get_table_markdown_for_section(df: pd.DataFrame, section: str) -> str:
    """
    Calculates the specific table for a section and returns it as Markdown.
    Keeps tables small (head 5-10) to save tokens.
    """
    try:
        # Ensure 'continent' column exists
        if 'continent' not in df.columns:
            continents_map = {
                'North America': ['United States', 'Mexico', 'Canada', 'Puerto Rico'],
                'South America': ['Brazil', 'Argentina', 'Colombia', 'Chile', 'Peru', 'Venezuela'],
                'Europe': ['United Kingdom', 'Sweden', 'Germany', 'France', 'Spain', 'Italy', 'Netherlands', 'Turkey'],
                'Asia': ['India', 'South Korea', 'Japan', 'China', 'Indonesia', 'Pakistan', 'Philippines', 'Thailand', 'Vietnam'],
                'Africa': ['Nigeria', 'South Africa', 'Kenya', 'Ghana'],
                'Oceania': ['Australia', 'New Zealand'],
                'Middle East': ['Israel', 'UAE', 'Saudi Arabia']
            }
            def get_cont(c):
                for cont, countries in continents_map.items():
                    if c in countries: return cont
                return 'Other'
            df['continent'] = df['artist_country'].apply(get_cont)

        # Helper to format big numbers (M and K)
        def fmt_num(x):
            try:
                x = float(x)
                if x >= 1_000_000: return f"{x/1_000_000:.1f}M"
                if x >= 1_000: return f"{x/1_000:.1f}K"
                return f"{x:,.0f}"
            except: return str(x)

        if section == "general_stats":
            total_views = df['views'].sum()
            total_likes = df['likes'].sum()
            eng_rate = (total_likes / total_views * 100) if total_views > 0 else 0
            stats = pd.DataFrame({
                "Metric": ["Total Songs", "Unique Countries", "Unique Genres", "Total Views", "Total Likes", "Engagement Rate (%)"],
                "Value": [len(df), df['artist_country'].nunique(), df['macro_genre'].nunique(), fmt_num(total_views), fmt_num(total_likes), f"{eng_rate:.1f}%"]
            })
            return stats.to_markdown(index=False)
            
        elif section == "continents":
            t = df.groupby('continent').agg(songs=('track_name', 'count'), views=('views', 'sum')).reset_index().sort_values('songs', ascending=False)
            t['views'] = t['views'].apply(fmt_num)
            return t.to_markdown(index=False)
            
        elif section == "countries":
            t = df.groupby('artist_country').agg(songs=('track_name', 'count'), views=('views', 'sum')).reset_index().sort_values('songs', ascending=False).head(10)
            t['views'] = t['views'].apply(fmt_num)
            return t.to_markdown(index=False)
            
        elif section == "genre_analysis":
            # Agregamos engagement para que la IA pueda comparar popularidad vs fidelidad
            t = df.groupby('macro_genre').agg(songs=('track_name', 'count'), views=('views', 'sum'), engagement=('engagement', 'mean')).reset_index().sort_values('songs', ascending=False).head(10)
            t['views'] = t['views'].apply(fmt_num)
            t['engagement'] = t['engagement'].round(1).astype(str) + '%'
            return t.to_markdown(index=False)

        elif section == "top_songs":
            # Top 10 canciones por vistas para que la IA analice el rendimiento individual
            t = df.nlargest(10, 'views')[['track_name', 'artist_names', 'views', 'likes', 'engagement']].copy()
            t['views'] = t['views'].apply(fmt_num)
            t['likes'] = t['likes'].apply(fmt_num)
            t['engagement'] = t['engagement'].round(1).astype(str) + '%'
            return t.to_markdown(index=False)
            
        elif section == "video_metrics":
            # Agregamos vistas promedio, engagement y datos de duración
            t = df.groupby('channel_type').agg(songs=('track_name', 'count'), avg_views=('views', 'mean'), avg_engagement=('engagement', 'mean')).reset_index().sort_values('songs', ascending=False)
            t['avg_views'] = t['avg_views'].apply(fmt_num)
            t['avg_engagement'] = t['avg_engagement'].round(1).astype(str) + '%'
            
            dur_stats = pd.DataFrame({
                "Metric": ["Avg Duration (min)", "Median Duration (min)", "Max Duration (min)"],
                "Value": [f"{df['duration_s'].mean()/60:.1f}", f"{df['duration_s'].median()/60:.1f}", f"{df['duration_s'].max()/60:.1f}"]
            })
            return f"Channel Types:\n{t.to_markdown(index=False)}\n\nDuration Stats:\n{dur_stats.to_markdown(index=False)}"
            
        elif section == "temporal_analysis":
            t = df.groupby('upload_quarter').agg(songs=('track_name', 'count'), views=('views', 'sum')).reset_index()
            t['views'] = t['views'].apply(fmt_num)
            return t.to_markdown(index=False)
            
        elif section == "collaborations":
            t = df.groupby('is_collaboration').agg(songs=('track_name', 'count'), views=('views', 'sum'), engagement=('engagement', 'mean')).reset_index()
            t['is_collaboration'] = t['is_collaboration'].map({0: 'Solo', 1: 'Collaboration'})
            t['views'] = t['views'].apply(fmt_num)
            t['engagement'] = t['engagement'].round(2).astype(str) + '%'
            return t.to_markdown(index=False)
            
    except Exception as e:
        logger.error(f"      [AI] Error building table for {section}: {e}")
    
    return ""


# ============================================================================
# MAIN
# ============================================================================
def main(argv: list[str] | None = None) -> int:
    logger.info("\n" + "=" * 70)
    logger.info("📊 WEEKLY MUSIC CHARTS REPORT GENERATOR (v2.0 — AI Enabled)")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    args = _parse_args(argv)
    use_ai = not args.no_ai

    if use_ai and not (GROQ_API_KEY or GOOGLE_API_KEY or DEEPSEEK_API_KEY):
        logger.warning("   ⚠️  No AI API keys found. AI insights will be disabled.")
        use_ai = False

    # 1. Resolve Period
    try:
        label = _resolve_week_label(args)
        period = week_from_label(label)
        logger.info(f"\n1. 📅 RESOLVING WEEK...\n   ✅ Week: {period.label}")
    except Exception as e:
        logger.error(f"   ❌ {e}")
        return 1

    # 2. Load Data
    logger.info(f"\n2. 📖 LOADING ENRICHED DATA...")
    try:
        df = load_week(period.label, ARCHIVE_DIR)
        logger.info(f"   ✅ {len(df)} songs loaded, {df.shape[1]} columns")
    except Exception as e:
        logger.error(f"   ❌ {e}")
        return 1

    # 3. Generate Notebooks
    languages = LANGUAGES if args.language == "both" else (args.language,)
    logger.info(f"\n3. 📝 GENERATING NOTEBOOKS ({', '.join(languages)})...")

    for lang in languages:
        # 3a. AI Insights
        insights = _generate_ai_insights(df, period.label, lang, use_ai)
        
        # 3b. Notebook
        out_path = notebook_dir(lang) / f"youtube_charts_{period.label}.ipynb"
        try:
            generate_notebook(df, period, out_path, lang, insights=insights)
            logger.info(f"   ✅ {lang.upper()}: {out_path}")
        except Exception as e:
            logger.error(f"   ❌ {lang.upper()}: {e}")
            return 1

    # 4. Summary
    logger.info("\n4. 📊 FINAL SUMMARY:")
    logger.info(f"   📅 Week:      {period.label}")
    logger.info(f"   🎵 Songs:     {len(df)}")
    logger.info(f"   🌍 Countries: {df['artist_country'].nunique()}")
    logger.info(f"   🎼 Genres:    {df['macro_genre'].nunique()}")
    logger.info(f"   🤖 AI Insights: {'Enabled' if use_ai else 'Disabled'}")
    logger.info("=" * 70 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
