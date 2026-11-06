"""
Groq API Client - Fallback Country and Genre Detection
============================================================================
Fallback detection module for musical artist metadata. Uses the official
Groq SDK to query the Llama 3.3 70B Versatile model when other sources
(including DeepSeek) return no results. Provides country of origin and
primary musical genre for a given artist name.

This module acts as a last-resort fallback in the metadata detection
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
- Rate limiting is applied via a 0.3s sleep between calls (Groq is fast,
  but the delay keeps usage polite).
- The prompt is intentionally identical to the DeepSeek fallback prompt
  for consistency across fallback sources.
- Failures are cached as `(None, None, "Groq failed")` to avoid retrying
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
_GROQ_CLIENT = None
_GROQ_CACHE = {}  # Cache: {artist: (country, genre, source)}


# ============================================================================
# CLIENT INITIALIZATION
# ============================================================================
def _get_groq_client() -> Optional[Groq]:
    """
    Lazily initialize and return the Groq client.

    The client is created only on first use and cached at module level.
    Returns None if the API key is missing or client creation fails.

    Returns
    -------
    Groq or None
        Configured Groq client, or None if the API key is missing or
        initialization fails.

    Notes
    -----
    Reads the API key from the `GROQ_API_KEY` environment variable. All
    initialization errors are logged at debug level and swallowed so the
    caller can gracefully fall back.
    """
    global _GROQ_CLIENT

    if _GROQ_CLIENT is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.debug("Groq API key not set")
            return None
        try:
            _GROQ_CLIENT = Groq(api_key=api_key)
        except Exception as e:
            logger.debug(f"Failed to initialize Groq client: {e}")
            return None

    return _GROQ_CLIENT


# ============================================================================
# PROMPT BUILDING
# ============================================================================
def _build_prompt(artist: str, context_country: Optional[str] = None) -> str:
    """
    Build the prompt sent to the Groq model.

    Parameters
    ----------
    artist : str
        Artist name to query.
    context_country : str, optional
        Known country used as context to assist the model.

    Returns
    -------
    str
        Formatted prompt requesting a JSON object with `country` and
        `genre` fields.

    Notes
    -----
    The prompt is intentionally identical to the DeepSeek fallback prompt
    for consistency across fallback sources.
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
def search_groq_fallback(
    artist: str,
    context_country: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Use the Groq API as a fallback to detect country and/or genre.

    Only called when other sources (including DeepSeek) return nothing.
    Results are cached per artist to avoid redundant API calls.

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
        - `source_info` describes the outcome (e.g., "Groq (Llama 3.3)",
          "Groq not available", "Groq failed").

    Notes
    -----
    - Applies a 0.3s delay before each API call as polite rate limiting.
    - Extracts the first JSON object found in the model response via
      regex, so stray text does not break parsing.
    - Country is validated and normalized via
      `validate_and_normalize_country`; genre via `normalize_genre`
      (imported locally to avoid a circular dependency with
      `genre_detector`).
    - Failed results are cached as `(None, None, "Groq failed")` to avoid
      retrying the same artist repeatedly.
    """
    if artist in _GROQ_CACHE:
        return _GROQ_CACHE[artist]

    client = _get_groq_client()
    if not client:
        return None, None, "Groq not available"

    # Rate limiting (Groq is fast, but let's be polite)
    time.sleep(0.3)

    prompt = _build_prompt(artist, context_country)

    try:
        # --- Call the model via the official Groq SDK ---
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )

        content = response.choices[0].message.content.strip()
        
        # Log the raw response so we can debug in GitHub Actions
        logger.info(f"  🤖 Groq raw response for {artist}: {content[:100]}...")

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

            result = (country, genre, "Groq (Llama 3.3)")
            _GROQ_CACHE[artist] = result
            return result

    except json.JSONDecodeError as e:
        logger.error(f"  ❌ Groq JSON parse error for {artist}: {e}")
    except Exception as e:
        # Changed to logger.error so the exact Groq API error shows up in the workflow log
        logger.error(f"  ❌ Groq API error for {artist}: {e}")

    result = (None, None, "Groq failed")
    _GROQ_CACHE[artist] = result
    return result
