"""
report_generator - Weekly Music Charts Report Generator
============================================================================
Package that turns an enriched weekly chart DB into a Jupyter notebook
with charts, tables and (from v2.0) AI-generated insights.

Public entry point
------------------
    python -m scripts.4_report_generator --language both

Subpackages
-----------
- `core`: periods, database access, metrics. Pure logic, no notebook code.
- `report`: notebook assembly (titles, sections, builders, notebook).

Sibling modules
---------------
- `config`: paths, logger, language helpers.
- `main`: CLI orchestrator (`main() -> int`).
- `__main__`: module entry point for `python -m`.

Versioning roadmap
------------------
- v1.0 (current): weekly report, EN/ES, charts and tables only.
- v2.0: integrate DeepSeek-generated insights (`core.insights`,
  `report.prompts`, `insights` parameter in `generate_notebook`).
- v3.0: add monthly report with its own metrics module
  (`core.metrics.monthly`, `report.builders_monthly`), plus the
  `--kind week|month` flag.
- v4.0: Streamlit dashboard consuming `core` directly.

Notes
-----
- No module in `core` imports from `report`. The dependency direction is
  `report -> core`, one way only. This keeps the dashboard (v4.0) free
  to import from `core` without pulling in `nbformat`.
- The package is import-safe: importing it does not read the filesystem,
  does not load a database and does not configure logging beyond what
  `config` already does at import time.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
