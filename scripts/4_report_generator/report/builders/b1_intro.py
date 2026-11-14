"""
B1 - Introduction
============================================================================
Builder for Section 1: Introduction.

Responsibilities
----------------
- Emit the section title (using the centralized titles registry).
- Emit a markdown cell with the reporting period metadata (week label,
  start date, end date, and number of days).
- Support both English and Spanish output based on the `language` argument.

Notes
-----
- This builder does not create any code cells or plots.
- All text is strictly in English inside the code; the bilingual output
  is handled by the `language` parameter and the `titles` registry.
- The `insights` argument is accepted for signature consistency with
  other builders but is intentionally ignored: the Introduction section
  does not have an AI-generated analysis.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import pandas as pd
from nbformat.v4 import new_markdown_cell

from report.titles import section_title


def build_intro(
    df: pd.DataFrame,
    period,
    language: str,
    insights: dict[str, str] | None = None,
) -> list:
    """
    Build the Introduction section.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched DataFrame (unused in this section, but kept for
        signature consistency with other builders).
    period : core.periods.Period
        The reporting period.
    language : str
        ``"en"`` or ``"es"``.
    insights : dict[str, str] or None
        Optional mapping of ``section_id -> markdown_text``. Ignored in
        this builder: the Introduction section has no AI-generated
        analysis. Accepted for signature consistency.

    Returns
    -------
    list
        A list of `nbformat` markdown cells.
    """
    if language == "en":
        meta = (
            f"**Week:** {period.label} | "
            f"**Period:** {period.start} → {period.end} | "
            f"**Days:** {period.n_days}"
        )
    else:
        meta = (
            f"**Semana:** {period.label} | "
            f"**Periodo:** {period.start} → {period.end} | "
            f"**Días:** {period.n_days}"
        )

    return [
        new_markdown_cell(section_title("intro", language)),
        new_markdown_cell(meta),
    ]
