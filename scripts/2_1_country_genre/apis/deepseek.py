"""
DeepSeek API Client - Primary Fallback Country and Genre Detection
============================================================================
Primary AI fallback detection module for musical artist metadata. Uses the
OpenAI-compatible interface to query DeepSeek's `deepseek-chat` model when
structured sources (MusicBrainz, Wikidata, Wikipedia) return no results.
Provides country of origin and primary musical genre for a given artist
name.

This module is the first AI fallback in the metadata detection pipeline,
invoked before the Groq and Muse Spark clients. It includes lazy client
initialization, in-memory caching, rate limiting, and robust JSON
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
- `openai` SDK installed (used as the OpenAI-compatible client).
- Environment variable `DEEPSEEK_API_KEY` set with a valid API key.

Notes
-----
- The module-level client and cache are singletons shared across calls
  within the same process.
- Rate limiting is applied via a 0.5s sleep between calls.
- The prompt is the canonical one used across all AI fallbacks
  (DeepSeek, Groq, Muse) for consistency of behavior and output schema.
- Failures are cached as `(None, None, "DeepSeek failed")` to avoid
  retrying the same artist repeatedly.
- The OpenAI SDK is reused because DeepSeek exposes an OpenAI-compatible
  API surface; only `base_url` differs.

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
_MODEL_NAME = "deepseek-chat"
_BASE_URL = "https://api.deepseek.com"
_REQUEST_TEMPERATURE = 0.1
_REQUEST_MAX_TOKENS = 200
_RATE_LIMIT_SECONDS = 0.5

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
        OpenAI-compatible client configured for DeepSeek, or None if the
        API key is missing or initialization fails.

    Notes
    -----
    Reads the API key from the `DEEPSEEK_API_KEY` environment variable.
    All initialization errors are logged at debug level and swallowed so
    the caller can gracefully fall back to the next source.
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
                base_url=_BASE_URL,
            )
        except Exception as e:
            logger.debug(f"Failed to initialize DeepSeek client: {e}")
            return None

    return _DEEPSEEK_CLIENT


# ============================================================================
# PROMPT BUILDING
# ============================================================================
def _build_prompt(artist: str, context_country: Optional[str] = None) -> str:
    """
    Build the prompt sent to the DeepSeek model.

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
    This is the canonical prompt used across all AI fallbacks (DeepSeek,
    Groq, Muse Spark). Any modification here should be mirrored in the
    other fallback modules to preserve consistency.
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
def search_deepseek_fallback(
    artist: str,
    context_country: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Use the DeepSeek API as fallback to detect country and/or genre.

    Only called when structured sources (MusicBrainz, Wikidata, Wikipedia)
    return nothing. Results are cached per artist to avoid redundant API
    calls.

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

    Notes
    -----
    - Applies a 0.5s delay before each API call as polite rate limiting.
    - Extracts the first JSON object found in the model response via
      regex, so stray text does not break parsing.
    - Country is validated and normalized via
      `validate_and_normalize_country`; genre via `normalize_genre`
      (imported locally to avoid a circular dependency with
      `genre_detector`).
    - Failed results are cached as `(None, None, "DeepSeek failed")` to
      avoid retrying the same artist repeatedly.
    """
    if artist in _DEEPSEEK_CACHE:
        return _DEEPSEEK_CACHE[artist]

    client = _get_deepseek_client()
    if not client:
        return None, None, "DeepSeek not available"

    # Rate limiting
    time.sleep(_RATE_LIMIT_SECONDS)

    prompt = _build_prompt(artist, context_country)

    try:
        # --- Call the model via the OpenAI-compatible interface ---
        response = client.chat.completions.create(
            model=_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=_REQUEST_TEMPERATURE,
            max_tokens=_REQUEST_MAX_TOKENS,
        )

        content = response.choices[0].message.content.strip()

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

            result = (country, genre, "DeepSeek API")
            _DEEPSEEK_CACHE[artist] = result
            return result

    except json.JSONDecodeError as e:
        logger.debug(f"DeepSeek JSON parse error for {artist}: {e}")
    except Exception as e:
        logger.debug(f"DeepSeek API error for {artist}: {e}")

    result = (None, None, "DeepSeek failed")
    _DEEPSEEK_CACHE[artist] = result
    return result
