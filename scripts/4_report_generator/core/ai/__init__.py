"""
Core AI - Intelligent Analysis Layer
============================================================================
This subpackage contains the AI components of the report generator.

Responsibilities
----------------
- Budget Management: Decide which AI model to use based on token limits
  and historical success/failure rates (`budget_manager`).
- Table Summarization: Extract key insights from Markdown tables using
  free-tier models like Groq or Google Gemma (`summarizer`).
- Text Writing: Polish the summary into a professional analysis using
  DeepSeek (`writer`).
- Caching: Save and load AI responses to avoid redundant API calls (`cache`).

Notes
-----
- This package is entirely optional. If no API keys are configured, or if
  the AI services fail, the report generator will simply skip the AI
  insights and produce the standard visual report (v1.1 behavior).
- The `budget_manager` relies on the global `ai_budget.json` file at the
  root of the repository to persist token usage across workflow runs.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

# Re-export the main classes for easier imports in main.py
from .budget_manager import BudgetManager
from .summarizer import TableSummarizer
from .writer import DeepSeekWriter

__all__ = [
    "BudgetManager",
    "TableSummarizer",
    "DeepSeekWriter",
]
