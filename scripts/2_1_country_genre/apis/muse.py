"""
Muse Spark (Meta AI) API Client - Deep Fallback Country and Genre Detection
============================================================================
Final-fallback detection module for musical artist metadata. Uses direct
HTTP requests to the Meta API `/v1/responses` endpoint with the
`muse-spark-1.3-contributor` model. Provides country of origin and primary
musical genre for a given artist name.

This module acts as the last-resort fallback in the metadata detection
pipeline, invoked only when all other sources (including Qwen) return
nothing. It includes in-memory caching, rate limiting, structured response
parsing, and robust JSON extraction with validation/normalization of
returned values.

Features
--------
- Direct HTTP requests to the Meta API `/v1/responses` endpoint.
- Uses the `muse-spark-1.3-contributor` model (default reasoning).
- In-memory cache keyed by artist name to avoid redundant API calls.
- Automatic country validation and normalization.
- Automatic genre normalization via the local genre detector.
- Structured parsing of the Meta API response blocks (`output` →
  `message` → `output_text`).
- Robust JSON extraction from model output.
- Graceful degradation when API key is missing or calls fail.

Dependencies
------------
- Internal: `..config` (logger), `..utils.country_utils`
  (validate_and_normalize_country), `..genre_detector` (normalize_genre,
  imported locally to avoid circular dependency).
- External: requests, os, json, re, time, typing (stdlib).

Requirements
------------
- Python 3.7+
- `requests` library installed.
- Environment variable `META_API_KEY` set with a valid Meta API key.

Notes
-----
- The module-level cache is a singleton shared across calls within the
  same process.
- Rate limiting is applied via a 0.5s sleep between calls (more
  conservative than the Groq fallback).
- The prompt is intentionally identical to the DeepSeek/Groq fallback
  prompts for consistency across fallback sources.
- Failures are cached (as `(None, None, "Muse failed")` or
  `(None, None, "Muse empty response")`) to avoid retrying the same
  artist repeatedly.
- The Meta response is expected to contain a list of `output` blocks; the
  module walks `message` → `content` → `output_text` to concatenate the
  final text.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

import json
import os
import re
import time
from typing import Optional, Tuple

import requests

from ..config import logger
from ..utils.country_utils import validate_and_normalize_country

# ============================================================================
# CONSTANTS AND GLOBAL STATE
# ============================================================================
_API_URL = "https://api.meta.ai/v1/responses"
_MODEL_NAME = "muse-spark-1.3-contributor"
_REQUEST_TIMEOUT_SECONDS = 30
_RATE_LIMIT_SECONDS = 0.5

_MUSE_CACHE = {}  # Cache: {artist: (country, genre, source)}


# ============================================================================
# PROMPT BUILDING
# ============================================================================
def _build_prompt(artist: str, context_country: Optional[str] = None) -> str:
    """
    Build the prompt sent to the Muse Spark model.

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
    The prompt is intentionally identical to the DeepSeek/Groq fallback
    prompts for consistency across fallback sources.
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
# RESPONSE PARSING
# ============================================================================
def _extract_text_from_response(response_data: dict) -> str:
    """
    Extract the concatenated output text from a Meta API response.

    The Muse response is expected to contain a list of `output` blocks;
    this helper walks `message` → `content` → `output_text` and joins all
    text fragments.

    Parameters
    ----------
    response_data : dict
        Parsed JSON response from the Meta API.

    Returns
    -------
    str
        Concatenated output text, or an empty string if no output text
        blocks were found.

    Notes
    -----
    The response may contain reasoning blocks alongside the final message;
    only `output_text` content blocks are collected.
    """
    content = ""

    if "output" not in response_data:
        return content

    for block in response_data["output"]:
        if block.get("type") != "message" or "content" not in block:
            continue
        for content_block in block["content"]:
            if content_block.get("type") == "output_text":
                content += content_block.get("text", "")

    return content


# ============================================================================
# FALLBACK DETECTION
# ============================================================================
def search_muse_fallback(
    artist: str,
    context_country: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Use the Muse Spark API as final fallback to detect country and/or genre.

    Only called when all other sources (including Qwen) return nothing.
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
        - `source_info` describes the outcome (e.g., "Muse Spark (Meta)",
          "Muse not available", "Muse failed", "Muse empty response").

    Notes
    -----
    - Applies a 0.5s delay before each API call as polite rate limiting.
    - Uses direct HTTP POST to the Meta `/v1/responses` endpoint.
    - Extracts the first JSON object found in the response text via regex,
      so stray text does not break parsing.
    - Country is validated and normalized via
      `validate_and_normalize_country`; genre via `normalize_genre`
      (imported locally to avoid a circular dependency with
      `genre_detector`).
    - Failures are cached to avoid retrying the same artist repeatedly.
    """
    if artist in _MUSE_CACHE:
        return _MUSE_CACHE[artist]

    api_key = os.getenv("META_API_KEY")
    if not api_key:
        logger.debug("Muse (Meta) API key not set")
        return None, None, "Muse not available"

    # Rate limiting
    time.sleep(_RATE_LIMIT_SECONDS)

    prompt = _build_prompt(artist, context_country)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": _MODEL_NAME,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            }
        ],
        # "reasoning_effort": "high",  <-- REMOVED: Not supported by Contributor model
        "stream": False,
    }

    try:
        # --- Call the Meta API ---
        response = requests.post(
            _API_URL,
            headers=headers,
            json=payload,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        
        # --- Log the real error if the request fails ---
        if response.status_code != 200:
            logger.error(f"  ❌ Muse API error for {artist}: {response.status_code} - {response.text[:150]}")
            _MUSE_CACHE[artist] = (None, None, f"Muse HTTP {response.status_code}")
            return None, None, f"Muse HTTP {response.status_code}"

        response_data = response.json()

        # --- Extract output text from structured response blocks ---
        content = _extract_text_from_response(response_data)

        if not content:
            logger.debug(f"  ❌ Muse response did not contain output text for {artist}")
            _MUSE_CACHE[artist] = (None, None, "Muse empty response")
            return None, None, "Muse empty response"

        # --- Log the raw response exactly as returned ---
        logger.info(f"  🤖 Muse raw response for {artist}: {content}")

        # --- Extract and parse JSON from the response text ---
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

            result = (country, genre, "Muse Spark (Meta)")
            _MUSE_CACHE[artist] = result
            return result

        logger.debug(
            f"  ❌ Muse JSON parse failed for {artist}. Raw content: {content[:100]}..."
        )

    except requests.exceptions.RequestException as e:
        logger.debug(f"  ❌ Muse API connection error for {artist}: {e}")
    except json.JSONDecodeError as e:
        logger.debug(f"  ❌ Muse JSON decode error for {artist}: {e}")
    except Exception as e:
        logger.debug(f"  ❌ Muse API error for {artist}: {e}")

    result = (None, None, "Muse failed")
    _MUSE_CACHE[artist] = result
    return result
