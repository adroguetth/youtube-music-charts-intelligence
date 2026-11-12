"""
__main__ - Module Entry Point
============================================================================
Allows running the package as a module:

    python -m scripts.4_report_generator --language both

This file is a thin wrapper. It imports `main` from `.main` and forwards
the exit code to the interpreter via `sys.exit`. No logic lives here.

Notes
-----
- The directory name `4_report_generator` starts with a digit, which is
  not a valid Python identifier. As a consequence, `python -m
  scripts.4_report_generator` only works if `scripts` is importable as a
  package (i.e. `scripts/__init__.py` exists) and the `importlib` loader
  can resolve the numeric module name. In practice, this is fragile and
  environment-dependent.
- The recommended invocation in CI and locally is therefore:

      python scripts/4_report_generator/main.py --language both

  which runs `main.py` as a script. This `__main__.py` is kept for
  completeness and for environments where `-m` happens to work, but it
  is not the canonical entry point.
- See the package `__init__.py` for the versioning roadmap and the
  dependency direction (`report -> core`, one way only).

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import sys

from .main import main


if __name__ == "__main__":
    sys.exit(main())
