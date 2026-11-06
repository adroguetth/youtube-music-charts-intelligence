"""
Qwen API Client (via Groq) - Fallback Country and Genre Detection
============================================================================
Fallback detection module for musical artist metadata. Uses the official
Groq SDK to query the Qwen 27B model when other sources (including GPT-OSS)
return no results. Provides country of origin and primary musical genre 
for a given artist name.

This module acts as a secondary AI fallback in the metadata detection
pipeline. It includes lazy client initialization, in-memory caching, rate
limiting, and robust JSON extraction with validation/normalization of
returned values.

Features
--------
- Lazy initialization of the Groq client (only when first needed).
- In-memory cache keyed by artist name to avoid redundant API calls.
- Automatic country validation and normalization.
- Automatic genre normalization via the local genre detector.
- Robust JSON extraction from model responses.
- Graceful degradation when API key is missing or calls fail.

Dependencies
------------
- Internal: `..config` (logger), `..utils.country_utils`
  (validate_and_normalize_country), `..genre_detector` (normalize_genre,
  imported locally to avoid circular dependency).
- External: groq, os, json, re, time, typing (stdlib).

Requirements
------------
- Python 3.7+
- `groq` SDK installed.
- Environment variable `GROQ_API_KEY` set with a valid API key.

Notes
-----
- The module-level client and cache are singletons shared across calls
  within the same process.
- Rate limiting is applied via a 0.3s sleep between calls.
- The prompt is intentionally identical to the other AI fallbacks for
  consistency across fallback sources.
- Failures are cached as `(None, None, "Qwen failed")` to avoid retrying
  the same artist repeatedly.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

import json
import os
import re
import time
from typing import Optional, Tuple

from groq import Groq

from ..config import logger
from ..utils.country_utils import validate_and_normalize_country

# ============================================================================
# CONSTANTS AND GLOBAL STATE
# ============================================================================
_QWEN_CLIENT = None
_QWEN_CACHE = {}  # Cache: {artist: (country, genre, source)}


# ============================================================================
# CLIENT INITIALIZATION
# ============================================================================
def _get_qwen_client() -> Optional[Groq]:
    """
    Lazily initialize and return the Groq client for Qwen.

    The client is created only on first use and cached at module level.
    Returns None if the API key is missing or client creation fails.
    """
    global _QWEN_CLIENT

    if _QWEN_CLIENT is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.debug("Groq API key not set (required for Qwen)")
            return None
        try:
            _QWEN_CLIENT = Groq(api_key=api_key)
        except Exception as e:
            logger.debug(f"Failed to initialize Groq client for Qwen: {e}")
            return None

    return _QWEN_CLIENT


# ============================================================================
# PROMPT BUILDING
# ============================================================================
def _build_prompt(artist: str, context_country: Optional[str] = None) -> str:
    """
    Build the prompt sent to the Qwen model.
    """
    if context_country:
        return f"""
You are a music knowledge expert. Provide accurate information about the musical artist "{artist}".

The artist is known to be from {context_country} (but please verify if correct). Return ONLY a valid JSON object with these fields (use null if unknown):
{{
    "country": "country of origin (full name, e.g., United States, South Korea, United Kingdom) - if the provided country is incorrect, provide the correct one, otherwise leave as provided",
    "genre": "primary musical genre (e.g., Pop, K-Pop, Reggaeton, Afrobeats, Rock, Hip-Hop/Rap)"
}}

Be precise and factual. If you're unsure about any field, set it to null.
Do not include any additional text outside the JSON object.
"""

    return f"""
You are a music knowledge expert. Provide accurate information about the musical artist "{artist}".

Return ONLY a valid JSON object with these fields (use null if unknown):
{{
    "country": "country of origin (full name, e.g., United States, South Korea, United Kingdom)",
    "genre": "primary musical genre (e.g., Pop, K-Pop, Reggaeton, Afrobeats, Rock, Hip-Hop/Rap)"
}}

Be precise and factual. If you're unsure about any field, set it to null.
Do not include any additional text outside the JSON object.
"""


# ============================================================================
# FALLBACK DETECTION
# ============================================================================
def search_qwen_fallback(
    artist: str,
    context_country: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Use the Qwen API (via Groq) as a fallback to detect country and/or genre.

    Only called when other sources (including GPT-OSS) return nothing.
    Results are cached per artist to avoid redundant API calls.
    """
    if artist in _QWEN_CACHE:
        return _QWEN_CACHE[artist]

    client = _get_qwen_client()
    if not client:
        return None, None, "Qwen not available"

    # Rate limiting
    time.sleep(0.3)

    prompt = _build_prompt(artist, context_country)

    try:
        # --- Call the model via the official Groq SDK ---
        # Using Qwen 27B, specialized in Asian and niche artists
        response = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )

        content = response.choices[0].message.content.strip()
        
        # Log the raw response so we can debug in GitHub Actions
        clean_content = content.replace('\n', ' ').replace('\r', '')
        logger.info(f"  🤖 Qwen raw response for {artist}: {clean_content}")

        # --- Extract and parse JSON from the response ---
        json_match = re.search(r"\{[^{}]*\}", content)
        if json_match:
            data = json.loads(json_match.group())
            country_raw = data.get("country")
            genre_raw = data.get("genre")

            country = None
            if country_raw:
                country = validate_and_normalize_country(country_raw)

            genre = None
            if genre_raw:
                # Local import to avoid circular dependency with genre_detector
                from ..genre_detector import normalize_genre

                macro, _ = normalize_genre(genre_raw)
                genre = macro if macro else genre_raw

            result = (country, genre, "Qwen (27B)")
            _QWEN_CACHE[artist] = result
            return result

    except json.JSONDecodeError as e:
        logger.error(f"  ❌ Qwen JSON parse error for {artist}: {e}")
    except Exception as e:
        logger.error(f"  ❌ Qwen API error for {artist}: {e}")

    result = (None, None, "Qwen failed")
    _QWEN_CACHE[artist] = result
    return result
