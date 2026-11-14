"""
Notebook - Assemble and Write the .ipynb File
============================================================================
Orchestrates the creation of a Jupyter notebook from a period's DataFrame.

Responsibilities
----------------
- Create a new notebook with the expected kernel metadata.
- Emit the title cell and the setup cell.
- Append the cells produced by each section builder, in the order
  declared in `report.sections.WEEKLY_SECTIONS`.
- Write the notebook to disk with `nbformat`.

Notes
-----
- This module contains no business logic and no metric definitions.
  Everything it emits comes from `report.builders` and `report.titles`.
- Imports are absolute (`from report.builders import ...`,
  `from report.sections import ...`, `from report.titles import ...`,
  `from report.setup import build_setup`), not relative. In script mode,
  `report` is a top-level module on `sys.path`; relative imports raise
  ``ImportError: attempted relative import beyond top-level package``.
- AI-generated insights (v2.0) are passed to each builder as the
  `insights` argument. Builders that support per-subsection injection
  (countries, genre_analysis, top_songs, video_metrics, temporal_analysis,
  collaborations) consume the dict internally. For the remaining sections
  (general_stats, continents), the insight is injected at the end of the
  section by this module.
- The v1.0 signature stays compatible:
  `generate_notebook(df, period, output_path, language, insights=None)`.
- The setup cell is emitted once, before the first section, by
  `setup.build_setup`. It is not part of `WEEKLY_SECTIONS` and must
  not be added there.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf
import pandas as pd
from nbformat.v4 import new_markdown_cell, new_notebook

from report.sections import BUILDERS, WEEKLY_SECTIONS
from report.setup import build_setup
from report.titles import notebook_title


# ============================================================================
# SECTIONS WITH INTERNAL INSIGHT INJECTION
# ============================================================================
# These sections have builders that inject their own insights after each
# subsection. `notebook.py` must NOT inject an insight at the end for them,
# or the insight will be duplicated.
_SECTIONS_WITH_INTERNAL_INSIGHTS: frozenset[str] = frozenset({
    "countries",
    "genre_analysis",
    "top_songs",
    "video_metrics",
    "temporal_analysis",
    "collaborations",
})


# ============================================================================
# PUBLIC API
# ============================================================================
def generate_notebook(
    df: pd.DataFrame,
    period,
    output_path: Path,
    language: str,
    insights: dict[str, str] | None = None,
) -> None:
    """
    Build and write a notebook for the given period and language.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched DataFrame for the period, produced by `core.db.load_week`.
    period : core.periods.Period
        Period being reported.
    output_path : Path
        Destination ``.ipynb`` file. Parent directories are created if
        they do not exist.
    language : str
        ``"en"`` or ``"es"``.
    insights : dict[str, str] or None
        Optional mapping of ``section_id -> markdown_text``. When provided,
        it is passed to each builder. Sections with internal injection
        (see `_SECTIONS_WITH_INTERNAL_INSIGHTS`) consume it directly;
        the remaining sections receive their insight at the end of the
        section from this function.

    Notes
    -----
    The notebook layout is:

        [title cell]
        [setup cell]
        for each section in WEEKLY_SECTIONS:
            [section cells from builder]
            [optional insight markdown cell]  # only for sections without
                                              # internal injection
    """
    nb = new_notebook()
    nb.metadata = _kernel_metadata()

    nb.cells.append(new_markdown_cell(_title_markdown(period, language)))
    nb.cells.extend(build_setup(period, language))

    for section in WEEKLY_SECTIONS:
        builder = BUILDERS[section]
        nb.cells.extend(builder(df, period, language, insights))

        # Only inject the insight at the end for sections whose builders
        # do NOT already handle it internally.
        if section not in _SECTIONS_WITH_INTERNAL_INSIGHTS:
            if insights and insights.get(section):
                nb.cells.append(new_markdown_cell(insights[section]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        nbf.write(nb, f)


# ============================================================================
# INTERNAL HELPERS
# ============================================================================
def _kernel_metadata() -> dict:
    """Return the notebook metadata block (kernel spec + language info)."""
    return {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.12.3",
        },
    }


def _title_markdown(period, language: str) -> str:
    """Return the H1 title cell for the notebook."""
    title = notebook_title(language)
    return f"# {title} — {period.label}\n"
