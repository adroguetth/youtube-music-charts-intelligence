"""
Command-Line Interface
============================================================================
Argument parser for the local YouTube Charts scraper. Every flag maps directly
to one behaviour in the pipeline and is documented for cron operators.

Features
--------
- Chart, country and week selection.
- Execution-mode switches (headed, headless, terminal, no-browser).
- Profile lifecycle control, including the destructive ``--wipe-profile``.
- Fallback gating: synthetic rows require ``--allow-fallback``.

Dependencies
------------
- Internal: models.enums (ChartType).
- External: argparse (stdlib).
- Downstream: __main__ (parse_args).

Requirements
------------
- Python 3.10+

Notes
-----
- The package directory starts with a digit; invoke it with ``python -m``.
- ``--terminal`` disables every interactive prompt; it is the cron mode.
- ``--captcha-timeout`` does not exist: challenge recovery is automatic.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import argparse
from typing import List, Optional

from .models.enums import ChartType


# ============================================================================
# PARSER
# ============================================================================
def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns
    -------
    argparse.ArgumentParser
        Fully configured parser.
    """
    parser = argparse.ArgumentParser(
        prog="python -m scripts.1_download_chart",
        description="YouTube Charts weekly scraper for a local Linux host.",
    )
    parser.add_argument(
        "--country",
        default="global",
        help="Chart country, e.g. global, us, cl (default: global).",
    )
    parser.add_argument(
        "--chart",
        default=ChartType.TOP_SONGS.value,
        help="Chart type, e.g. TopSongs, TopArtists (default: TopSongs).",
    )
    parser.add_argument(
        "--week",
        default=None,
        help="Force the week id, e.g. 2025-W05. Defaults to the current ISO week.",
    )
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help=(
            "Allow writing SYNTHETIC rows when scraping fails. Without this flag "
            "the run exits with code 20 and the database is untouched."
        ),
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Skip Playwright and use direct HTTP only.",
    )
    parser.add_argument(
        "--terminal",
        action="store_true",
        help=(
            "Non-interactive mode: no input() prompts. Not headless; the window "
            "still opens when a display is available. This is the cron mode."
        ),
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Show the browser window (default when a display is present).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help=(
            "Force headless mode. Not recommended: Google challenges headless "
            "sessions far more often than headed ones."
        ),
    )
    parser.add_argument(
        "--use-chrome",
        action="store_true",
        help="Use the installed Google Chrome instead of the bundled Chromium.",
    )
    parser.add_argument(
        "--no-profile",
        action="store_true",
        help="Use a throwaway context instead of the persistent .browser-profile.",
    )
    parser.add_argument(
        "--open-folder",
        action="store_true",
        help="Open the archive folder when the run succeeds.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-scrape even when the week already holds real rows.",
    )
    parser.add_argument(
        "--wipe-profile",
        action="store_true",
        help=(
            "DESTRUCTIVE: delete .browser-profile before running. Google will "
            "challenge the first run afterwards. Use only on a confirmed "
            "corrupt profile."
        ),
    )
    parser.add_argument(
        "--pause",
        action="store_true",
        help="Wait for Enter before exiting (double-click launches).",
    )
    return parser


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)
