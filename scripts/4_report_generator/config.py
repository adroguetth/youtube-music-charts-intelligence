
"""
Config - Paths, API Keys and Color Palette
============================================================================
Centralized configuration module for the report generator (Script 4).

This module defines all filesystem paths, AI API credentials, output
directories, and the shared visual design system (color palette) used
across the Quarto templates and Matplotlib charts.

Features
--------
- Repository-relative paths for consistent behavior in CI/CD.
- Output directory auto-creation for reports and caches.
- Centralized AI configuration (DeepSeek).
- YouTube-inspired color palette for unified visual identity.

Dependencies
------------
- External: os, pathlib (stdlib).

Requirements
------------
- Python 3.7+

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import os
from pathlib import Path

# ============================================================================
# DIRECTORY STRUCTURE CONFIGURATION
# ============================================================================
# Determine repository root (two levels up from this file)
REPO_ROOT: Path = Path(__file__).parent.parent.parent

# Input: Where the enriched databases are stored (Script 3 output)
INPUT_DB_DIR: Path = REPO_ROOT / "charts_archive" / "3_enrich-chart-data"

# Output: Where the final HTML and PDF reports will be saved
OUTPUT_DIR: Path = REPO_ROOT / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Cache: Where AI-generated texts are stored to save API tokens
CACHE_DIR: Path = OUTPUT_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Templates: Where the Quarto .qmd files and CSS live
TEMPLATES_DIR: Path = REPO_ROOT / "scripts" / "4_report_generator" / "templates"


# ============================================================================
# AI CONFIGURATION (DeepSeek)
# ============================================================================
# API Key loaded from environment variables (GitHub Secrets)
DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL: str = "https://api.deepseek.com/v1/chat/completions"

# Model settings
DEEPSEEK_MODEL: str = "deepseek-chat"
DEEPSEEK_TEMPERATURE: float = 0.7


# ============================================================================
# VISUAL DESIGN SYSTEM (YouTube Palette)
# ============================================================================
# These colors are shared between Matplotlib (charts.py) and Quarto (styles.css)
YT_RED: str = "#FF0000"
YT_RED_DARK: str = "#CC0000"
YT_BG: str = "#FFFFFF"
YT_SURFACE: str = "#F9F9F9"
YT_TEXT: str = "#0F0F0F"
YT_GRAY: str = "#606060"
YT_GRID: str = "#E5E5E5"

# Semantic colors for charts
COLOR_PRIMARY: str = YT_RED
COLOR_SECONDARY: str = YT_GRAY
COLOR_SUCCESS: str = "#2BA640"  # Green for positive trends
COLOR_DANGER: str = "#E50914"   # Red for negative trends
COLOR_NEUTRAL: str = "#AAAAAA"  # Light gray for backgrounds or "Other"


# ============================================================================
# PUBLIC API
# ============================================================================
__all__ = [
    "REPO_ROOT",
    "INPUT_DB_DIR",
    "OUTPUT_DIR",
    "CACHE_DIR",
    "TEMPLATES_DIR",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_API_URL",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_TEMPERATURE",
    "YT_RED",
    "YT_RED_DARK",
    "YT_BG",
    "YT_SURFACE",
    "YT_TEXT",
    "YT_GRAY",
    "YT_GRID",
    "COLOR_PRIMARY",
    "COLOR_SECONDARY",
    "COLOR_SUCCESS",
    "COLOR_DANGER",
    "COLOR_NEUTRAL",
]
