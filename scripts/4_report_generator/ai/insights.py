"""
AI Insights - DeepSeek API Integration
============================================================================
Connects to the DeepSeek API to generate the narrative texts for the report.

This module handles:
- Extraction of key metrics from the Pandas DataFrame.
- Prompt engineering for English and Spanish.
- API requests with error handling and retries.
- Returning a structured dictionary with the texts.

Dependencies
------------
- Internal: `..config` (API keys, model settings, logger).
- External: requests, json (stdlib + third-party).

Requirements
------------
- Python 3.7+
- DEEPSEEK_API_KEY environment variable set.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import json
import time
import requests
import pandas as pd
from typing import Dict, Any

from ..config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_TEMPERATURE,
    logger
)


# ============================================================================
# HELPER: DATA SUMMARY FOR PROMPT
# ============================================================================
def _extract_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """Extract key metrics from the DataFrame to build the AI prompt."""
    
    top_songs = df.nsmallest(3, 'rank')[['track_name', 'artist_names', 'views']].to_dict('records')
    top_countries = df['artist_country'].value_counts().head(3).to_dict()
    top_genres = df['macro_genre'].value_counts().head(3).to_dict()
    collabs = len(df[df['is_collaboration'] == 1])
    
    return {
        "total_songs": len(df),
        "unique_countries": df['artist_country'].nunique(),
        "total_views": int(df['views'].sum()),
        "total_likes": int(df['likes'].sum()),
        "top_songs": top_songs,
        "top_countries": top_countries,
        "top_genres": top_genres,
        "collaborations": collabs
    }


# ============================================================================
# MAIN FUNCTION: GENERATE INSIGHTS
# ============================================================================
def generate_insights(df: pd.DataFrame, week_str: str, language: str = "en") -> Dict[str, str]:
    """
    Generate the report texts using DeepSeek.

    Parameters
    ----------
    df : pd.DataFrame
        The enriched chart data.
    week_str : str
        The week identifier (e.g., '2026-W45').
    language : str
        'en' for English or 'es' for Spanish.

    Returns
    -------
    dict
        Dictionary with keys: 'intro', 'trend', 'top_songs', 'countries'.
        If the API fails, it returns a dictionary with error messages.
    """
    
    if not DEEPSEEK_API_KEY:
        logger.warning("⚠️ DEEPSEEK_API_KEY not set. Returning placeholder texts.")
        return _get_placeholders(language)

    summary = _extract_summary(df)

    # Build the prompt based on language
    if language == "es":
        prompt = f"""
        Eres un analista experto en la industria musical. Escribe el contenido para un informe semanal de tendencias musicales basado en estos datos de la semana {week_str}.
        
        Datos:
        - Top 3 canciones: {summary['top_songs']}
        - Países dominantes: {summary['top_countries']}
        - Géneros dominantes: {summary['top_genres']}
        - Colaboraciones en el Top 100: {summary['collaborations']}
        
        Devuelve ÚNICAMENTE un objeto JSON válido con las siguientes claves (textos en español):
        - "intro": Un resumen ejecutivo de 2 párrafos (aprox. 150 palabras) destacando la diversidad global.
        - "trend": 1 oración analizando la tendencia de vistas (inventa una tendencia positiva o negativa coherente).
        - "top_songs": 1 oración analizando el top de canciones.
        - "countries": 1 oración analizando la distribución geográfica.
        
        No uses markdown en los textos, solo texto plano.
        """
    else:
        prompt = f"""
        You are an expert music industry analyst. Write the content for a weekly music trends report based on this data for week {week_str}.
        
        Data:
        - Top 3 songs: {summary['top_songs']}
        - Dominant countries: {summary['top_countries']}
        - Dominant genres: {summary['top_genres']}
        - Collaborations in the Top 100: {summary['collaborations']}
        
        Return ONLY a valid JSON object with the following keys (texts in English):
        - "intro": An executive summary of 2 paragraphs (approx. 150 words) highlighting global diversity.
        - "trend": 1 sentence analyzing the view trend (invent a coherent positive or negative trend).
        - "top_songs": 1 sentence analyzing the top songs.
        - "countries": 1 sentence analyzing the geographic distribution.
        
        Do not use markdown in the texts, just plain text.
        """

    # Retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": DEEPSEEK_TEMPERATURE,
                    "response_format": {"type": "json_object"}  # Force JSON output
                },
                timeout=45
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                # Parse the JSON string returned by the AI
                insights = json.loads(content)
                
                # Ensure all keys exist
                return {
                    "intro": insights.get("intro", "Analysis not available."),
                    "trend": insights.get("trend", ""),
                    "top_songs": insights.get("top_songs", ""),
                    "countries": insights.get("countries", "")
                }
            elif 500 <= response.status_code < 600:
                logger.warning(f"⚠️ DeepSeek server error {response.status_code}. Retrying...")
                time.sleep(2 ** attempt)
            else:
                logger.error(f"❌ DeepSeek API error: {response.status_code} - {response.text[:100]}")
                break
                
        except requests.Timeout:
            logger.warning(f"⚠️ DeepSeek timeout. Retrying... ({attempt + 1}/{max_retries})")
            time.sleep(2 ** attempt)
        except json.JSONDecodeError:
            logger.error("❌ Failed to parse AI response as JSON.")
            break
        except Exception as e:
            logger.error(f"❌ Unexpected error calling DeepSeek: {e}")
            break

    # Fallback if all retries fail
    return _get_placeholders(language)


def _get_placeholders(language: str) -> Dict[str, str]:
    """Return default texts if the API fails."""
    if language == "es":
        return {
            "intro": "No se pudo generar el resumen ejecutivo. Por favor, verifique la configuración de la API.",
            "trend": "Análisis de tendencia no disponible.",
            "top_songs": "Análisis de canciones no disponible.",
            "countries": "Análisis geográfico no disponible."
        }
    return {
        "intro": "Could not generate the executive summary. Please check the API configuration.",
        "trend": "Trend analysis not available.",
        "top_songs": "Top songs analysis not available.",
        "countries": "Geographic analysis not available."
    }
