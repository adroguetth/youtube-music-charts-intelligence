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

import numpy as np
import pandas as pd

from config import (
    ARCHIVE_DIR,
    DEEPSEEK_API_KEY,
    GOOGLE_API_KEY,
    GROQ_API_KEY,
    META_API_KEY,
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
    Generates the AI insights for the introduction, each subsection,
    and the conclusion. Returns a dictionary mapping section_id -> markdown_text.
    """
    if not use_ai:
        return {}

    logger.info(f"   🧠 Generating AI insights ({language.upper()})...")
    
    # Initialize components
    cache = AICache()
    budget = BudgetManager()
    summarizer = TableSummarizer(
        groq_api_key=GROQ_API_KEY,
        google_api_key=GOOGLE_API_KEY,
        meta_api_key=META_API_KEY,
    )
    writer = DeepSeekWriter(api_key=DEEPSEEK_API_KEY)

    insights = {}

    # ========================================================================
    # 1. GENERATE SUBSECTION INSIGHTS (the loop)
    # ========================================================================
    ai_sections = [
        "general_stats", "continents", "countries_by_songs", "countries_by_likes",
        "countries_top_songs", "genre_stats", "genre_treemap", "genre_engagement",
        "top_songs_by_views", "top_songs_by_likes", "top_songs_by_engagement",
        "video_summary", "video_views", "video_engagement", "video_duration", "video_channels",
        "temporal_views", "temporal_engagement", "temporal_releases",
        "collab_views", "collab_engagement",
    ]

    for section in ai_sections:
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
            # Record failure so the circuit breaker can activate
            budget.record_usage(model_used, 0, success=False)
            continue

        # 4. Polish with DeepSeek (pass 'section' as the first argument)
        final_text, tokens_writer = writer.polish(section, raw_summary, language)
        
        # 5. Record usage and save to cache
        budget.record_usage(model_used, tokens_summary, success=True)
        cache.save(period_label, section, language, {
            "summary": raw_summary,
            "final_text": final_text,
            "model_used": model_used
        })
        
        insights[section] = final_text
        logger.info(f"      ✅ {section} (via {model_used})")

    # ========================================================================
    # 2. GENERATE CONCLUSION (with FULL text of all sections)
    # ========================================================================
    logger.info(f"      [Conclusion] Generating conclusion...")
    
    # Build context with the FULL text of all sections, not just 200 chars
    conclusion_context_parts = []
    for section_id, text in insights.items():
        if section_id not in ["introduction", "conclusion"]:
            conclusion_context_parts.append(f"### {section_id}\n{text}")
    
    conclusion_context = "\n\n".join(conclusion_context_parts)
    
    conclusion_text, _ = writer.polish("conclusion", conclusion_context, language)
    if conclusion_text:
        insights["conclusion"] = conclusion_text
        logger.info(f"      ✅ conclusion (via DeepSeek)")

    # ========================================================================
    # 3. GENERATE INTRODUCTION (with FULL text of all sections + conclusion)
    # ========================================================================
    logger.info(f"      [Intro] Generating introduction...")
    
    intro_context_parts = []
    for section_id, text in insights.items():
        if section_id not in ["introduction", "conclusion"]:
            intro_context_parts.append(f"### {section_id}\n{text}")
    
    intro_context = "\n\n".join(intro_context_parts)
    
    # Add the conclusion to the context for the introduction
    if insights.get("conclusion"):
        intro_context += f"\n\n### conclusion\n{insights['conclusion']}"
    
    intro_text, _ = writer.polish("introduction", intro_context, language)
    if intro_text:
        insights["introduction"] = intro_text
        logger.info(f"      ✅ introduction (via DeepSeek)")

    return insights


def _get_table_markdown_for_section(df: pd.DataFrame, section: str) -> str:
    """
    Calculates the specific table for a subsection and returns it as Markdown.
    Keeps tables small (head 5-10) to save tokens.
    """
    try:
        # Ensure 'continent' column exists (needed for 'continents')
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

        # ====================================================================
        # SECTION 2: General Statistics
        # ====================================================================
        if section == "general_stats":
            total_views = df['views'].sum()
            total_likes = df['likes'].sum()
            eng_rate = (total_likes / total_views * 100) if total_views > 0 else 0
            stats = pd.DataFrame({
                "Metric": ["Total Songs", "Unique Countries", "Unique Genres", "Total Views", "Total Likes", "Engagement Rate (%)"],
                "Value": [len(df), df['artist_country'].nunique(), df['macro_genre'].nunique(), fmt_num(total_views), fmt_num(total_likes), f"{eng_rate:.1f}%"]
            })
            return stats.to_markdown(index=False)

        # ====================================================================
        # SECTION 3: Continents
        # ====================================================================
        elif section == "continents":
            t = df.groupby('continent').agg(songs=('track_name', 'count'), views=('views', 'sum')).reset_index().sort_values('songs', ascending=False)
            t['views'] = t['views'].apply(fmt_num)
            return t.to_markdown(index=False)

        # ====================================================================
        # SECTION 4: Countries
        # ====================================================================
        elif section == "countries_by_songs":
            t = df.groupby('artist_country').agg(songs=('track_name', 'count')).reset_index().sort_values('songs', ascending=False).head(10)
            return t.to_markdown(index=False)

        elif section == "countries_by_likes":
            t = df.groupby('artist_country').agg(likes=('likes', 'sum')).reset_index().sort_values('likes', ascending=False).head(10)
            t['likes'] = t['likes'].apply(fmt_num)
            return t.to_markdown(index=False)

        elif section == "countries_top_songs":
            # For this section, we just send a small sample of top songs per country
            top_countries = df['artist_country'].value_counts().head(5).index.tolist()
            rows = []
            for country in top_countries:
                df_country = df[df['artist_country'] == country]
                top_song = df_country.nlargest(1, 'views')[['track_name', 'artist_names', 'views']].iloc[0]
                rows.append({
                    "Country": country,
                    "Top Song": top_song['track_name'],
                    "Artist": top_song['artist_names'],
                    "Views": fmt_num(top_song['views'])
                })
            return pd.DataFrame(rows).to_markdown(index=False)

        # ====================================================================
        # SECTION 5: Genre Analysis
        # ====================================================================
        elif section == "genre_stats":
            t = df.groupby('macro_genre').agg(songs=('track_name', 'count'), views=('views', 'sum'), engagement=('engagement', 'mean')).reset_index().sort_values('songs', ascending=False).head(10)
            t['views'] = t['views'].apply(fmt_num)
            t['engagement'] = t['engagement'].round(1).astype(str) + '%'
            return t.to_markdown(index=False)

        elif section == "genre_treemap":
            t = df.groupby('macro_genre').agg(songs=('track_name', 'count')).reset_index().sort_values('songs', ascending=False).head(15)
            return t.to_markdown(index=False)

        elif section == "genre_engagement":
            t = df.groupby('macro_genre').agg(engagement=('engagement', 'mean')).reset_index().sort_values('engagement', ascending=False).head(10)
            t['engagement'] = t['engagement'].round(1).astype(str) + '%'
            return t.to_markdown(index=False)

        # ====================================================================
        # SECTION 6: Song Metrics
        # ====================================================================
        elif section == "top_songs_by_views":
            t = df.nlargest(10, 'views')[['track_name', 'artist_names', 'views', 'engagement']].copy()
            t['views'] = t['views'].apply(fmt_num)
            t['engagement'] = t['engagement'].round(1).astype(str) + '%'
            return t.to_markdown(index=False)

        elif section == "top_songs_by_likes":
            t = df.nlargest(10, 'likes')[['track_name', 'artist_names', 'likes', 'engagement']].copy()
            t['likes'] = t['likes'].apply(fmt_num)
            t['engagement'] = t['engagement'].round(1).astype(str) + '%'
            return t.to_markdown(index=False)

        elif section == "top_songs_by_engagement":
            t = df.nlargest(10, 'engagement')[['track_name', 'artist_names', 'views', 'engagement']].copy()
            t['views'] = t['views'].apply(fmt_num)
            t['engagement'] = t['engagement'].round(1).astype(str) + '%'
            return t.to_markdown(index=False)

        # ====================================================================
        # SECTION 7: Video Metrics
        # ====================================================================
        elif section == "video_summary":
            video_stats = {
                'Category': ['Official Videos', 'Lyric Videos', 'Live Performances', 'Collaborations'],
                'Count': [df['is_official_video'].sum(), df['is_lyric_video'].sum(), df['is_live_performance'].sum(), df['is_collaboration'].sum()]
            }
            v_stats_df = pd.DataFrame(video_stats)
            v_stats_df['Percentage'] = (v_stats_df['Count'] / len(df) * 100).round(1).astype(str) + '%'
            return v_stats_df.to_markdown(index=False)

        elif section == "video_views":
            df_video = df.copy()
            conditions = [df_video['is_official_video'] == 1, df_video['is_lyric_video'] == 1, df_video['is_live_performance'] == 1]
            choices = ['Official', 'Lyric', 'Live']
            df_video['video_type'] = pd.Series(np.select(conditions, choices, default='Other'), index=df_video.index)
            views_stats = df_video.groupby('video_type').agg(total_videos=('views', 'count'), avg_views=('views', 'mean')).reset_index()
            views_stats['avg_views'] = views_stats['avg_views'].apply(fmt_num)
            return views_stats.to_markdown(index=False)

        elif section == "video_engagement":
            df_video = df.copy()
            conditions = [df_video['is_official_video'] == 1, df_video['is_lyric_video'] == 1, df_video['is_live_performance'] == 1]
            choices = ['Official', 'Lyric', 'Live']
            df_video['video_type'] = pd.Series(np.select(conditions, choices, default='Other'), index=df_video.index)
            eng_stats = df_video.groupby('video_type').agg(avg_engagement=('engagement', 'mean')).reset_index()
            eng_stats['avg_engagement'] = eng_stats['avg_engagement'].round(1).astype(str) + '%'
            return eng_stats.to_markdown(index=False)

        elif section == "video_duration":
            dur_stats = pd.DataFrame({
                "Metric": ["Avg Duration (min)", "Median Duration (min)", "Max Duration (min)"],
                "Value": [f"{df['duration_s'].mean()/60:.1f}", f"{df['duration_s'].median()/60:.1f}", f"{df['duration_s'].max()/60:.1f}"]
            })
            return dur_stats.to_markdown(index=False)

        elif section == "video_channels":
            channel_counts = df['channel_type'].value_counts()
            ch_df = pd.DataFrame({'Channel Type': channel_counts.index, 'Count': channel_counts.values})
            ch_df['Percentage'] = (ch_df['Count'] / len(df) * 100).round(1).astype(str) + '%'
            return ch_df.to_markdown(index=False)

        # ====================================================================
        # SECTION 8: Temporal Analysis
        # ====================================================================
        elif section == "temporal_views":
            t = df.groupby('upload_quarter').agg(songs=('track_name', 'count'), views=('views', 'sum')).reset_index()
            t['views'] = t['views'].apply(fmt_num)
            return t.to_markdown(index=False)

        elif section == "temporal_engagement":
            t = df.groupby('upload_quarter').agg(engagement=('engagement', 'mean')).reset_index()
            t['engagement'] = t['engagement'].round(1).astype(str) + '%'
            return t.to_markdown(index=False)

        elif section == "temporal_releases":
            t = df['upload_quarter'].value_counts().sort_index().reset_index()
            t.columns = ['Quarter', 'Count']
            return t.to_markdown(index=False)

        # ====================================================================
        # SECTION 9: Collaborations
        # ====================================================================
        elif section == "collab_views":
            t = df.groupby('is_collaboration').agg(songs=('track_name', 'count'), avg_views=('views', 'mean')).reset_index()
            t['is_collaboration'] = t['is_collaboration'].map({0: 'Solo', 1: 'Collaboration'})
            t['avg_views'] = t['avg_views'].apply(fmt_num)
            return t.to_markdown(index=False)

        elif section == "collab_engagement":
            t = df.groupby('is_collaboration').agg(avg_engagement=('engagement', 'mean')).reset_index()
            t['is_collaboration'] = t['is_collaboration'].map({0: 'Solo', 1: 'Collaboration'})
            t['avg_engagement'] = t['avg_engagement'].round(1).astype(str) + '%'
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

    if use_ai and not (GROQ_API_KEY or GOOGLE_API_KEY or DEEPSEEK_API_KEY or META_API_KEY):
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
