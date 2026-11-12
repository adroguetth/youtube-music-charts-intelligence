"""
Cache - AI Response Persistence
============================================================================
Saves and loads AI responses (summaries and final texts) to avoid redundant
API calls. This is crucial for saving tokens and reducing latency.

Responsibilities
----------------
- Check if a cached response exists for a specific period, section, and language.
- Save a new response to the cache.
- Use a file-based JSON cache (one file per section/week/language).

Notes
-----
- The cache lives in the `cache_ai/` folder at the root of the repository.
- The cache key is built from: `{period_label}_{section_id}_{language}.json`.
- The cache does NOT expire automatically. If you want to force a refresh
  (e.g., after changing the prompt), simply delete the `cache_ai/` folder.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path

# ============================================================================
# CONSTANTS
# ============================================================================
# Navigate up 3 levels: cache.py -> ai -> core -> 4_report_generator -> repo_root
_REPO_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = _REPO_ROOT / "cache_ai"


class AICache:
    def __init__(self):
        # Ensure the cache directory exists
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _get_path(self, period_label: str, section_id: str, language: str) -> Path:
        """Build the file path for a given cache key."""
        filename = f"{period_label}_{section_id}_{language}.json"
        return CACHE_DIR / filename

    def get(self, period_label: str, section_id: str, language: str) -> dict | None:
        """
        Retrieve a cached response.
        
        Returns
        -------
        dict or None
            A dictionary with "summary", "final_text", and "model_used" keys,
            or None if no cache exists.
        """
        path = self._get_path(period_label, section_id, language)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"   [Cache] Warning: Failed to read {path.name}: {e}")
            return None

    def save(self, period_label: str, section_id: str, language: str, data: dict):
        """
        Save a response to the cache.
        
        Parameters
        ----------
        period_label : str
            e.g., "2026-W46"
        section_id : str
            e.g., "general_stats"
        language : str
            "en" or "es"
        data : dict
            Contains "summary", "final_text", and "model_used".
        """
        path = self._get_path(period_label, section_id, language)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"   [Cache] Warning: Failed to write {path.name}: {e}")
