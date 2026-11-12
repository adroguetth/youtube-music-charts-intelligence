"""
Report - Notebook Assembly
============================================================================
Layer that turns the aggregations from `core` into a Jupyter notebook.

Responsibilities
----------------
- Declare the ordered list of report sections (`sections`).
- Provide the section titles in English and Spanish (`titles`).
- Provide one cell builder per section (`builders`).
- Provide the notebook setup cell (`setup`).
- Assemble and write the final `.ipynb` file (`notebook`).

Notes
-----
- This subpackage imports `nbformat` and `pandas`, and depends on `core`
  for data and metrics. Nothing in `core` imports from here: the
  dependency goes one way only.
- Imports are absolute (`from report.x import ...`), not relative
  (`from .x import ...`), because `main.py` is executed in script mode
  and `report` is a top-level module on `sys.path`.
- `BUILDERS` is defined in `report.sections` (the registry that wires
  section ids to builder functions). The individual builders live in
  the `report.builders` package.
- The `build_setup` function lives in `report.setup` because it is not a
  report section; it is prepended to the notebook before the first section.
- Builders return `nbformat` cells. They do not print, log, or write
  files. All I/O happens in `notebook.generate_notebook` and in
  `main.py`.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

from report.notebook import generate_notebook
from report.sections import BUILDERS, WEEKLY_SECTIONS
from report.setup import build_setup
from report.titles import section_title

__all__ = [
    "BUILDERS",
    "WEEKLY_SECTIONS",
    "build_setup",
    "generate_notebook",
    "section_title",
]
