"""
Titles - Section Headings in English and Spanish
============================================================================
Centralised section titles for the weekly report.

Responsibilities
----------------
- Provide the markdown heading for each report section, per language.
- Provide the title of the notebook itself, per language.

Notes
-----
- Keys must match the section identifiers declared in `report.sections`.
  If a new section is added there, add its title here too. A missing key
  raises `KeyError` at build time, which is the desired behaviour: no
  section should ever render without a heading.
- Section numbers are hardcoded in the titles (e.g. "## 4. Country Analysis")
  and must be kept in sync with `WEEKLY_SECTIONS`. The section ordering is
  defined in `report.sections`.
- Sub-sections (e.g. "4.1. Top Countries") are handled directly by the
  builders as markdown cells, not by this registry, to keep the structure
  flat and easy to read.
- This module contains no formatting logic beyond returning strings.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

# ============================================================================
# NOTEBOOK TITLE
# ============================================================================
_NOTEBOOK_TITLE = {
    "en": "Enriched Music Charts Analysis",
    "es": "Análisis Enriquecido de Charts Musicales",
}


# ============================================================================
# SECTION TITLES
# ============================================================================
_SECTION_TITLES = {
    "intro": {
        "en": "## 1. Introduction",
        "es": "## 1. Introducción",
    },
    "general_stats": {
        "en": "## 2. General Statistics",
        "es": "## 2. Estadísticas Generales",
    },
    "continents": {
        "en": "## 3. Continent Analysis",
        "es": "## 3. Análisis por Continente",
    },
    "countries": {
        "en": "## 4. Country Analysis",
        "es": "## 4. Análisis por País",
    },
    "genre_analysis": {
        "en": "## 5. Genre Analysis",
        "es": "## 5. Análisis por Género",
    },
    "top_songs": {
        "en": "## 6. Song Metrics",
        "es": "## 6. Métricas de Canciones",
    },
    "video_metrics": {
        "en": "## 7. Video Metrics",
        "es": "## 7. Métricas de Video",
    },
    "temporal_analysis": {
        "en": "## 8. Temporal Analysis",
        "es": "## 8. Análisis Temporal",
    },
    "collaborations": {
        "en": "## 9. Collaborations Analysis",
        "es": "## 9. Análisis de Colaboraciones",
    },
    "exec_summary": {
        "en": "## 10. Executive Summary",
        "es": "## 10. Resumen Ejecutivo",
    },
}


# ============================================================================
# PUBLIC API
# ============================================================================
def notebook_title(language: str) -> str:
    """
    Return the notebook title for a given language.

    Parameters
    ----------
    language : str
        ``"en"`` or ``"es"``.

    Returns
    -------
    str
        Notebook title, e.g. ``"Enriched Music Charts Analysis"``.

    Raises
    ------
    KeyError
        If `language` is not supported.
    """
    return _NOTEBOOK_TITLE[language]


def section_title(section: str, language: str) -> str:
    """
    Return the markdown heading for a given section and language.

    Parameters
    ----------
    section : str
        Section identifier, e.g. ``"general_stats"``. Must match a key in
        `_SECTION_TITLES`.
    language : str
        ``"en"`` or ``"es"``.

    Returns
    -------
    str
        Markdown heading, e.g. ``"## 2. General Statistics"``.

    Raises
    ------
    KeyError
        If `section` is unknown or `language` is not supported.
    """
    return _SECTION_TITLES[section][language]
