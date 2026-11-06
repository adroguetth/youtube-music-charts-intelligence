"""
DeepSeek API Client - Fallback Country and Genre Detection
============================================================================
Fallback detection module for musical artist metadata. Uses the OpenAI-compatible
interface to query DeepSeek's chat model when other sources return no results. 
Provides country of origin and primary musical genre for a given artist name.

This module acts as a fallback in the metadata detection pipeline. It includes 
lazy client initialization, in-memory caching, rate limiting, and robust JSON 
extraction with validation/normalization of returned values.

Features
--------
- Lazy initialization of the DeepSeek client (only when first needed).
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
- External: openai, os, json, re, time, typing (stdlib).

Requirements
------------
- Python 3.7+
- `openai` SDK installed.
- Environment variable `DEEPSEEK_API_KEY` set with a valid API key.

Notes
-----
- The module-level client and cache are singletons shared across calls
  within the same process.
- Rate limiting is applied via a 0.5s sleep between calls.
- Failures are cached as `(None, None, "DeepSeek failed")` to avoid retrying
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
from openai import OpenAI

from ..config import logger
from ..utils.country_utils import validate_and_normalize_country

# ============================================================================
# CONSTANTS AND GLOBAL STATE
# ============================================================================
_DEEPSEEK_CLIENT = None
_DEEPSEEK_CACHE = {}  # Cache: {artist: (country, genre, source)}


# ============================================================================
# CLIENT INITIALIZATION
# ============================================================================
def _get_deepseek_client() -> Optional[OpenAI]:
    """
    Lazily initialize and return the DeepSeek client.

    The client is created only on first use and cached at module level.
    Returns None if the API key is missing or client creation fails.

    Returns
    -------
    OpenAI or None
        Configured OpenAI client (pointed to DeepSeek), or None if the API 
        key is missing or initialization fails.
    """
    global _DEEPSEEK_CLIENT

    if _DEEPSEEK_CLIENT is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            logger.debug("DeepSeek API key not set")
            return None
        try:
            _DEEPSEEK_CLIENT = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
        except Exception as e:
            logger.debug(f"Failed to initialize DeepSeek client: {e}")
            return None

    return _DEEPSEEK_CLIENT


# ============================================================================
# FALLBACK DETECTION
# ============================================================================
def search_deepseek_fallback(
    artist: str,
    context_country: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Use the DeepSeek API as fallback to get country and/or genre.

    Only called when other sources return nothing. Results are cached per 
    artist to avoid redundant API calls.

    Parameters
    ----------
    artist : str
        Artist name to search for.
    context_country : str, optional
        Known country used as context to assist the model.

    Returns
    -------
    tuple of (str or None, str or None, str)
        A tuple `(country, genre, source_info)` where:
        - `country` is the normalized country name, or None.
        - `genre` is the normalized macro-genre, or None.
        - `source_info` describes the outcome (e.g., "DeepSeek API",
          "DeepSeek not available", "DeepSeek failed").
    """
    if artist in _DEEPSEEK_CACHE:
        return _DEEPSEEK_CACHE[artist]

    client = _get_deepseek_client()
    if not client:
        return None, None, "DeepSeek not available"

    # Rate limiting
    time.sleep(0.5)

    # Build prompt
    if context_country:
        prompt = f"""
You are a music knowledge expert. Provide accurate information about the musical artist "{artist}".

The artist is known to be from {context_country} (but please verify if correct). Return ONLY a valid JSON object with these fields (use null if unknown):
{{
    "country": "country of origin (full name, e.g., United States, South Korea, United Kingdom) - if the provided country is incorrect, provide the correct one, otherwise leave as provided",
    "genre": "primary musical genre (e.g., Pop, K-Pop, Reggaeton, Afrobeats, Rock, Hip-Hop/Rap)"
}}

Be precise and factual. If you're unsure about any field, set it to null.
Do not include any additional text outside the JSON object.
"""
    else:
        prompt = f"""
You are a music knowledge expert. Provide accurate information about the musical artist "{artist}".

Return ONLY a valid JSON object with these fields (use null if unknown):
{{
    "country": "country of origin (full name, e.g., United States, South Korea, United Kingdom)",
    "genre": "primary musical genre (e.g., Pop, K-Pop, Reggaeton, Afrobeats, Rock, Hip-Hop/Rap)"
}}

Be precise and factual. If you're unsure about any field, set it to null.
Do not include any additional text outside the JSON object.
"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200
        )
        content = response.choices[0].message.content.strip()

        # --- Log the raw response cleanly (single line) ---
        clean_content = content.replace('\n', ' ').replace('\r', '')
        logger.info(f"  🤖 DeepSeek raw response for {artist}: {clean_content}")

        # Extract JSON from response
        json_match = re.search(r'\{[^{}]*\}', content)
        if json_match:
            data = json.loads(json_match.group())
            country_raw = data.get('country')
            genre_raw = data.get('genre')

            country = None
            if country_raw:
                country = validate_and_normalize_country(country_raw)

            genre = None
            if genre_raw:
                # Local import to avoid circular dependency with genre_detector
                from ..genre_detector import normalize_genre
                macro, _ = normalize_genre(genre_raw)
                genre = macro if macro else genre_raw

            result = (country, genre, "DeepSeek API")
            _DEEPSEEK_CACHE[artist] = result
            return result

    except json.JSONDecodeError as e:
        logger.error(f"  ❌ DeepSeek JSON parse error for {artist}: {e}")
    except Exception as e:
        logger.error(f"  ❌ DeepSeek API error for {artist}: {e}")

    result = (None, None, "DeepSeek failed")
    _DEEPSEEK_CACHE[artist] = result
    return result
