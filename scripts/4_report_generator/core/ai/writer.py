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
- The `WRITER_PROMPTS` dictionary is keyed by `section_id`. It includes
  the 21 subsection prompts plus the `introduction` and `conclusion`.

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
    # ========================================================================
    # INTRODUCTION (injected at the beginning of the notebook)
    # ========================================================================
    "introduction": {
        "es": (
            "Actúa como un editor de una revista de análisis musical. "
            "Escribe una introducción de 6 a 8 líneas para un reporte semanal de YouTube Music Charts. "
            "El objetivo es invitar al lector a sumergirse en los datos. "
            "Menciona que el reporte cubre {period_label} y que analiza {total_songs} canciones de {total_countries} países y {total_genres} géneros. "
            "Usa un tono periodístico, atractivo y directo. "
            "PROHIBIDO: No uses frases como 'En este reporte...' o 'A continuación...'. Ve directo al tema."
        ),
        "en": (
            "Act as an editor of a music analysis magazine. "
            "Write a 6 to 8-line introduction for a weekly YouTube Music Charts report. "
            "The goal is to invite the reader to dive into the data. "
            "Mention that the report covers {period_label} and analyzes {total_songs} songs from {total_countries} countries and {total_genres} genres. "
            "Use a journalistic, engaging, and direct tone. "
            "FORBIDDEN: Do not use phrases like 'In this report...' or 'Below...'. Get straight to the point."
        )
    },

    # ========================================================================
    # CONCLUSION (injected at the end of the notebook)
    # ========================================================================
    "conclusion": {
        "es": (
            "Actúa como un analista senior de la industria musical. "
            "Basado en todos los análisis de este reporte, escribe una conclusión de 8 a 10 líneas. "
            "NO es un resumen. Es una síntesis de los hallazgos principales. "
            "Identifica 3 o 4 descubrimientos clave (ej. el género dominante, el país líder, la tendencia temporal más notable, el impacto de las colaboraciones). "
            "Conecta los hallazgos entre sí (ej. 'El dominio de Indian Pop se alinea con la concentración geográfica en Asia...'). "
            "Termina con una implicación estratégica para la industria. "
            "PROHIBIDO: No uses frases como 'En conclusión' o 'Para resumir'. Sé directo y analítico."
        ),
        "en": (
            "Act as a senior music industry analyst. "
            "Based on all the analyses in this report, write an 8 to 10-line conclusion. "
            "It is NOT a summary. It is a synthesis of the main findings. "
            "Identify 3 or 4 key discoveries (e.g., the dominant genre, the leading country, the most notable temporal trend, the impact of collaborations). "
            "Connect the findings to each other (e.g., 'The dominance of Indian Pop aligns with the geographic concentration in Asia...'). "
            "End with a strategic implication for the industry. "
            "FORBIDDEN: Do not use phrases like 'In conclusion' or 'To summarize'. Be direct and analytical."
        )
    },

    # ========================================================================
    # SECTION 2: General Statistics
    # ========================================================================
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

    # ========================================================================
    # SECTION 3: Continents
    # ========================================================================
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

    # ========================================================================
    # SECTION 4: Countries
    # ========================================================================
    "countries_by_songs": {
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

    "countries_by_likes": {
        "es": (
            "Analiza el Top de países por total de likes:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Top 3:** Menciona los países con más likes y sus cifras exactas.\n"
            "2. **Brecha:** Compara el 1º con el 2º. ¿Es una diferencia abismal o un empate técnico?\n"
            "3. **Insight:** ¿Coincide el ranking de likes con el de canciones? Si no, ¿qué revela esto sobre la fidelidad de la audiencia?\n"
            "Sé directo y analítico."
        ),
        "en": (
            "Analyze the Top countries by total likes:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Top 3:** Mention the countries with the most likes and their exact figures.\n"
            "2. **Gap:** Compare 1st with 2nd. Is it a huge difference or a technical tie?\n"
            "3. **Insight:** Does the likes ranking match the song count ranking? If not, what does this reveal about audience loyalty?\n"
            "Be direct and analytical."
        )
    },

    "countries_top_songs": {
        "es": (
            "Analiza las canciones más exitosas por país:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **Protagonistas:** Menciona la canción más vista en cada uno de los países del Top 5.\n"
            "2. **Patrón:** ¿Hay algún artista o género que se repita en varios países? ¿O cada país tiene su propio hit local?\n"
            "3. **Conclusión:** ¿El éxito es global (un hit que funciona en todos lados) o local (cada país tiene su favorito)?\n"
            "Sé directo con los nombres propios."
        ),
        "en": (
            "Analyze the top songs by country:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **Protagonists:** Mention the most-viewed song in each of the Top 5 countries.\n"
            "2. **Pattern:** Is there an artist or genre that repeats across countries? Or does each country have its own local hit?\n"
            "3. **Conclusion:** Is the success global (one hit that works everywhere) or local (each country has its favorite)?\n"
            "Be direct with proper names."
        )
    },

    # ========================================================================
    # SECTION 5: Genre Analysis
    # ========================================================================
    "genre_stats": {
        "es": (
            "Analiza la tabla de estadísticas por género:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Género Dominante:** Menciona el género con más canciones y su cifra exacta.\n"
            "2. **Diversidad:** ¿El catálogo está concentrado en pocos géneros o hay una distribución equilibrada?\n"
            "3. **Oportunidad:** ¿Hay algún género con pocas canciones pero que merezca la pena explorar?\n"
            "Ve al dato."
        ),
        "en": (
            "Analyze the genre statistics table:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Dominant Genre:** Mention the genre with the most songs and its exact figure.\n"
            "2. **Diversity:** Is the catalog concentrated in few genres or is there a balanced distribution?\n"
            "3. **Opportunity:** Is there any genre with few songs but worth exploring?\n"
            "Stick to the data."
        )
    },

    "genre_treemap": {
        "es": (
            "Analiza el treemap de distribución de géneros:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Bloque Más Grande:** Menciona el género que ocupa más espacio en el treemap.\n"
            "2. **Concentración:** ¿Los 3 primeros géneros suman más del 50% del catálogo? ¿O hay una larga cola de géneros minoritarios?\n"
            "3. **Implicación:** ¿Qué dice esto sobre la estrategia de contenido? ¿Es un catálogo de nicho o masivo?\n"
            "Sé analítico."
        ),
        "en": (
            "Analyze the genre distribution treemap:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Biggest Block:** Mention the genre that occupies the most space in the treemap.\n"
            "2. **Concentration:** Do the top 3 genres add up to more than 50% of the catalog? Or is there a long tail of minority genres?\n"
            "3. **Implication:** What does this say about the content strategy? Is it a niche or mass catalog?\n"
            "Be analytical."
        )
    },

    "genre_engagement": {
        "es": (
            "Analiza la tasa de engagement por género:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Rey del Engagement:** Menciona el género con la tasa más alta y su porcentaje exacto.\n"
            "2. **Comparación:** ¿Coincide con el género más popular (por volumen)? Si no es así, explica qué revela esto (ej. música de fondo vs. nichos apasionados).\n"
            "3. **Estrategia:** ¿Qué género ofrece la mejor oportunidad de conexión profunda?\n"
            "Sin relleno."
        ),
        "en": (
            "Analyze the engagement rate by genre:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Engagement King:** Mention the genre with the highest rate and its exact percentage.\n"
            "2. **Comparison:** Does it match the most popular genre (by volume)? If not, explain what this reveals (e.g., background music vs. passionate niches).\n"
            "3. **Strategy:** Which genre offers the best opportunity for deep connection?\n"
            "No fluff."
        )
    },

    # ========================================================================
    # SECTION 6: Song Metrics
    # ========================================================================
    "top_songs_by_views": {
        "es": (
            "Analiza el ranking de canciones por vistas:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **Los Protagonistas:** Nombra las canciones o artistas que dominan en vistas.\n"
            "2. **La Anomalía:** Busca un 'hit de nicho'. ¿Hay alguna canción con muchas menos vistas pero un engagement altísimo? Destácala.\n"
            "3. **Conclusión:** ¿El éxito de esta semana es por masividad o por fidelidad?\n"
            "Sé directo con los nombres propios."
        ),
        "en": (
            "Analyze the song ranking by views:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Protagonists:** Name the songs or artists dominating views.\n"
            "2. **The Anomaly:** Look for a 'niche hit'. Is there a song with far fewer views but extremely high engagement? Highlight it.\n"
            "3. **Conclusion:** Is this week's success driven by mass appeal or loyalty?\n"
            "Be direct with proper names."
        )
    },

    "top_songs_by_likes": {
        "es": (
            "Analiza el ranking de canciones por likes:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **Los Protagonistas:** Nombra las canciones o artistas que dominan en likes.\n"
            "2. **Comparación:** ¿Coincide el Top de likes con el Top de vistas? Si no es así, ¿qué revela esto sobre la fidelidad de la audiencia?\n"
            "3. **Insight:** ¿Hay alguna canción que tenga muchos likes pero pocas vistas? Eso indicaría un hit de nicho muy querido.\n"
            "Sé directo con los nombres propios."
        ),
        "en": (
            "Analyze the song ranking by likes:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Protagonists:** Name the songs or artists dominating likes.\n"
            "2. **Comparison:** Does the likes Top match the views Top? If not, what does this reveal about audience loyalty?\n"
            "3. **Insight:** Is there a song with many likes but few views? That would indicate a highly beloved niche hit.\n"
            "Be direct with proper names."
        )
    },

    "top_songs_by_engagement": {
        "es": (
            "Analiza el ranking de canciones por engagement:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Hit de Nicho:** Menciona la canción con la tasa de engagement más alta y su porcentaje.\n"
            "2. **La Paradoja:** ¿Esta canción también está en el Top de vistas? Si no es así, explica qué revela esto (ej. una canción muy querida por un nicho pero poco masiva).\n"
            "3. **Conclusión:** ¿El éxito de esta semana se mide por masividad o por conexión profunda?\n"
            "Sé directo con los nombres propios."
        ),
        "en": (
            "Analyze the song ranking by engagement:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Niche Hit:** Mention the song with the highest engagement rate and its percentage.\n"
            "2. **The Paradox:** Is this song also in the views Top? If not, explain what this reveals (e.g., a song loved by a niche but not massive).\n"
            "3. **Conclusion:** Is this week's success measured by mass appeal or deep connection?\n"
            "Be direct with proper names."
        )
    },

    # ========================================================================
    # SECTION 7: Video Metrics
    # ========================================================================
    "video_summary": {
        "es": (
            "Analiza el resumen de video (categorías y porcentajes):\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Formato Dominante:** Menciona qué categoría (Official, Lyric, Live, Collaborations) tiene el mayor porcentaje.\n"
            "2. **El Formato Minoritario:** ¿Cuál es el que menos presencia tiene? ¿Es una oportunidad de mercado?\n"
            "3. **Conclusión:** ¿El catálogo está equilibrado o hay una dependencia clara de un formato?\n"
            "Sé directo."
        ),
        "en": (
            "Analyze the video summary (categories and percentages):\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Dominant Format:** Mention which category (Official, Lyric, Live, Collaborations) has the highest percentage.\n"
            "2. **The Minority Format:** Which one has the least presence? Is it a market opportunity?\n"
            "3. **Conclusion:** Is the catalog balanced or is there a clear dependency on one format?\n"
            "Be direct."
        )
    },

    "video_views": {
        "es": (
            "Analiza las vistas por tipo de video:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Formato Ganador:** Menciona qué tipo (Official, Lyric, Live) lidera en vistas promedio.\n"
            "2. **La Brecha:** Compara el 1º con el 2º. ¿Es una diferencia abismal o un empate técnico?\n"
            "3. **Insight:** ¿El formato que más vistas genera es también el que más se produce? Si no es así, indica la oportunidad.\n"
            "Enfócate en la estrategia de producción."
        ),
        "en": (
            "Analyze views by video type:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Winning Format:** Mention which type (Official, Lyric, Live) leads in average views.\n"
            "2. **Gap:** Compare 1st with 2nd. Is it a huge difference or a technical tie?\n"
            "3. **Insight:** Is the format that generates the most views also the one that is produced the most? If not, state the opportunity.\n"
            "Focus on production strategy."
        )
    },

    "video_engagement": {
        "es": (
            "Analiza el engagement por tipo de video:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Formato Más Querido:** Menciona qué tipo de video tiene el engagement promedio más alto.\n"
            "2. **La Paradoja:** ¿Coincide con el que más vistas genera? Si no es así, explica qué revela esto (ej. los Lyric Videos generan menos vistas pero más conexión).\n"
            "3. **Conclusión:** ¿Qué formato ofrece la mejor oportunidad de conexión profunda con la audiencia?\n"
            "Sé directo."
        ),
        "en": (
            "Analyze engagement by video type:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Most Loved Format:** Mention which video type has the highest average engagement.\n"
            "2. **The Paradox:** Does it match the one with the most views? If not, explain what this reveals (e.g., Lyric Videos generate fewer views but more connection).\n"
            "3. **Conclusion:** Which format offers the best opportunity for deep connection with the audience?\n"
            "Be direct."
        )
    },

    "video_duration": {
        "es": (
            "Analiza la duración de los videos:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **La Duración Promedio:** Menciona la duración media y la mediana (en minutos).\n"
            "2. **El Rango:** ¿Los videos son cortos (menos de 3 min) o largos (más de 5 min)? ¿Hay mucha diferencia entre el mínimo y el máximo?\n"
            "3. **Implicación:** ¿Qué implica esto para la retención de la audiencia? ¿Son videos de formato 'single' o de formato 'álbum'?\n"
            "Sé analítico."
        ),
        "en": (
            "Analyze video duration:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Average Duration:** Mention the mean and median duration (in minutes).\n"
            "2. **The Range:** Are videos short (under 3 min) or long (over 5 min)? Is there a big difference between the minimum and maximum?\n"
            "3. **Implication:** What does this imply for audience retention? Are they 'single' format or 'album' format videos?\n"
            "Be analytical."
        )
    },

    "video_channels": {
        "es": (
            "Analiza la distribución por tipo de canal:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Canal Dominante:** Menciona qué tipo de canal (Artist, VEVO, Topic, etc.) tiene más canciones y su porcentaje.\n"
            "2. **Diversidad:** ¿Hay muchos tipos de canal o el catálogo está concentrado en uno o dos?\n"
            "3. **Implicación:** ¿Qué dice esto sobre la estrategia de distribución? ¿Es un catálogo de artistas independientes o de grandes sellos?\n"
            "Sé directo."
        ),
        "en": (
            "Analyze the distribution by channel type:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Dominant Channel:** Mention which channel type (Artist, VEVO, Topic, etc.) has the most songs and its percentage.\n"
            "2. **Diversity:** Are there many channel types or is the catalog concentrated in one or two?\n"
            "3. **Implication:** What does this say about the distribution strategy? Is it an independent artist catalog or a major label one?\n"
            "Be direct."
        )
    },

    # ========================================================================
    # SECTION 8: Temporal Analysis
    # ========================================================================
    "temporal_views": {
        "es": (
            "Analiza la evolución de vistas por trimestre:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Pico:** Identifica el trimestre con más vistas totales y su cifra exacta.\n"
            "2. **La Tendencia:** ¿Las vistas suben, bajan o se mantienen estables a lo largo de los trimestres?\n"
            "3. **Estacionalidad:** ¿Hay un patrón claro (ej. lanzamientos de verano, campañas de fin de año)?\n"
            "Ve al grano."
        ),
        "en": (
            "Analyze views evolution by quarter:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Peak:** Identify the quarter with the most total views and its exact figure.\n"
            "2. **The Trend:** Do views rise, fall, or remain stable across quarters?\n"
            "3. **Seasonality:** Is there a clear pattern (e.g., summer releases, year-end campaigns)?\n"
            "Get to the point."
        )
    },

    "temporal_engagement": {
        "es": (
            "Analiza la evolución del engagement por trimestre:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Pico:** Identifica el trimestre con el engagement promedio más alto y su porcentaje.\n"
            "2. **La Tendencia:** ¿La fidelidad de la audiencia se mantiene estable o varía con el tiempo?\n"
            "3. **Insight:** ¿El trimestre con más vistas es también el de más engagement? Si no es así, explica qué revela esto.\n"
            "Sé directo."
        ),
        "en": (
            "Analyze engagement evolution by quarter:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Peak:** Identify the quarter with the highest average engagement and its percentage.\n"
            "2. **The Trend:** Does audience loyalty remain stable or fluctuate over time?\n"
            "3. **Insight:** Is the quarter with the most views also the one with the most engagement? If not, explain what this reveals.\n"
            "Be direct."
        )
    },

    "temporal_releases": {
        "es": (
            "Analiza la distribución de lanzamientos por trimestre:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Trimestre Más Activo:** Identifica el trimestre con más lanzamientos y su cifra exacta.\n"
            "2. **La Distribución:** ¿Los lanzamientos están concentrados en un trimestre o distribuidos de forma equilibrada?\n"
            "3. **Implicación:** ¿Qué dice esto sobre la estrategia de lanzamiento? ¿Es una campaña de verano o de fin de año?\n"
            "Ve al grano."
        ),
        "en": (
            "Analyze release distribution by quarter:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Most Active Quarter:** Identify the quarter with the most releases and its exact figure.\n"
            "2. **The Distribution:** Are releases concentrated in one quarter or evenly distributed?\n"
            "3. **Implication:** What does this say about the release strategy? Is it a summer or year-end campaign?\n"
            "Get to the point."
        )
    },

    # ========================================================================
    # SECTION 9: Collaborations
    # ========================================================================
    "collab_views": {
        "es": (
            "Analiza las vistas: solistas vs colaboraciones:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Ganador:** Responde: ¿las colaboraciones o los solistas generan más vistas promedio?\n"
            "2. **La Brecha:** Compara ambos con sus cifras exactas. ¿Es una diferencia significativa?\n"
            "3. **Conclusión:** ¿Conviene colaborar para masificar o es mejor lanzar en solitario?\n"
            "Sé analítico."
        ),
        "en": (
            "Analyze views: solo vs collaborations:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Winner:** Answer: Do collaborations or solo artists generate more average views?\n"
            "2. **Gap:** Compare both with their exact figures. Is it a significant difference?\n"
            "3. **Conclusion:** Is it better to collaborate for mass reach or release solo?\n"
            "Be analytical."
        )
    },

    "collab_engagement": {
        "es": (
            "Analiza el engagement: solistas vs colaboraciones:\n\n{summary}\n\n"
            "Redacta 4 a 6 líneas. "
            "1. **El Ganador:** Responde: ¿las colaboraciones o los solistas generan más engagement promedio?\n"
            "2. **La Paradoja:** ¿Coincide con el que genera más vistas? Si no es así, explica qué revela esto (ej. las colaboraciones fidelizan pero no masifican).\n"
            "3. **Recomendación:** Termina con una recomendación: ¿conviene colaborar para fidelizar o para masificar?\n"
            "Sé analítico."
        ),
        "en": (
            "Analyze engagement: solo vs collaborations:\n\n{summary}\n\n"
            "Write 4 to 6 lines. "
            "1. **The Winner:** Answer: Do collaborations or solo artists generate more average engagement?\n"
            "2. **The Paradox:** Does it match the one that generates the most views? If not, explain what this reveals (e.g., collaborations build loyalty but not mass reach).\n"
            "3. **Recommendation:** End with a recommendation: is it better to collaborate for loyalty or mass reach?\n"
            "Be analytical."
        )
    },
}


class DeepSeekWriter:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.api_url = "https://api.deepseek.com/v1/chat/completions"

    def polish(self, section_id: str, summary: str, language: str = "es") -> tuple[str, int]:
        """
        Polish the raw summary using DeepSeek.
        
        Parameters
        ----------
        section_id : str
            The report section identifier (e.g., 'general_stats', 'introduction', 'conclusion').
        summary : str
            The raw summary generated by Groq, Gemma, or Muse Spark.
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

        # Safely get the prompt for the specific section and language
        section_prompts = WRITER_PROMPTS.get(section_id, {})
        prompt_template = section_prompts.get(language, section_prompts.get("es", ""))

        if not prompt_template:
            print(f"   [Writer] Warning: No prompt found for section '{section_id}' and language '{language}'. Using raw summary.")
            return summary, 0

        # For introduction and conclusion, the summary is already formatted with the placeholders
        # For other sections, the summary is the raw summary from the summarizer
        try:
            prompt = prompt_template.format(summary=summary)
        except KeyError:
            # If the prompt has other placeholders (like introduction), format them
            prompt = prompt_template

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
                    "max_tokens": 400
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
