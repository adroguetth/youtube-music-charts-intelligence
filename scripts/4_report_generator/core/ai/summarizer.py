"""
Summarizer - Table Analysis via Free-Tier Models
============================================================================
Reads a DataFrame in Markdown format and generates a 5-line summary using
free-tier models (Groq or Google Gemma).

Responsibilities
----------------
- Build the specific prompt for table summarization.
- Try to summarize using Groq (GPT-OSS-120B) first.
- Fallback to Google (Gemma 4) if Groq fails or hits its limit.
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
        "Eres un analista de datos de la industria musical. "
        "Analiza la siguiente tabla:\n\n"
        "{table}\n\n"
        "Extrae un resumen estructurado de máximo 5 oraciones. "
        "Reglas estrictas:\n"
        "1. Menciona el líder absoluto y su cifra exacta.\n"
        "2. Calcula y menciona una tasa o ratio clave si es posible (ej. engagement rate).\n"
        "3. Destaca un dato de contraste (una brecha, una caída o una concentración).\n"
        "4. No uses viñetas. No uses lenguaje poético. Ve directo al dato matemático."
    ),
    "en": (
        "You are a music industry data analyst. "
        "Analyze the following table:\n\n"
        "{table}\n\n"
        "Extract a structured summary of maximum 5 sentences. "
        "Strict rules:\n"
        "1. Mention the absolute leader and its exact figure.\n"
        "2. Calculate and mention a key rate or ratio if possible (e.g., engagement rate).\n"
        "3. Highlight a contrasting data point (a gap, a drop, or a concentration).\n"
        "4. No bullet points. No poetic language. Get straight to the mathematical data."
    )
}


class TableSummarizer:
    def __init__(self, groq_api_key: str | None = None, google_api_key: str | None = None):
        self.groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
        self.google_api_key = google_api_key or os.environ.get("GOOGLE_API_KEY")

    def _summarize_with_groq(self, table_markdown: str, language: str) -> tuple[str, int]:
        """Call Groq API. Returns (summary, tokens_used)."""
        if not self.groq_api_key:
            print("   [Summarizer] No Groq API key found.")
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
                    "temperature": 0.1,
                    "max_tokens": 500  # Aumentado para dar espacio a los tokens de razonamiento
                },
                timeout=90  # Aumentado a 90s porque gpt-oss-120b tarda en procesar
            )
            
            if response.status_code != 200:
                print(f"   [Summarizer] Groq Error {response.status_code}: {response.text[:200]}")
                return "", 0
                
            data = response.json()
            summary = data["choices"][0]["message"]["content"].strip()
            tokens_used = data.get("usage", {}).get("total_tokens", 0)
            
            return summary, tokens_used
            
        except requests.exceptions.Timeout:
            print(f"   [Summarizer] Groq Timeout after 90 seconds.")
            return "", 0
        except Exception as e:
            print(f"   [Summarizer] Groq Exception: {e}")
            return "", 0

    def _summarize_with_google(self, table_markdown: str, language: str) -> tuple[str, int]:
        """Call Google API. Returns (summary, tokens_used)."""
        if not self.google_api_key:
            print("   [Summarizer] No Google API key found.")
            return "", 0

        prompt = PROMPTS.get(language, PROMPTS["es"]).format(table=table_markdown)
        
        # URL exacta para el modelo gemma-4-26b-a4b-it
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-4-26b-a4b-it:generateContent?key={self.google_api_key}"
        
        try:
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}]
                },
                timeout=60
            )
            
            if response.status_code != 200:
                print(f"   [Summarizer] Google Error {response.status_code}: {response.text[:200]}")
                return "", 0
                
            data = response.json()
            summary = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            tokens_used = data.get("usageMetadata", {}).get("totalTokenCount", 0)
            
            return summary, tokens_used
            
        except Exception as e:
            print(f"   [Summarizer] Google Exception: {e}")
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
                print("   [Summarizer] Groq failed. Trying Google Gemma as fallback...")
                summary, tokens = self._summarize_with_google(table_markdown, language)
                if summary:
                    return summary, "google_gemma", tokens

        elif model_name == "google_gemma":
            summary, tokens = self._summarize_with_google(table_markdown, language)
            if summary:
                return summary, "google_gemma", tokens
        
        # If both failed
        print("   [Summarizer] Both Groq and Google failed to generate a summary.")
        return "", model_name, 0
