"""
Writer - Final Analysis Generation via DeepSeek
============================================================================
Takes a raw summary from the `summarizer` and polishes it into a
professional, engaging analysis using DeepSeek.

Responsibilities
----------------
- Build the specific prompt for the final analysis.
- Call the DeepSeek API.
- Return the polished text.

Notes
-----
- DeepSeek does NOT calculate. It only writes. The numbers and insights
  come strictly from the `summary` provided by the small models.
- If the API key is missing or the call fails, it returns the original
  summary so the report is never left empty.

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
WRITER_PROMPTS = {
    "general_stats": {
        "es": (
            "Actúa como un Consultor Senior de Estrategia Musical. "
            "Analiza el resumen estadístico de la semana:\n\n{summary}\n\n"
            "Redacta un análisis ejecutivo de 4 a 6 líneas. "
            "Sigue esta estructura:\n"
            "1. **Contexto:** Describe el tamaño del catálogo usando el número total de canciones.\n"
            "2. **Benchmark:** Compara la tasa de engagement con el estándar de la industria (3%-8%). ¿Estamos ante una audiencia hiper-fiel o pasiva?\n"
            "3. **Diversidad:** Menciona la cantidad de países y géneros. ¿Es un fenómeno local o global?\n"
            "4. **Conclusión:** Cierra con una frase de impacto estratégico. "
            "PROHIBIDO: No uses 'En conclusión', 'Es importante destacar' ni lenguaje poético. Ve al dato."
        ),
        "en": (
            "Act as a Senior Music Strategy Consultant. "
            "Analyze this week's statistical summary:\n\n{summary}\n\n"
            "Write an executive analysis of 4 to 6 lines. "
            "Follow this structure:\n"
            "1. **Context:** Describe the catalog size using the total number of songs.\n"
            "2. **Benchmark:** Compare the engagement rate with the industry standard (3%-8%). Are we facing a hyper-loyal or passive audience?\n"
            "3. **Diversity:** Mention the number of countries and genres. Is this a local or global phenomenon?\n"
            "4. **Conclusion:** End with a sentence of strategic impact. "
            "FORBIDDEN: Do not use 'In conclusion', 'It is important to note', or poetic language. Stick to the data."
        )
    },

    "continents": {
        "es": (
            "Analiza la distribución geográfica por continente:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas con tono analítico. "
            "1. **Dominancia:** ¿Qué continente lidera y por qué crees que lo hace?\n"
            "2. **Brecha:** Compara el líder con el segundo lugar. ¿Es un monopolio o hay competencia?\n"
            "3. **Riesgo:** Si un continente concentra la mayoría, indica el riesgo de dependencia de ese mercado.\n"
            "Sé directo. Nada de introducciones."
        ),
        "en": (
            "Analyze the geographic distribution by continent:\n\n{summary}\n\n"
            "Write 4 to 6 lines with an analytical tone. "
            "1. **Dominance:** Which continent leads and why do you think it does?\n"
            "2. **Gap:** Compare the leader with the second place. Is it a monopoly or is there competition?\n"
            "3. **Risk:** If one continent concentrates the majority, state the risk of dependency on that market.\n"
            "Be direct. No introductions."
        )
    },

    "countries": {
        "es": (
            "Analiza el Top de países por cantidad de canciones:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Top 3:** Menciona los países líderes con sus cifras exactas.\n"
            "2. **La Brecha:** ¿El primer lugar domina por mucho o hay una competencia reñida?\n"
            "3. **Long Tail:** Observa si el resto de países tienen muy pocas canciones. ¿Es un mercado concentrado o diverso?\n"
            "Termina con una implicación para la expansión internacional."
        ),
        "en": (
            "Analyze the Top countries by song count:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Top 3:** Mention the leading countries with their exact figures.\n"
            "2. **The Gap:** Does the first place dominate by a landslide or is there tight competition?\n"
            "3. **Long Tail:** Observe if the rest of the countries have very few songs. Is it a concentrated or diverse market?\n"
            "End with an implication for international expansion."
        )
    },

    "genre_analysis": {
        "es": (
            "Analiza el rendimiento de los géneros musicales:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **Volumen vs Fidelidad:** Menciona el género más popular. Luego, identifica el género con el engagement más alto.\n"
            "2. **El Insight:** ¿El género más escuchado es también el más querido? Si no es así, explica qué revela esto (ej. música de fondo vs. nichos apasionados).\n"
            "3. **Estrategia:** ¿Qué género ofrece la mejor oportunidad de conexión profunda?\n"
            "Sin relleno."
        ),
        "en": (
            "Analyze the performance of music genres:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **Volume vs Loyalty:** Mention the most popular genre. Then, identify the genre with the highest engagement.\n"
            "2. **The Insight:** Is the most-listened genre also the most-loved? If not, explain what this reveals (e.g., background music vs. passionate niches).\n"
            "3. **Strategy:** Which genre offers the best opportunity for deep connection?\n"
            "No fluff."
        )
    },

    "top_songs": {
        "es": (
            "Analiza el ranking de canciones de la semana:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **Los Protagonistas:** Nombra las canciones o artistas que dominan en vistas y en likes.\n"
            "2. **La Anomalía:** Busca un 'hit de nicho'. ¿Hay alguna canción con muchas menos vistas pero un engagement altísimo? Destácala.\n"
            "3. **Conclusión:** ¿El éxito de esta semana es por masividad o por fidelidad?\n"
            "Sé directo con los nombres propios."
        ),
        "en": (
            "Analyze this week's song ranking:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Protagonists:** Name the songs or artists dominating views and likes.\n"
            "2. **The Anomaly:** Look for a 'niche hit'. Is there a song with far fewer views but extremely high engagement? Highlight it.\n"
            "3. **Conclusion:** Is this week's success driven by mass appeal or loyalty?\n"
            "Be direct with proper names."
        )
    },

    "video_metrics": {
        "es": (
            "Analiza el rendimiento de los formatos de video:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Formato Ganador:** Menciona si los videos Oficiales, Lyric o Live lideran en vistas y en engagement.\n"
            "2. **Duración:** Basado en los datos de duración, indica si los videos son cortos o largos y qué implica para la retención de la audiencia.\n"
            "3. **Canal:** Concluye qué tipo de canal domina el mercado.\n"
            "Enfócate en la estrategia de producción."
        ),
        "en": (
            "Analyze the performance of video formats:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Winning Format:** Mention whether Official, Lyric, or Live videos lead in views and engagement.\n"
            "2. **Duration:** Based on duration data, state if videos are short or long and what it implies for audience retention.\n"
            "3. **Channel:** Conclude which channel type dominates the market.\n"
            "Focus on production strategy."
        )
    },

    "temporal_analysis": {
        "es": (
            "Analiza la evolución temporal por trimestres:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **Picos:** Identifica el trimestre con más lanzamientos y el de más vistas.\n"
            "2. **Estacionalidad:** Explica si hay un patrón claro (ej. lanzamientos de verano, campañas de fin de año).\n"
            "3. **Engagement:** ¿La fidelidad de la audiencia se mantiene estable o varía con el tiempo?\n"
            "Ve al grano."
        ),
        "en": (
            "Analyze the temporal evolution by quarters:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **Peaks:** Identify the quarter with the most releases and the one with the most views.\n"
            "2. **Seasonality:** Explain if there's a clear pattern (e.g., summer releases, year-end campaigns).\n"
            "3. **Engagement:** Does audience loyalty remain stable or fluctuate over time?\n"
            "Get to the point."
        )
    },

    "collaborations": {
        "es": (
            "Analiza el impacto de las colaboraciones:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **Vistas vs Engagement:** Responde: ¿las colaboraciones generan más vistas o más engagement que los solistas?\n"
            "2. **Escalabilidad:** Observa si a mayor cantidad de artistas, el rendimiento sube o baja.\n"
            "3. **Recomendación:** Termina con una recomendación de una línea: ¿conviene colaborar para masificar o para fidelizar? Sé analítico."
        ),
        "en": (
            "Analyze the impact of collaborations:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **Views vs Engagement:** Answer: Do collaborations generate more views or more engagement than solo artists?\n"
            "2. **Scalability:** Observe if performance goes up or down with more artists.\n"
            "3. **Recommendation:** End with a one-line recommendation: Is it better to collaborate for mass reach or loyalty? Be analytical."
        )
    }
}


class DeepSeekWriter:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.api_url = "https://api.deepseek.com/v1/chat/completions"

    def polish(self, summary: str, language: str = "es") -> tuple[str, int]:
        """
        Polish the raw summary using DeepSeek.
        
        Parameters
        ----------
        summary : str
            The raw summary generated by Groq or Gemma.
        language : str
            "es" or "en".

        Returns
        -------
        tuple[str, int]
            (final_text, tokens_used)
        """
        if not summary:
            return "", 0

        if not self.api_key:
            print("   [Writer] DeepSeek API key not found. Using raw summary.")
            return summary, 0

        prompt = WRITER_PROMPTS.get(language, WRITER_PROMPTS["es"]).format(summary=summary)

        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "You are an expert music journalist."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.6,
                    "max_tokens": 250
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            final_text = data["choices"][0]["message"]["content"].strip()
            tokens_used = data.get("usage", {}).get("total_tokens", 0)
            
            return final_text, tokens_used
            
        except Exception as e:
            print(f"   [Writer] DeepSeek failed: {e}")
            # Fallback: devolver el resumen crudo para no dejar el reporte sin análisis
            print("   [Writer] Falling back to the raw summary.")
            return summary, 0
