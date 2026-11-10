"""
Report - Notebook Assembly
============================================================================
Layer that turns the aggregations from `core` into a Jupyter notebook.

Responsibilities
----------------
- Declare the ordered list of report sections (`sections`).
- Provide the section titles in English and Spanish (`titles`).
- Provide one cell builder per section (`builders`).
- Assemble and write the final `.ipynb` file (`notebook`).

Notes
-----
- This subpackage imports `nbformat` and `pandas`, and depends on `core`
  for data and metrics. Nothing in `core` imports from here: the
  dependency goes one way only.
- Imports are absolute (`from report.builders import ...`), not relative
  (`from .builders import ...`), because `main.py` is executed in script
  mode and `report` is a top-level module on `sys.path`. Relative imports
  break with ``ImportError: attempted relative import beyond top-level
  package`` when `report.builders` imports from `core.metrics` via a
  parent-relative path.
- Builders return `nbformat` cells. They do not print, log, or write
  files. All I/O happens in `notebook.generate_notebook` and in
  `main.py`.
- In v2.0, AI-generated insights will be injected between a section's
  cells and the next section's header. That injection point lives in
  `notebook.generate_notebook` via an optional `insights` parameter, so
  no builder needs to change.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

from report.builders import BUILDERS
from report.notebook import generate_notebook
from report.sections import WEEKLY_SECTIONS
from report.titles import section_title

__all__ = [
    "BUILDERS",
    "WEEKLY_SECTIONS",
    "generate_notebook",
    "section_title",
]
