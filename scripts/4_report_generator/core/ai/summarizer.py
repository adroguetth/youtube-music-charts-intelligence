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
import time
import requests

# ============================================================================
# PROMPT TEMPLATES
# ============================================================================
# Instruct the model to extract facts and do calculations, NOT to write prose.
# The final analytical writing is handled by DeepSeek in the next step.
PROMPTS = {
    "es": (
        "Eres un analista de datos. Tu única tarea es extraer los hechos clave de esta tabla:\n\n"
        "{table}\n\n"
        "Escribe un resumen estructurado en viñetas (bullet points) con las siguientes reglas:\n"
        "1. **Líder:** Quién es el número 1 en la métrica principal y cuál es su cifra exacta.\n"
        "2. **Comparativa:** Cuál es la diferencia numérica o porcentual entre el 1º y el 2º lugar.\n"
        "3. **Contexto:** Menciona la cifra total o el promedio general si aplica.\n"
        "4. **Anomalía:** Destaca un dato que rompa la tendencia (ej. alguien con pocas vistas pero mucho engagement).\n"
        "Sé directo, usa los números exactos de la tabla y no uses lenguaje poético."
    ),
    "en": (
        "You are a data analyst. Your only task is to extract key facts from this table:\n\n"
        "{table}\n\n"
        "Write a structured bullet-point summary with the following rules:\n"
        "1. **Leader:** Who is number 1 in the main metric and what is their exact figure.\n"
        "2. **Comparison:** What is the numerical or percentage gap between 1st and 2nd place.\n"
        "3. **Context:** Mention the total figure or overall average if applicable.\n"
        "4. **Anomaly:** Highlight a data point that breaks the trend (e.g., someone with low views but high engagement).\n"
        "Be direct, use exact numbers from the table, and do not use poetic language."
    )
}


class TableSummarizer:
    def __init__(self, groq_api_key: str | None = None, google_api_key: str | None = None):
        self.groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
        self.google_api_key = google_api_key or os.environ.get("GOOGLE_API_KEY")
        
        # Rate Limiter variables
        self.last_groq_request_time = 0
        self.groq_cooldown_seconds = 60

    def _summarize_with_groq(self, table_markdown: str, language: str) -> tuple[str, int]:
        """Call Groq API with Rate Limiting protection."""
        if not self.groq_api_key:
            print("   [Summarizer] No Groq API key found.")
            return "", 0

        # Proactive rate limiting (avoid bursts)
        current_time = time.time()
        time_since_last = current_time - self.last_groq_request_time
        if time_since_last < 4:
            time.sleep(4 - time_since_last)

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
                    "max_tokens": 500
                },
                timeout=90
            )
            
            self.last_groq_request_time = time.time()

            # Reactive rate limiting (if blocked)
            if response.status_code == 429:
                print(f"   [Summarizer] ⚠️ Groq 429 (Rate Limit). Pausing {self.groq_cooldown_seconds} seconds...")
                time.sleep(self.groq_cooldown_seconds)
                return "", 0

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
        """Call Google API."""
        if not self.google_api_key:
            print("   [Summarizer] No Google API key found.")
            return "", 0

        prompt = PROMPTS.get(language, PROMPTS["es"]).format(table=table_markdown)
        
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
