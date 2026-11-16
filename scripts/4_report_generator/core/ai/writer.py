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
- Fallback: if all small models fail, analyze the raw table directly.

Notes
-----
- DeepSeek does NOT calculate. It only writes. The numbers and insights
  come strictly from the `summary` provided by the small models.
- If the API key is missing or the call fails, it returns the original
  summary so the report is never left empty.
- The `WRITER_PROMPTS` dictionary is keyed by `section_id`. It includes
  the 21 subsection prompts plus the `introduction` and `conclusion`.
- The `polish_from_table` method is a fallback used when all small models
  (Groq, Google, Meta) fail. It asks DeepSeek to analyze the raw table.
- Every prompt produces a SINGLE PARAGRAPH. No headers, no numbering,
  no bullet points, no section labels. This is enforced both in the
  prompt and in the reinforced system message (`_build_system_message`).
- Prompts accept optional `{context}` (week label + total songs) and
  always receive `{summary}`. When `period_label` is not provided, the
  context block is omitted and the prompt still works.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import os
import requests

# ============================================================================
# BANNED PHRASES (per language)
# ============================================================================
# These phrases are forbidden in ALL outputs. They are injected into the
# system message and act as a global blacklist. Add to this list whenever
# a new generic phrase shows up in the outputs.
_BANNED_PHRASES = {
    "es": [
        "en conclusión",
        "es importante destacar",
        "cabe mencionar",
        "los números no mienten",
        "detrás de cada reproducción",
        "la interpretación está a la vista",
        "hegemonía geográfica",
        "diásporas masivas",
        "economías con poblaciones jóvenes",
        "esto sugiere que",
        "esto indica que",
        "esto revela que",
    ],
    "en": [
        "in conclusion",
        "it is important to note",
        "it is worth mentioning",
        "the numbers don't lie",
        "behind every play",
        "the interpretation is on the table",
        "geographic hegemony",
        "massive diasporas",
        "young populations",
        "this suggests that",
        "this indicates that",
        "this reveals that",
    ],
}

# ============================================================================
# MAX TOKENS
# ============================================================================
# Intro and conclusion need more room than the individual sections.
_MAX_TOKENS_OVERRIDE = {
    "introduction": 1200,
    "conclusion": 1500,
}
_DEFAULT_MAX_TOKENS = 1000


# ============================================================================
# HELPERS
# ============================================================================
def _build_system_message(language: str) -> str:
    """
    Build the reinforced system message that applies to every section.

    It forbids headers, numbering, bullet points, section labels, Yes/No
    answers and the phrases in `_BANNED_PHRASES`. This is the safety net
    that keeps the output consistent even if an individual prompt slips.
    """
    banned = ", ".join(_BANNED_PHRASES.get(language, _BANNED_PHRASES["es"]))
    if language == "en":
        return (
            "You are a music data analyst writing for an executive at a record label. "
            "You ALWAYS write in flowing prose, in a single paragraph. "
            "You NEVER use headers, numbering, bullet points, or section labels "
            "(like 'Context:', 'Conclusion:', 'Insight:', 'The Winner:', 'The Gap:'). "
            "You NEVER respond with 'Yes' or 'No' to a question: you write in affirmative. "
            "You NEVER use these phrases: " + banned + ". "
            "Your output is always a single analytical paragraph."
        )
    return (
        "Eres un analista de datos musicales que escribe para un ejecutivo de un sello "
        "discográfico. Escribes SIEMPRE en prosa fluida, en un solo párrafo. "
        "NUNCA usas encabezados, numeración, viñetas ni etiquetas de sección "
        "(como 'Contexto:', 'Conclusión:', 'Insight:', 'El Ganador:', 'La Brecha:'). "
        "NUNCA respondes con 'Sí' o 'No' a una pregunta: redactas en afirmativo. "
        "NUNCA usas estas frases: " + banned + ". "
        "Tu salida es siempre un único párrafo de análisis ejecutivo."
    )


def _build_context(language: str, period_label: str, total_songs: int) -> str:
    """
    Build the context block that anchors the analysis in the period.

    Returns an empty string if `period_label` is not provided, so the
    prompts remain backward compatible with callers that don't pass it.
    """
    if not period_label:
        return ""
    if language == "en":
        return f"Context: week {period_label}, {total_songs} songs in the global chart.\n\n"
    return f"Contexto: semana {period_label}, {total_songs} canciones en el chart global.\n\n"


# ============================================================================
# PROMPT TEMPLATES
# ============================================================================
# Every prompt follows the same pattern:
#   {context}{summary}\n\n
#   "Write a SINGLE PARAGRAPH of X-Y words in flowing prose. "
#   "NO headers, NO numbering, NO bullet points, "
#   "NO section labels, NO 'Yes'/'No' answers. "
#   "It is a flowing paragraph..."
#   "Cover, without making it explicit: - point 1 - point 2 - point 3"
#   "Use proper names when applicable. Do not speculate about causes..."
#   "Start directly with [something specific]."
# ============================================================================
WRITER_PROMPTS = {
    # ========================================================================
    # INTRODUCTION (receives the full text of all sections)
    # ========================================================================
    "introduction": {
        "es": (
            "{context}"
            "A continuación, los análisis de todas las secciones del reporte:\n\n"
            "{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 150-200 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas de sección, NO respondas con 'Sí'/'No'. "
            "Es un párrafo corrido, como la apertura de un informe ejecutivo.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El tamaño y alcance del catálogo (países, géneros, canciones).\n"
            "- El género dominante y el país líder, con cifras exactas.\n"
            "- La tendencia temporal más notable.\n"
            "- Una frase final que invite a leer el resto del reporte.\n\n"
            "Usa los nombres propios cuando aplique. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el dato o con el nombre del género dominante."
        ),
        "en": (
            "{context}"
            "Below are the analyses of all sections of the report:\n\n"
            "{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 150-200 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO section labels, NO 'Yes'/'No' answers. "
            "It is a flowing paragraph, like the opening of an executive report.\n\n"
            "Cover, without making it explicit:\n"
            "- The size and reach of the catalog (countries, genres, songs).\n"
            "- The dominant genre and the leading country, with exact figures.\n"
            "- The most notable temporal trend.\n"
            "- A closing sentence that invites the reader to go through the report.\n\n"
            "Use proper names when applicable. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the data point or with the name of the dominant genre."
        ),
    },

    # ========================================================================
    # CONCLUSION (receives the full text of all sections)
    # ========================================================================
    "conclusion": {
        "es": (
            "{context}"
            "A continuación, los análisis de todas las secciones del reporte:\n\n"
            "{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 250-300 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas de sección, NO respondas con 'Sí'/'No'. "
            "NO repitas literalmente las frases de las secciones: sintetiza, "
            "conecta los hallazgos entre sí y añade una interpretación que no "
            "esté explícita en las secciones individuales.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El género dominante y su cantidad exacta de canciones.\n"
            "- El país líder en cantidad de canciones y su cifra exacta.\n"
            "- El país líder en likes y su cifra exacta.\n"
            "- La brecha entre el primer y segundo país (en canciones y en likes).\n"
            "- La tendencia temporal más notable (ej. el trimestre con más lanzamientos).\n"
            "- El impacto de las colaboraciones (vistas vs engagement).\n"
            "- Una implicación estratégica concreta para la industria al cierre.\n\n"
            "Usa los números exactos del reporte. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el hallazgo más contundente."
        ),
        "en": (
            "{context}"
            "Below are the analyses of all sections of the report:\n\n"
            "{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 250-300 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO section labels, NO 'Yes'/'No' answers. "
            "Do NOT literally repeat the phrases from the sections: synthesize, "
            "connect the findings to each other and add an interpretation that "
            "is not explicit in the individual sections.\n\n"
            "Cover, without making it explicit:\n"
            "- The dominant genre and its exact song count.\n"
            "- The leading country in song count and its exact figure.\n"
            "- The leading country in likes and its exact figure.\n"
            "- The gap between the first and second country (in songs and likes).\n"
            "- The most notable temporal trend (e.g. the quarter with the most releases).\n"
            "- The impact of collaborations (views vs engagement).\n"
            "- A concrete strategic implication for the industry at the close.\n\n"
            "Use the exact numbers from the report. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the most striking finding."
        ),
    },

    # ========================================================================
    # SECTION 2: General Statistics
    # ========================================================================
    "general_stats": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'Contexto:' o 'Benchmark:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido, "
            "como el análisis de un informe ejecutivo.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El tamaño del catálogo (canciones, países, géneros).\n"
            "- El engagement frente al estándar de la industria (3%-8%): "
            "indica si la audiencia es hiper-fiel o pasiva, apoyándote en el dato.\n"
            "- Una frase final de impacto estratégico que conecte los datos con una decisión.\n\n"
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el dato principal (el total de canciones o el engagement)."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'Context:' or 'Benchmark:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph, "
            "like the analysis of an executive report.\n\n"
            "Cover, without making it explicit:\n"
            "- The size of the catalog (songs, countries, genres).\n"
            "- The engagement versus the industry standard (3%-8%): "
            "state whether the audience is hyper-loyal or passive, backed by the data.\n"
            "- A closing sentence of strategic impact that links data to a decision.\n\n"
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the main data point (total songs or engagement)."
        ),
    },

    # ========================================================================
    # SECTION 3: Continents
    # ========================================================================
    "continents": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'Dominancia:' o 'Riesgo:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El continente que lidera y su cifra exacta.\n"
            "- La brecha entre el primero y el segundo.\n"
            "- Si un continente concentra la mayoría, el riesgo de dependencia de ese mercado.\n\n"
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el nombre del continente líder o con su cifra."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'Dominance:' or 'Risk:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The leading continent and its exact figure.\n"
            "- The gap between first and second place.\n"
            "- If one continent concentrates the majority, the risk of dependency on that market.\n\n"
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the name of the leading continent or with its figure."
        ),
    },

    # ========================================================================
    # SECTION 4: Countries
    # ========================================================================
    "countries_by_songs": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Top 3:', 'La Brecha:' o 'Long Tail:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- Los países líderes con sus cifras exactas.\n"
            "- Si el primer lugar domina con holgura o si hay competencia reñida.\n"
            "- Si el mercado está concentrado o si hay una larga cola de países con muy pocas canciones.\n"
            "- Una implicación para la expansión internacional al cierre.\n\n"
            "Usa los nombres propios de los países. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el nombre del país líder o con su cifra."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Top 3:', 'The Gap:' or 'Long Tail:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The leading countries with their exact figures.\n"
            "- Whether the first place dominates by a landslide or there is tight competition.\n"
            "- Whether the market is concentrated or if there is a long tail of countries with very few songs.\n"
            "- An implication for international expansion at the close.\n\n"
            "Use country names. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the name of the leading country or with its figure."
        ),
    },

    "countries_by_likes": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Top 3:', 'Brecha:' o 'Insight:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- Los países líderes con sus cifras exactas de likes.\n"
            "- La brecha entre el primero y el segundo.\n"
            "- Si el orden coincide con el ranking por canciones; si no coincide, "
            "qué revela sobre la fidelidad de la audiencia.\n\n"
            "Usa los nombres propios de los países. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el nombre del país líder o con su cifra de likes."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Top 3:', 'Gap:' or 'Insight:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The leading countries with their exact likes figures.\n"
            "- The gap between first and second place.\n"
            "- Whether the order matches the song-count ranking; if it does not, "
            "what that reveals about audience loyalty.\n\n"
            "Use country names. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the name of the leading country or with its likes figure."
        ),
    },

    "countries_top_songs": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'Protagonistas:', 'Patrón:' o 'Conclusión:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- La canción más vista en cada uno de los países del Top 5, con sus nombres propios.\n"
            "- Si hay un artista o género que se repite entre países, o si cada país "
            "tiene su propio hit local.\n"
            "- Si el éxito es global (un hit que funciona en todos lados) o local.\n\n"
            "Usa los nombres propios de canciones, artistas y países. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el nombre de la primera canción o del primer país."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'Protagonists:', 'Pattern:' or 'Conclusion:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The most-viewed song in each of the Top 5 countries, with proper names.\n"
            "- Whether an artist or genre repeats across countries, or if each country "
            "has its own local hit.\n"
            "- Whether the success is global (one hit that works everywhere) or local.\n\n"
            "Use the names of songs, artists and countries. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the name of the first song or of the first country."
        ),
    },

    # ========================================================================
    # SECTION 5: Genre Analysis
    # ========================================================================
    "genre_stats": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Género Dominante:' o 'Diversidad:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El género con más canciones y su cifra exacta.\n"
            "- Si el catálogo está concentrado en pocos géneros o hay una distribución equilibrada.\n"
            "- Si hay algún género con pocas canciones que merezca la pena explorar.\n\n"
            "Usa los nombres propios de los géneros. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el nombre del género dominante o con su cifra."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Dominant Genre:' or 'Diversity:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The genre with the most songs and its exact figure.\n"
            "- Whether the catalog is concentrated in few genres or has a balanced distribution.\n"
            "- Whether any genre with few songs is worth exploring.\n\n"
            "Use genre names. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the name of the dominant genre or with its figure."
        ),
    },

    "genre_treemap": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Bloque Más Grande:' o 'Concentración:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El género que ocupa el mayor bloque en el treemap.\n"
            "- Si los tres primeros géneros suman más del 50% del catálogo, "
            "o si hay una larga cola de géneros minoritarios.\n"
            "- Qué dice esto sobre la estrategia de contenido (nicho vs masivo).\n\n"
            "Usa los nombres propios de los géneros. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el nombre del género que ocupa el mayor bloque."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Biggest Block:' or 'Concentration:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The genre that occupies the largest block in the treemap.\n"
            "- Whether the top 3 genres add up to more than 50% of the catalog, "
            "or if there is a long tail of minority genres.\n"
            "- What this says about the content strategy (niche vs mass).\n\n"
            "Use genre names. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the name of the genre that occupies the largest block."
        ),
    },

    "genre_engagement": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Rey del Engagement:' o 'Estrategia:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El género con la tasa de engagement más alta y su porcentaje exacto.\n"
            "- Si coincide o no con el género más popular por volumen, "
            "y qué revela ese contraste.\n"
            "- Qué género ofrece la mejor oportunidad de conexión profunda.\n\n"
            "Usa los nombres propios de los géneros. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el nombre del género con mayor engagement o con su porcentaje."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Engagement King:' or 'Strategy:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The genre with the highest engagement rate and its exact percentage.\n"
            "- Whether it matches or not the most popular genre by volume, "
            "and what that contrast reveals.\n"
            "- Which genre offers the best opportunity for deep connection.\n\n"
            "Use genre names. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the name of the highest-engagement genre or with its percentage."
        ),
    },

    # ========================================================================
    # SECTION 6: Song Metrics
    # ========================================================================
    "top_songs_by_views": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'Los Protagonistas:', 'La Anomalía:' o 'Conclusión:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- Las canciones o artistas que lideran en vistas, con sus cifras exactas.\n"
            "- Si hay una canción con muchas menos vistas pero engagement atípicamente alto "
            "(o viceversa), destácala como anomalía.\n"
            "- Una frase final que responda si el éxito de la semana es por masividad o por fidelidad.\n\n"
            "Usa los nombres propios de las canciones y artistas. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el nombre de la canción líder o con su cifra."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Protagonists:', 'The Anomaly:' or 'Conclusion:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The songs or artists dominating views, with their exact figures.\n"
            "- Whether any song has far fewer views but an atypically high engagement "
            "(or vice versa); highlight it as an anomaly.\n"
            "- A closing sentence that answers whether this week's success is mass appeal or loyalty.\n\n"
            "Use the names of songs and artists. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the name of the leading song or with its figure."
        ),
    },

    "top_songs_by_likes": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'Los Protagonistas:', 'Comparación:' o 'Insight:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- Las canciones o artistas que lideran en likes, con sus cifras exactas.\n"
            "- Si el Top de likes coincide o no con el Top de vistas; si no coincide, "
            "qué revela sobre la fidelidad de la audiencia.\n"
            "- Si hay una canción con muchos likes pero pocas vistas (o engagement "
            "atípicamente alto), destácala como hit de nicho.\n\n"
            "Usa los nombres propios de las canciones y artistas. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el nombre de la canción líder o con su cifra de likes."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Protagonists:', 'Comparison:' or 'Insight:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The songs or artists dominating likes, with their exact figures.\n"
            "- Whether the likes Top matches or not the views Top; if it does not, "
            "what that reveals about audience loyalty.\n"
            "- Whether any song has many likes but few views (or atypically high "
            "engagement); highlight it as a niche hit.\n\n"
            "Use the names of songs and artists. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the name of the leading song or with its likes figure."
        ),
    },

    "top_songs_by_engagement": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Hit de Nicho:', 'La Paradoja:' o 'Conclusión:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- La canción con la tasa de engagement más alta y su porcentaje exacto.\n"
            "- Si esa canción también aparece (o no) en el Top de vistas, y qué revela "
            "ese contraste sobre el tipo de audiencia (masiva vs de nicho).\n"
            "- Una frase final que responda si el éxito de la semana se mide por masividad "
            "o por conexión profunda.\n\n"
            "Usa los nombres propios de las canciones y artistas. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el nombre de la canción líder o con su porcentaje."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Niche Hit:', 'The Paradox:' or 'Conclusion:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The song with the highest engagement rate and its exact percentage.\n"
            "- Whether that song also appears (or not) in the views Top, and what that "
            "contrast reveals about the type of audience (mass vs niche).\n"
            "- A closing sentence that answers whether this week's success is measured by "
            "mass appeal or by deep connection.\n\n"
            "Use the names of songs and artists. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the name of the leading song or with its percentage."
        ),
    },

    # ========================================================================
    # SECTION 7: Video Metrics
    # ========================================================================
    "video_summary": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Formato Dominante:' o 'El Formato Minoritario:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- La categoría (Official, Lyric, Live, Collaborations) con el mayor porcentaje.\n"
            "- La categoría con menos presencia y si es una oportunidad de mercado.\n"
            "- Si el catálogo está equilibrado o si hay una dependencia clara de un formato.\n\n"
            "Usa los nombres de las categorías. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con la categoría dominante o con su porcentaje."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Dominant Format:' or 'The Minority Format:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The category (Official, Lyric, Live, Collaborations) with the highest percentage.\n"
            "- The category with the least presence and whether it is a market opportunity.\n"
            "- Whether the catalog is balanced or if there is a clear dependency on one format.\n\n"
            "Use the category names. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the dominant category or with its percentage."
        ),
    },

    "video_views": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Formato Ganador:' o 'La Brecha:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El tipo de video (Official, Lyric, Live) que lidera en vistas promedio, con su cifra.\n"
            "- La brecha entre el primero y el segundo.\n"
            "- Si el formato con más vistas es también el que más se produce; si no, "
            "indica la oportunidad.\n\n"
            "Usa los nombres de los tipos de video. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el tipo de video líder o con su cifra."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Winning Format:' or 'Gap:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The video type (Official, Lyric, Live) that leads in average views, with its figure.\n"
            "- The gap between first and second place.\n"
            "- Whether the format with the most views is also the one produced the most; if not, "
            "state the opportunity.\n\n"
            "Use the video type names. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the leading video type or with its figure."
        ),
    },

    "video_engagement": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Formato Más Querido:' o 'La Paradoja:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El tipo de video con el engagement promedio más alto, con su cifra.\n"
            "- Si coincide o no con el que más vistas genera; si no coincide, "
            "qué revela ese contraste.\n"
            "- Qué formato ofrece la mejor oportunidad de conexión profunda con la audiencia.\n\n"
            "Usa los nombres de los tipos de video. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el tipo de video con mayor engagement o con su cifra."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Most Loved Format:' or 'The Paradox:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The video type with the highest average engagement, with its figure.\n"
            "- Whether it matches or not the one with the most views; if it does not, "
            "what that contrast reveals.\n"
            "- Which format offers the best opportunity for deep connection with the audience.\n\n"
            "Use the video type names. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the highest-engagement video type or with its figure."
        ),
    },

    "video_duration": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'La Duración Promedio:' o 'El Rango:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- La duración media y la mediana (en minutos), con sus cifras.\n"
            "- Si los videos son cortos (menos de 3 min) o largos (más de 5 min), "
            "y si hay mucha diferencia entre el mínimo y el máximo.\n"
            "- Qué implica esto para la retención de la audiencia (formato single o álbum).\n\n"
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con la duración promedio o con la mediana."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Average Duration:' or 'The Range:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The mean and median duration (in minutes), with their figures.\n"
            "- Whether videos are short (under 3 min) or long (over 5 min), "
            "and whether there is a big difference between the minimum and maximum.\n"
            "- What this implies for audience retention (single vs album format).\n\n"
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the average duration or with the median."
        ),
    },

    "video_channels": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Canal Dominante:' o 'Diversidad:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El tipo de canal (Artist, VEVO, Topic, etc.) con más canciones y su porcentaje.\n"
            "- Si hay muchos tipos de canal o si el catálogo está concentrado en uno o dos.\n"
            "- Qué dice esto sobre la estrategia de distribución (independiente vs grandes sellos).\n\n"
            "Usa los nombres de los tipos de canal. "
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el tipo de canal dominante o con su porcentaje."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Dominant Channel:' or 'Diversity:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The channel type (Artist, VEVO, Topic, etc.) with the most songs and its percentage.\n"
            "- Whether there are many channel types or if the catalog is concentrated in one or two.\n"
            "- What this says about the distribution strategy (independent vs major labels).\n\n"
            "Use the channel type names. "
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the dominant channel type or with its percentage."
        ),
    },

    # ========================================================================
    # SECTION 8: Temporal Analysis
    # ========================================================================
    "temporal_views": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Pico:' o 'La Tendencia:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El trimestre con más vistas totales y su cifra exacta.\n"
            "- Si las vistas suben, bajan o se mantienen estables a lo largo de los trimestres.\n"
            "- Si hay un patrón de estacionalidad (lanzamientos de verano, fin de año, etc.).\n\n"
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el trimestre pico o con su cifra."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Peak:' or 'The Trend:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The quarter with the most total views and its exact figure.\n"
            "- Whether views rise, fall, or remain stable across quarters.\n"
            "- Whether there is a seasonality pattern (summer releases, year-end, etc.).\n\n"
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the peak quarter or with its figure."
        ),
    },

    "temporal_engagement": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Pico:' o 'La Tendencia:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El trimestre con el engagement promedio más alto y su porcentaje exacto.\n"
            "- Si la fidelidad de la audiencia se mantiene estable o varía con el tiempo.\n"
            "- Si el trimestre con más vistas es también el de más engagement; si no, "
            "qué revela eso.\n\n"
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el trimestre de mayor engagement o con su porcentaje."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Peak:' or 'The Trend:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The quarter with the highest average engagement and its exact percentage.\n"
            "- Whether audience loyalty remains stable or fluctuates over time.\n"
            "- Whether the quarter with the most views is also the one with the most engagement; "
            "if not, what that reveals.\n\n"
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the highest-engagement quarter or with its percentage."
        ),
    },

    "temporal_releases": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Trimestre Más Activo:' o 'La Distribución:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- El trimestre con más lanzamientos y su cifra exacta.\n"
            "- Si los lanzamientos están concentrados en un trimestre o distribuidos "
            "de forma equilibrada.\n"
            "- Qué dice esto sobre la estrategia de lanzamiento (campaña de verano, "
            "fin de año, etc.).\n\n"
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con el trimestre más activo o con su cifra."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Most Active Quarter:' or 'The Distribution:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- The quarter with the most releases and its exact figure.\n"
            "- Whether releases are concentrated in one quarter or evenly distributed.\n"
            "- What this says about the release strategy (summer campaign, year-end, etc.).\n\n"
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the most active quarter or with its figure."
        ),
    },

    # ========================================================================
    # SECTION 9: Collaborations
    # ========================================================================
    "collab_views": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Ganador:' o 'La Brecha:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- Si las colaboraciones o los solistas generan más vistas promedio, "
            "con las cifras exactas de ambos grupos.\n"
            "- Si esa diferencia es significativa o marginal, y qué implica para "
            "la estrategia de colaboración.\n"
            "- Una frase final que conecte los datos con una decisión concreta.\n\n"
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con la comparación o con la cifra."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Winner:' or 'The Gap:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- Whether collaborations or solo artists generate more average views, "
            "with the exact figures for both groups.\n"
            "- Whether that difference is significant or marginal, and what it implies "
            "for the collaboration strategy.\n"
            "- A closing sentence that links the data to a concrete decision.\n\n"
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the comparison or with the figure."
        ),
    },

    "collab_engagement": {
        "es": (
            "{context}{summary}\n\n"
            "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
            "NO uses encabezados, NO numeres, NO uses viñetas, "
            "NO uses etiquetas como 'El Ganador:' o 'La Paradoja:', "
            "NO respondas con 'Sí'/'No'. Es un párrafo corrido.\n\n"
            "Cubre, sin señalarlo explícitamente:\n"
            "- Si las colaboraciones o los solistas generan más engagement promedio, "
            "con las cifras exactas de ambos grupos.\n"
            "- Si coincide o no con el grupo que genera más vistas; si no coincide, "
            "qué revela ese contraste.\n"
            "- Una recomendación final sobre si conviene colaborar para fidelizar "
            "o para masificar.\n\n"
            "No especules sobre causas que no estén en los datos.\n\n"
            "Empieza directamente con la comparación o con la cifra."
        ),
        "en": (
            "{context}{summary}\n\n"
            "Write a SINGLE PARAGRAPH of 90-130 words in flowing prose. "
            "NO headers, NO numbering, NO bullet points, "
            "NO labels like 'The Winner:' or 'The Paradox:', "
            "NO 'Yes'/'No' answers. It is a flowing paragraph.\n\n"
            "Cover, without making it explicit:\n"
            "- Whether collaborations or solo artists generate more average engagement, "
            "with the exact figures for both groups.\n"
            "- Whether it matches or not the group that generates the most views; if it "
            "does not, what that contrast reveals.\n"
            "- A closing recommendation on whether to collaborate for loyalty or for mass reach.\n\n"
            "Do not speculate about causes that are not in the data.\n\n"
            "Start directly with the comparison or with the figure."
        ),
    },
}


class DeepSeekWriter:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.api_url = "https://api.deepseek.com/v1/chat/completions"

    # ========================================================================
    # PUBLIC API
    # ========================================================================
    def polish(
        self,
        section_id: str,
        summary: str,
        language: str = "es",
        period_label: str = "",
        total_songs: int = 0,
    ) -> tuple[str, int]:
        """
        Polish the raw summary using DeepSeek.

        Parameters
        ----------
        section_id : str
            The report section identifier (e.g., 'general_stats',
            'introduction', 'conclusion').
        summary : str
            The raw summary generated by Groq, Gemma, or Muse Spark.
        language : str
            "es" or "en".
        period_label : str
            Optional ISO week label (e.g., "2026-W46"). When provided, it is
            injected into the prompt as context. When empty, the context block
            is omitted and the prompt works unchanged.
        total_songs : int
            Optional total number of songs in the chart. Only used when
            `period_label` is also provided.

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

        section_prompts = WRITER_PROMPTS.get(section_id, {})
        prompt_template = section_prompts.get(language, section_prompts.get("es", ""))

        if not prompt_template:
            print(
                f"   [Writer] Warning: No prompt found for section '{section_id}' "
                f"and language '{language}'. Using raw summary."
            )
            return summary, 0

        context = _build_context(language, period_label, total_songs)
        prompt = prompt_template.format(context=context, summary=summary)

        max_tokens = _MAX_TOKENS_OVERRIDE.get(section_id, _DEFAULT_MAX_TOKENS)
        system_message = _build_system_message(language)

        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.6,
                    "max_tokens": max_tokens,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            final_text = data["choices"][0]["message"]["content"].strip()
            tokens_used = data.get("usage", {}).get("total_tokens", 0)

            return final_text, tokens_used

        except Exception as e:
            print(f"   [Writer] DeepSeek failed: {e}")
            print("   [Writer] Falling back to the raw summary.")
            return summary, 0

    def polish_from_table(
        self,
        section_id: str,
        table_md: str,
        language: str = "es",
        period_label: str = "",
        total_songs: int = 0,
    ) -> tuple[str, int]:
        """
        Fallback method: ask DeepSeek to analyze the raw table directly.
        Used when all small summarizer models fail.
        """
        if not table_md or not self.api_key:
            return "", 0

        context = _build_context(language, period_label, total_songs)

        if language == "en":
            prompt = (
                f"{context}"
                "Analyze the following table:\n\n"
                f"{table_md}\n\n"
                "Write a SINGLE PARAGRAPH of 100-150 words in flowing prose. "
                "NO headers, NO numbering, NO bullet points, NO section labels. "
                "Mention the highest data point, the second and third, and highlight "
                "any anomaly or notable trend, with exact figures. "
                "Do not invent data. Do not speculate about causes that are not in the table."
            )
        else:
            prompt = (
                f"{context}"
                "Analiza la siguiente tabla:\n\n"
                f"{table_md}\n\n"
                "Escribe UN SOLO PÁRRAFO de 90-130 palabras en prosa fluida. "
                "NO uses encabezados, NO numeres, NO uses viñetas, NO uses etiquetas de sección. "
                "Menciona el dato más alto, el segundo y el tercero, y destaca cualquier "
                "anomalía o tendencia notable, con cifras exactas. "
                "No inventes datos. No especules sobre causas que no estén en la tabla."
            )

        system_message = _build_system_message(language)

        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 1200,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            final_text = data["choices"][0]["message"]["content"].strip()
            tokens_used = data.get("usage", {}).get("total_tokens", 0)

            return final_text, tokens_used

        except Exception as e:
            print(f"   [Writer] DeepSeek fallback failed: {e}")
            return "", 0
