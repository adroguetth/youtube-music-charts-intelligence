"""
B2 - General Statistics
============================================================================
Builder for Section 2: General Statistics.

Responsibilities
----------------
- Emit the section title.
- Emit a code cell that calculates general statistics (total songs,
  unique countries, unique genres, total views/likes, averages).
- Format the output as a vertical table to avoid horizontal overflow.

Notes
-----
- This builder does not create any plots in the current version.
- The numeric formatting avoids scientific notation (K, M, B suffixes).
- The `style_axes` helper is not used here yet, but the section is
  structured so that a chart can be added later without touching other
  sections.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import pandas as pd
from nbformat.v4 import new_code_cell, new_markdown_cell

from report.titles import section_title


def build_general_stats(df: pd.DataFrame, period, language: str) -> list:
    """
    Build the General Statistics section.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched DataFrame for the period.
    period : core.periods.Period
        The reporting period.
    language : str
        ``"en"`` or ``"es"``.

    Returns
    -------
    list
        A list of `nbformat` cells.
    """
    return [
        new_markdown_cell(section_title("general_stats", language)),
        new_code_cell(
            # 1. Calculate stats.
            # 2. Convert the dict to a list of tuples and then to a DataFrame
            #    with columns 'Metric' and 'Value'.
            # 3. The global pd.set_option('display.float_format', ...) in
            #    SETUP_CODE ensures numbers are displayed cleanly.
            "stats = general_stats(df)\n"
            "display(pd.DataFrame(list(stats.items()), columns=['Metric', 'Value']))"
        ),
    ]
