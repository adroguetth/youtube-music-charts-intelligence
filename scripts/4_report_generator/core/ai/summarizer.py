"""
Summarizer - Table Analysis via Free-Tier Models
============================================================================
Reads a DataFrame in Markdown format and generates a 5-line summary using
free-tier models (Groq or Google Gemma).

Responsibilities
----------------
- Build the specific prompt for table summarization.
- Try to summarize using Groq (GPT-OSS-120B) first.
- Fallback to Google (Gemma-4-31B-it) if Groq fails or hits its limit.
- Return the raw summary string.

Notes
-----
- This module does NOT make decisions about which model to use; it receives
  the model name from `BudgetManager`.
- It expects API keys to be configured in the environment variables
  (`GROQ_API_KEY` and `GOOGLE_API_KEY`).
- If both models fail, it returns an empty string so the pipeline continues.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import os
import requests

# ============================================================================
# PROMPT TEMPLATES
# ============================================================================
PROMPTS = {
    "es": (
        "Eres un analista experto en la industria musical. "
        "Lee la siguiente tabla de datos en formato Markdown:\n\n"
        "{table}\n\n"
        "Escribe un resumen conciso de 5 líneas destacando las estadísticas más importantes, "
        "los líderes y cualquier tendencia notable. No inventes datos, usa solo lo que está en la tabla."
    ),
    "en": (
        "You are an expert music industry analyst. "
        "Read the following data table in Markdown format:\n\n"
        "{table}\n\n"
        "Write a concise 5-line summary highlighting the most important statistics, "
        "the leaders, and any notable trends. Do not hallucinate data, use only what is in the table."
    )
}


class TableSummarizer:
    def __init__(self, groq_api_key: str | None = None, google_api_key: str | None = None):
        self.groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
        self.google_api_key = google_api_key or os.environ.get("GOOGLE_API_KEY")

    def _summarize_with_groq(self, table_markdown: str, language: str) -> tuple[str, int]:
        """Call Groq API. Returns (summary, tokens_used)."""
        if not self.groq_api_key:
            return "", 0

        prompt = PROMPTS.get(language, PROMPTS["es"]).format(table=table_markdown)
        
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "openai/gpt-oss-120b",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 250
                },
                timeout=20
            )
            response.raise_for_status()
            data = response.json()
            
            summary = data["choices"][0]["message"]["content"].strip()
            tokens_used = data.get("usage", {}).get("total_tokens", 0)
            
            return summary, tokens_used
            
        except Exception as e:
            print(f"   [Summarizer] Groq failed: {e}")
            return "", 0

    def _summarize_with_google(self, table_markdown: str, language: str) -> tuple[str, int]:
        """Call Google API. Returns (summary, tokens_used)."""
        if not self.google_api_key:
            return "", 0

        prompt = PROMPTS.get(language, PROMPTS["es"]).format(table=table_markdown)
        
        # URL de la API de Google Gemini/Gemma (ajustar según el endpoint exacto de Google AI Studio)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent?key={self.google_api_key}"
        
        try:
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}]
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            summary = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Google no siempre devuelve el uso exacto de tokens, pero podemos estimarlo
            tokens_used = data.get("usageMetadata", {}).get("totalTokenCount", 0)
            
            return summary, tokens_used
            
        except Exception as e:
            print(f"   [Summarizer] Google failed: {e}")
            return "", 0

    def summarize(self, table_markdown: str, model_name: str, language: str = "es") -> tuple[str, str, int]:
        """
        Generate a summary from a Markdown table.
        
        Parameters
        ----------
        table_markdown : str
            The DataFrame converted to Markdown.
        model_name : str
            "groq_gpt_oss" or "google_gemma" (provided by BudgetManager).
        language : str
            "es" or "en".

        Returns
        -------
        tuple[str, str, int]
            (summary_text, model_used, tokens_used)
        """
        if model_name == "groq_gpt_oss":
            summary, tokens = self._summarize_with_groq(table_markdown, language)
            if summary:
                return summary, "groq_gpt_oss", tokens
            else:
                # Si Groq falló (por ejemplo, por límite de cuota), intentamos con Google
                print("   [Summarizer] Groq failed or returned empty. Trying Google Gemma as fallback...")
                summary, tokens = self._summarize_with_google(table_markdown, language)
                if summary:
                    return summary, "google_gemma", tokens

        elif model_name == "google_gemma":
            summary, tokens = self._summarize_with_google(table_markdown, language)
            if summary:
                return summary, "google_gemma", tokens
        
        # Si llegamos aquí, ambos fallaron o el modelo no estaba disponible
        return "", model_name, 0
