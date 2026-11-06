def search_muse_fallback(
    artist: str,
    context_country: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Use the Muse Spark API as final fallback to detect country and/or genre.

    Only called when all other sources (including Groq) return nothing.
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

        # --- Log the raw response cleanly (single line) ---
        clean_content = content.replace('\n', ' ').replace('\r', '')
        logger.info(f"  🤖 Muse raw response for {artist}: {clean_content}")

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
