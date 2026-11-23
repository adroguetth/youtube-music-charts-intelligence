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
from typing import Optional

import requests

# ============================================================================
# PROMPT TEMPLATES
# ============================================================================
PROMPTS = {
    "es": (
        "Eres un analista de datos senior. Tu tarea es extraer los hechos clave de esta tabla "
        "para que un redactor los convierta en un análisis ejecutivo.\n\n"
        "TABLA:\n"
        "{table}\n\n"
        "{section_hint}"
        "INSTRUCCIONES:\n"
        "1. Escribe un resumen en viñetas (bullet points), una por hecho. "
        "NO uses etiquetas como 'Top 1:', 'Top 2:', 'Contexto:' o 'Observación:'. "
        "Cada bullet empieza directamente con el dato o el nombre propio.\n"
        "2. Usa las cifras EXACTAS tal como aparecen en la tabla (si dice '40.7M', "
        "escribe '40.7M'; si dice '1,371.3', escribe '1,371.3'). No redondees.\n"
        "3. Cubre, según lo que la tabla permita:\n"
        "   - Los 3 valores más altos (si la tabla es un ranking).\n"
        "   - La tendencia temporal (si la tabla tiene trimestres, meses o años): "
        "¿sube, baja o se mantiene? ¿Dónde está el pico?\n"
        "   - La brecha entre el primero y el segundo (si aplica).\n"
        "   - La concentración: ¿el top 3 suma más del 50% del total? (si aplica).\n"
        "   - La comparación entre grupos (si la tabla compara dos o más categorías, "
        "ej. solo vs colaboración, official vs lyric).\n"
        "   - Cualquier anomalía: un valor atípico, un empate, una caída abrupta, "
        "una categoría con muy pocos datos.\n"
        "   - El total o promedio global (si la tabla lo permite).\n"
        "4. Si la tabla no permite algún punto (ej. no hay dimensión temporal), "
        "omítelo. No inventes datos ni tendencias.\n\n"
        "PROHIBIDO:\n"
        "- Escribir conclusiones, recomendaciones o interpretaciones "
        "('esto sugiere que...', 'esto indica que...', 'esto revela que...').\n"
        "- Especular sobre causas ('porque la audiencia es joven', 'debido a...').\n"
        "- Usar lenguaje poético o adjetivos valorativos ('impresionante', 'sorprendente').\n"
        "- Redondear o parafrasear las cifras.\n"
        "- Usar etiquetas de sección en los bullets.\n\n"
        "PERMITIDO: describir patrones objetivos ('el valor sube de Q1 a Q3', "
        "'la brecha entre el 1º y el 2º es de 0.1M', 'el top 3 concentra el 48% del total'). "
        "Eso NO es interpretar, es describir.\n\n"
        "FORMATO DE SALIDA: solo los bullets, sin introducción, sin cierre, sin título."
    ),
    "en": (
        "You are a data analyst. Your task is to extract the key facts from this table "
        "so a writer can turn them into an executive analysis.\n\n"
        "TABLE:\n"
        "{table}\n\n"
        "{section_hint}"
        "INSTRUCTIONS:\n"
        "1. Write a bullet-point summary, one bullet per fact. "
        "DO NOT use labels like 'Top 1:', 'Top 2:', 'Context:' or 'Observation:'. "
        "Each bullet starts directly with the data point or proper name.\n"
        "2. Use the EXACT figures as they appear in the table (if it says '40.7M', "
        "write '40.7M'; if it says '1,371.3', write '1,371.3'). Do not round.\n"
        "3. Cover, as the table allows:\n"
        "   - The top 3 values (if the table is a ranking).\n"
        "   - The temporal trend (if the table has quarters, months or years): "
        "up, down, or flat? Where is the peak?\n"
        "   - The gap between 1st and 2nd (if applicable).\n"
        "   - Concentration: does the top 3 add up to more than 50% of the total? (if applicable).\n"
        "   - Comparison between groups (if the table compares two or more categories, "
        "e.g. solo vs collaboration, official vs lyric).\n"
        "   - Any anomaly: an outlier, a tie, an abrupt drop, a category with very little data.\n"
        "   - The total or overall average (if the table allows).\n"
        "4. If the table does not allow a point (e.g. no temporal dimension), "
        "omit it. Do not invent data or trends.\n\n"
        "FORBIDDEN:\n"
        "- Writing conclusions, recommendations or interpretations "
        "('this suggests that...', 'this indicates that...', 'this reveals that...').\n"
        "- Speculating about causes ('because the audience is young', 'due to...').\n"
        "- Using poetic language or value adjectives ('impressive', 'surprising').\n"
        "- Rounding or paraphrasing figures.\n"
        "- Using section labels in bullets.\n\n"
        "ALLOWED: describing objective patterns ('the value rises from Q1 to Q3', "
        "'the gap between 1st and 2nd is 0.1M', 'the top 3 concentrate 48% of the total'). "
        "That is NOT interpreting, it is describing.\n\n"
        "OUTPUT FORMAT: only the bullets, no intro, no closing, no title."
    ),
}


# ============================================================================
# HELPERS
# ============================================================================
# Frases que indican que el modelo se negó a responder. Se busca al INICIO
# del texto (no en cualquier posición) para no rechazar bullets legítimos
# como "The gap cannot be computed because...".
_REFUSAL_PREFIXES = (
    "i'm sorry", "i am sorry",
    "i cannot", "i can't", "i can not",
    "i'm unable", "i am unable",
    "sorry, i",
    "lo siento", "no puedo", "no soy capaz",
)


def _looks_like_refusal(text: str) -> bool:
    if not text or len(text) < 20:
        return True
    head = text[:80].strip().lower()
    return any(head.startswith(p) for p in _REFUSAL_PREFIXES)


def _build_prompt(language: str, table_markdown: str, section_hint: str) -> str:
    """Construye el prompt completo. section_hint va como pista opcional
    (e.g. 'Sección: colaboraciones') para orientar el resumen."""
    template = PROMPTS.get(language, PROMPTS["es"])
    hint_block = f"CONTEXTO ADICIONAL:\n{section_hint}\n\n" if section_hint else ""
    return template.format(table=table_markdown, section_hint=hint_block)


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

        # Rate limiter (Groq)
        self.last_groq_request_time = 0.0
        self.groq_min_interval = 20.0       # 20s entre llamadas
        self.groq_cooldown_seconds = 60     # cooldown tras 429

    # ========================================================================
    # GROQ
    # ========================================================================
    def _summarize_with_groq(
        self, table_markdown: str, language: str, section_hint: str = "",
    ) -> tuple[str, int]:
        if not self.groq_api_key:
            print("   [Summarizer] No Groq API key found.")
            return "", 0

        # Rate limiting proactivo
        elapsed = time.time() - self.last_groq_request_time
        if elapsed < self.groq_min_interval:
            time.sleep(self.groq_min_interval - elapsed)

        try:
            # El prompt se construye DENTRO del try para que un .format()
            # roto no crashee el pipeline silenciosamente.
            prompt = _build_prompt(language, table_markdown, section_hint)
        except Exception as e:
            print(f"   [Summarizer] Error construyendo prompt Groq: {e}")
            return "", 0

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
                    "temperature": 0.2,        # determinismo, no creatividad
                    "max_tokens": 3000,         # gpt-oss genera reasoning tokens
                },
                timeout=90,
            )
            self.last_groq_request_time = time.time()

            if response.status_code == 429:
                print(f"   [Summarizer] ⚠️ Groq 429. Cooldown {self.groq_cooldown_seconds}s...")
                time.sleep(self.groq_cooldown_seconds)
                return "", 0

            if response.status_code != 200:
                print(f"   [Summarizer] Groq Error {response.status_code}: {response.text[:300]}")
                return "", 0

            data = response.json()
            summary = (data["choices"][0]["message"]["content"] or "").strip()
            tokens_used = data.get("usage", {}).get("total_tokens", 0)

            if _looks_like_refusal(summary):
                print("   [Summarizer] Groq refusal/empty. Treating as failure.")
                return "", 0

            return summary, tokens_used

        except requests.exceptions.Timeout:
            print("   [Summarizer] Groq timeout.")
            return "", 0
        except Exception as e:
            print(f"   [Summarizer] Groq exception: {type(e).__name__}: {e}")
            return "", 0

    # ========================================================================
    # GOOGLE (Gemma)
    # ========================================================================
    def _summarize_with_google(
        self, table_markdown: str, language: str, section_hint: str = "",
    ) -> tuple[str, int]:
        if not self.google_api_key:
            print("   [Summarizer] No Google API key found.")
            return "", 0

        try:
            prompt = _build_prompt(language, table_markdown, section_hint)
        except Exception as e:
            print(f"   [Summarizer] Error construyendo prompt Google: {e}")
            return "", 0

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemma-3-27b-it:generateContent?key={self.google_api_key}"
        )

        for attempt in range(1, 3):
            try:
                response = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=120,
                )

                if response.status_code != 200:
                    print(f"   [Summarizer] Google Error {response.status_code} "
                          f"(attempt {attempt}/2): {response.text[:300]}")
                    if attempt == 1 and response.status_code == 500:
                        print("   [Summarizer] Reintentando en 5s...")
                        time.sleep(5)
                        continue
                    return "", 0

                data = response.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                summary = (parts[0].get("text", "") if parts else "").strip()
                tokens_used = data.get("usageMetadata", {}).get("totalTokenCount", 0)

                if _looks_like_refusal(summary):
                    print("   [Summarizer] Google refusal/empty.")
                    return "", 0

                return summary, tokens_used

            except Exception as e:
                print(f"   [Summarizer] Google exception (attempt {attempt}/2): "
                      f"{type(e).__name__}: {e}")
                if attempt == 1:
                    time.sleep(5)
                    continue
                return "", 0

        return "", 0

    # ========================================================================
    # META (Muse Spark)
    # ========================================================================
    def _summarize_with_muse_spark(
        self, table_markdown: str, language: str, section_hint: str = "",
    ) -> tuple[str, int]:
        if not self.meta_api_key:
            print("   [Summarizer] No Meta API key found.")
            return "", 0

        try:
            prompt = _build_prompt(language, table_markdown, section_hint)
        except Exception as e:
            print(f"   [Summarizer] Error construyendo prompt Meta: {e}")
            return "", 0

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
                    "temperature": 0.2,
                    "max_tokens": 3000,
                    "reasoning_effort": "low",
                },
                timeout=120,
            )

            if response.status_code != 200:
                print(f"   [Summarizer] Muse Spark Error {response.status_code}: "
                      f"{response.text[:300]}")
                return "", 0

            data = response.json()
            message_content = (
                data.get("choices", [{}])[0].get("message", {}).get("content")
            )
            if not message_content:
                print("   [Summarizer] Muse Spark returned NoneType content.")
                return "", 0

            summary = message_content.strip()
            tokens_used = data.get("usage", {}).get("total_tokens", 0)

            if _looks_like_refusal(summary):
                print("   [Summarizer] Muse Spark refusal/empty.")
                return "", 0

            return summary, tokens_used

        except Exception as e:
            print(f"   [Summarizer] Muse Spark exception: {type(e).__name__}: {e}")
            return "", 0

    # ========================================================================
    # ROUTER
    # ========================================================================
    def summarize(
        self,
        table_markdown: str,
        model_name: str,
        language: str = "es",
        section_hint: str = "",
    ) -> tuple[str, str, int]:
        """
        Generate a summary from a Markdown table, using the specified model
        and falling back through the chain if needed.

        Returns
        -------
        tuple[str, str, int]
            (summary_text, model_used, tokens_used). summary_text == "" si
            todos fallaron.
        """
        # Orden de intento según lo que pidió BudgetManager
        order: list[str]
        if model_name == "groq_gpt_oss":
            order = ["groq_gpt_oss", "google_gemma", "muse_spark"]
        elif model_name == "google_gemma":
            order = ["google_gemma", "muse_spark"]
        elif model_name == "muse_spark":
            order = ["muse_spark"]
        else:
            # Nombre desconocido: intentar la cadena completa por seguridad
            print(f"   [Summarizer] Modelo desconocido '{model_name}'. "
                  f"Intentando cadena completa.")
            order = ["groq_gpt_oss", "google_gemma", "muse_spark"]

        for attempt_model in order:
            print(f"   [Summarizer] Intentando {attempt_model}...")
            if attempt_model == "groq_gpt_oss":
                summary, tokens = self._summarize_with_groq(table_markdown, language, section_hint)
                if summary:
                    return summary, "groq_gpt_oss", tokens
            elif attempt_model == "google_gemma":
                summary, tokens = self._summarize_with_google(table_markdown, language, section_hint)
                if summary:
                    return summary, "google_gemma", tokens
            elif attempt_model == "muse_spark":
                summary, tokens = self._summarize_with_muse_spark(table_markdown, language, section_hint)
                if summary:
                    return summary, "muse_spark", tokens

        print("   [Summarizer] Todos los modelos fallaron.")
        return "", model_name, 0
