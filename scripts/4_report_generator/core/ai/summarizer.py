"""
Summarizer - Table Analysis via AI Models
============================================================================
Reads a DataFrame in Markdown format and generates a structured summary using
AI models with a three-tier fallback chain:
    1. Groq (GPT-OSS-120B) - fast, free
    2. Google (Gemma 4) - free, generous daily limit
    3. Meta (Muse Spark 1.3 Contributor, reasoning effort low) - paid, reliable

Responsibilities
----------------
- Build the specific prompt for table summarization.
- Try to summarize using Groq first.
- Fallback to Google Gemma if Groq fails or hits its limit.
- Fallback to Meta Muse Spark if both Groq and Google fail.
- Return the raw summary string.

Notes
-----
- This module does NOT make decisions about which model to use; it receives
  the model name from `BudgetManager`.
- It expects API keys to be configured in the environment variables
  (`GROQ_API_KEY`, `GOOGLE_API_KEY`, and `META_API_KEY`).
- If all three models fail, it returns an empty string so the pipeline continues.
- The prompt is intentionally flexible to avoid model refusals on tables
  that don't have a clear "leader" or "second place" (e.g., temporal analysis).

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import os
import time
import requests

# ============================================================================
# PROMPT TEMPLATES (flexible to avoid refusals)
# ============================================================================
PROMPTS = {
    "es": (
        "Eres un analista de datos. Tu única tarea es extraer los hechos clave de esta tabla:\n\n"
        "{table}\n\n"
        "Escribe un resumen estructurado en viñetas (bullet points) con las siguientes reglas:\n"
        "1. **Dato más relevante:** Menciona el dato más alto o más importante de la tabla (con su cifra exacta).\n"
        "2. **Tendencia general:** Describe la tendencia o el contraste más notable (ej. quién sube, quién baja, qué grupo domina).\n"
        "3. **Contexto:** Menciona la cifra total o el promedio general si aplica.\n"
        "4. **Observación:** Destaca cualquier dato que rompa la tendencia (ej. un valor atípico, un empate, una caída abrupta).\n"
        "Sé directo, usa los números exactos de la tabla y no uses lenguaje poético. "
        "Si la tabla no tiene un 'líder' claro, describe el patrón general sin inventar datos."
    ),
    "en": (
        "You are a data analyst. Your only task is to extract key facts from this table:\n\n"
        "{table}\n\n"
        "Write a structured bullet-point summary with the following rules:\n"
        "1. **Most relevant data point:** Mention the highest or most important figure in the table (with its exact number).\n"
        "2. **General trend:** Describe the most notable trend or contrast (e.g., who rises, who falls, which group dominates).\n"
        "3. **Context:** Mention the total figure or overall average if applicable.\n"
        "4. **Observation:** Highlight any data point that breaks the trend (e.g., an outlier, a tie, an abrupt drop).\n"
        "Be direct, use exact numbers from the table, and do not use poetic language. "
        "If the table has no clear 'leader', describe the general pattern without inventing data."
    )
}


class TableSummarizer:
    def __init__(
        self,
        groq_api_key: str | None = None,
        google_api_key: str | None = None,
        meta_api_key: str | None = None,
    ):
        self.groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
        self.google_api_key = google_api_key or os.environ.get("GOOGLE_API_KEY")
        self.meta_api_key = meta_api_key or os.environ.get("META_API_KEY")

        # Rate Limiter variables (for Groq)
        self.last_groq_request_time = 0
        self.groq_cooldown_seconds = 60

    # ========================================================================
    # GROQ
    # ========================================================================
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
                    "Content-Type": "application/json",
                },
                json={
                    "model": "openai/gpt-oss-120b",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
                timeout=90,
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

            # Validate response to catch model refusals
            refusal_phrases = ["unable to", "cannot", "i'm sorry", "i am sorry"]
            if not summary or len(summary) < 20 or any(phrase in summary.lower() for phrase in refusal_phrases):
                print("   [Summarizer] Groq returned a refusal or an empty response. Treating as failure.")
                return "", 0

            return summary, tokens_used

        except requests.exceptions.Timeout:
            print(f"   [Summarizer] Groq Timeout after 90 seconds.")
            return "", 0
        except Exception as e:
            print(f"   [Summarizer] Groq Exception: {e}")
            return "", 0

    # ========================================================================
    # GOOGLE (Gemma)
    # ========================================================================
    def _summarize_with_google(self, table_markdown: str, language: str) -> tuple[str, int]:
        """Call Google API (Gemma 4) with one retry on error 500."""
        if not self.google_api_key:
            print("   [Summarizer] No Google API key found.")
            return "", 0

        prompt = PROMPTS.get(language, PROMPTS["es"]).format(table=table_markdown)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-4-26b-a4b-it:generateContent?key={self.google_api_key}"

        # Try up to 2 times (1 initial + 1 retry)
        for attempt in range(1, 3):
            try:
                response = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}]
                    },
                    timeout=120,  # Increased from 90 to 120 seconds
                )

                if response.status_code != 200:
                    print(f"   [Summarizer] Google Error {response.status_code} (attempt {attempt}/2): {response.text[:200]}")
                    if attempt == 1 and response.status_code == 500:
                        print("   [Summarizer] Retrying in 5 seconds...")
                        time.sleep(5)
                        continue
                    return "", 0

                data = response.json()
                summary = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                tokens_used = data.get("usageMetadata", {}).get("totalTokenCount", 0)

                # Validate response to catch model refusals
                refusal_phrases = ["unable to", "cannot", "i'm sorry", "i am sorry"]
                if not summary or len(summary) < 20 or any(phrase in summary.lower() for phrase in refusal_phrases):
                    print("   [Summarizer] Google returned a refusal or an empty response.")
                    return "", 0

                return summary, tokens_used

            except Exception as e:
                print(f"   [Summarizer] Google Exception (attempt {attempt}/2): {e}")
                if attempt == 1:
                    time.sleep(5)
                    continue
                return "", 0

        return "", 0

    # ========================================================================
    # META (Muse Spark 1.3 Contributor, reasoning effort low)
    # ========================================================================
    def _summarize_with_muse_spark(self, table_markdown: str, language: str) -> tuple[str, int]:
        """Call Meta Muse Spark API (Contributor mode, reasoning effort low)."""
        if not self.meta_api_key:
            print("   [Summarizer] No Meta API key found.")
            return "", 0

        prompt = PROMPTS.get(language, PROMPTS["es"]).format(table=table_markdown)

        # URL and model per Meta's documentation:
        # https://dev.meta.ai/docs/muse-spark
        url = "https://api.meta.ai/v1/chat/completions"
        model_id = "muse-spark-1.3-contributor"

        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.meta_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 500,
                    "reasoning_effort": "low",
                },
                timeout=120,
            )

            if response.status_code != 200:
                print(f"   [Summarizer] Muse Spark Error {response.status_code}: {response.text[:200]}")
                return "", 0

            data = response.json()
            summary = data["choices"][0]["message"]["content"].strip()
            tokens_used = data.get("usage", {}).get("total_tokens", 0)

            # Validate response to catch model refusals
            refusal_phrases = ["unable to", "cannot", "i'm sorry", "i am sorry"]
            if not summary or len(summary) < 20 or any(phrase in summary.lower() for phrase in refusal_phrases):
                print("   [Summarizer] Muse Spark returned a refusal or an empty response.")
                return "", 0

            return summary, tokens_used

        except Exception as e:
            print(f"   [Summarizer] Muse Spark Exception: {e}")
            return "", 0

    # ========================================================================
    # ROUTER
    # ========================================================================
    def summarize(self, table_markdown: str, model_name: str, language: str = "es") -> tuple[str, str, int]:
        """
        Generate a summary from a Markdown table, using the specified model
        and falling back through the chain if needed.

        Parameters
        ----------
        table_markdown : str
            The DataFrame converted to Markdown.
        model_name : str
            The model decided by `BudgetManager` ("groq_gpt_oss", "google_gemma",
            or "muse_spark").
        language : str
            "es" or "en".

        Returns
        -------
        tuple[str, str, int]
            (summary_text, model_used, tokens_used)
        """
        # Attempt 1: Groq
        if model_name == "groq_gpt_oss":
            summary, tokens = self._summarize_with_groq(table_markdown, language)
            if summary:
                return summary, "groq_gpt_oss", tokens

            print("   [Summarizer] Groq failed. Trying Google Gemma as fallback...")
            summary, tokens = self._summarize_with_google(table_markdown, language)
            if summary:
                return summary, "google_gemma", tokens

            print("   [Summarizer] Google failed. Trying Meta Muse Spark as final fallback...")
            summary, tokens = self._summarize_with_muse_spark(table_markdown, language)
            if summary:
                return summary, "muse_spark", tokens

        # Attempt 2: Google
        elif model_name == "google_gemma":
            summary, tokens = self._summarize_with_google(table_markdown, language)
            if summary:
                return summary, "google_gemma", tokens

            print("   [Summarizer] Google failed. Trying Meta Muse Spark as final fallback...")
            summary, tokens = self._summarize_with_muse_spark(table_markdown, language)
            if summary:
                return summary, "muse_spark", tokens

        # Attempt 3: Muse Spark (explicitly chosen by BudgetManager)
        elif model_name == "muse_spark":
            summary, tokens = self._summarize_with_muse_spark(table_markdown, language)
            if summary:
                return summary, "muse_spark", tokens

        # All failed
        print("   [Summarizer] All available models failed to generate a summary.")
        return "", model_name, 0
