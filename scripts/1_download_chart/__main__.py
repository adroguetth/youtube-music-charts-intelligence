"""
YouTube Charts Data Scraper - Entry Point
============================================================================
Local-first pipeline for downloading YouTube Charts weekly data and storing it
in SQLite. Orchestrates dependency checks, browser automation with
anti-detection measures, CSV acquisition, idempotent SQLite persistence,
retention cleanup and a final inventory summary.

This module is the entry point of the scraper. It is meant to run on a physical
Linux host (shell or cron); only the generated results are published upstream.

Usage
-----
    python -m scripts.1_download_chart --terminal --use-chrome

Features
--------
- Complete CSV files (100 songs) from YouTube Charts.
- Historical data in SQLite with one database per ISO week.
- Bounded download retries with automatic challenge recovery and egress
  rotation; no manual step is ever required.
- Backup before every database update; retention for backups and databases.
- Fallback mode that writes synthetic rows only when explicitly allowed.

Dependencies
------------
- Internal: cli, config, core.*, fallbacks.*, models.*, persistence.*, utils.*.
- External: playwright, sqlite3 (stdlib), csv, asyncio.
- Downstream: none (this is the entry point).

Requirements
------------
- Python 3.10+
- Playwright with Chromium installed in the virtualenv.
- A local display for headed Chrome; the cron example lives in README.md.

Notes
-----
- Paths are anchored at the repository root, so cron may start anywhere.
- Week identifiers follow ISO format ``YYYY-WXX`` (e.g. ``2025-W05``).
- The run refuses to write placeholder data unless ``--allow-fallback`` is set.
- Exit code ``21`` signals an exhausted challenge rotation; cron retries later.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .cli import parse_args
from .config import (
    ARCHIVE_DIR,
    BACKUP_RETENTION_DAYS,
    DATABASE_DIR,
    DATABASE_RETENTION_WEEKS,
    IS_GITHUB_ACTIONS,
    LOCK_FILE,
    MIN_ROWS_IDEMPOTENCY,
    MIN_ROWS_PRIMARY,
    ensure_directories,
    get_week_identifier,
    proxy_candidates,
)
from .core.browser import (
    ensure_playwright_available,
    is_browser_launch_error,
    wipe_browser_profile,
)
from .core.captcha import ChallengeDetected
from .core.downloader import download_via_http, download_youtube_charts
from .fallbacks.synthetic import create_fallback_file
from .models.enums import ExitCode
from .persistence.backup import cleanup_old_backups, cleanup_old_databases
from .persistence.sqlite_handler import (
    count_real_rows,
    list_available_databases,
    update_sqlite_database,
)
from .utils.locking import LockBusy, cleanup_browser_locks, process_lock
from .utils.logging_setup import attach_file_handler, configure_logging, get_logger
from .utils.processes import kill_orphan_browser_processes, open_folder

# ============================================================================
# CONSTANTS
# ============================================================================
MAX_DOWNLOAD_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 10

log = get_logger()


# ============================================================================
# ENTRY POINT
# ============================================================================
def main(argv: Optional[List[str]] = None) -> int:
    """Run the pipeline, then honour the interactive flags of a manual launch.

    Parameters
    ----------
    argv : list of str or None, optional
        Argument vector; ``None`` reads ``sys.argv[1:]``.

    Returns
    -------
    int
        Process exit code.

    Notes
    -----
    ``--terminal`` returns before any prompt, so cron runs are always
    non-interactive. The ``--pause``/no-TTY prompt only closes a desktop
    window; it is unrelated to challenge handling.
    """
    code = _run(argv)
    args_list = list(argv) if argv is not None else sys.argv[1:]

    if "--terminal" in args_list:
        return code
    if "--open-folder" in args_list and code == 0:
        open_folder(ARCHIVE_DIR)

    try:
        has_tty = sys.stdin.isatty()
    except Exception:
        has_tty = False
    if "--pause" in args_list or not has_tty:
        try:
            input("\nPress Enter to close...")
        except Exception:
            pass
    return code


# ============================================================================
# PIPELINE STAGES
# ============================================================================
def _run(argv: Optional[List[str]] = None) -> int:
    """Parse arguments, set up logging and execute under the process lock.

    Parameters
    ----------
    argv : list of str or None, optional
        Argument vector; ``None`` reads ``sys.argv[1:]``.

    Returns
    -------
    int
        Process exit code, including ``30`` when the lock is already held.
    """
    args = parse_args(argv)
    configure_logging()
    ensure_directories()
    attach_file_handler(log)

    print("\n" + "=" * 70)
    print("YOUTUBE CHARTS - LOCAL EXTRACTOR (100 songs)")
    print("Target: local Linux host; CI runners are not supported")
    print(f"Chart: {args.chart} / Country: {args.country}")
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 70)

    if args.wipe_profile:
        log.warning("--wipe-profile set: deleting the persistent profile")
        log.warning("The next run will most likely be challenged")
        wipe_browser_profile()

    try:
        with process_lock(LOCK_FILE):
            return _run_pipeline(args)
    except LockBusy:
        log.error("Another run already holds %s; exiting", LOCK_FILE)
        return ExitCode.LOCK_BUSY


def _run_pipeline(args) -> int:
    """Execute the pipeline stages in order.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments.

    Returns
    -------
    int
        Process exit code (``0`` on a successful real write).

    Notes
    -----
    Download attempts rotate through ``proxy_candidates()`` and stop on the
    first CSV that passes ``MIN_ROWS_PRIMARY``. ``ChallengeDetected`` triggers
    the next attempt; exhausting the rotation returns ``CAPTCHA_BLOCKED``.
    """
    if IS_GITHUB_ACTIONS:
        log.error("This build runs on local hosts only, not on CI runners")
        return ExitCode.NO_DATA

    if args.terminal:
        log.info(
            "Terminal mode: non-interactive, DISPLAY=%s",
            os.environ.get("DISPLAY", "(none)"),
        )
    else:
        log.info(
            "Local mode: persistent_profile=%s timezone=%s DISPLAY=%s",
            not args.no_profile,
            os.environ.get("TZ", "(system)"),
            os.environ.get("DISPLAY", "(none)"),
        )

    week_id = args.week or get_week_identifier()
    if not args.force:
        db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
        if db_path.exists():
            try:
                existing = count_real_rows(db_path, week_id)
                if existing >= MIN_ROWS_IDEMPOTENCY:
                    log.info(
                        "Week %s already holds %d real rows; skipping "
                        "(use --force to re-scrape)",
                        week_id,
                        existing,
                    )
                    return ExitCode.IDEMPOTENT_SKIP
            except Exception as exc:
                log.info("Idempotency check failed (ignored): %s", exc)
    log.info("Target week: %s", week_id)

    print("\n0. CHECKING DEPENDENCIES...")
    playwright_ready = False
    if not args.no_browser:
        playwright_ready = ensure_playwright_available()
        if not playwright_ready:
            log.warning("Playwright unavailable; falling back to direct HTTP")
    else:
        log.info("--no-browser: skipping Playwright")

    print("\n1. DOWNLOADING YOUTUBE CHARTS...")
    csv_path: Optional[Path] = None
    is_synthetic = False
    challenged = False

    if playwright_ready:
        show_browser = not args.headless
        if args.headless:
            log.warning(
                "Explicit --headless: Google challenges headless sessions; "
                "run without it if the download fails"
            )
        elif args.terminal:
            log.info(
                "Terminal mode with DISPLAY=%s: headed window",
                os.environ.get("DISPLAY", "(none)"),
            )
        else:
            log.info("Headed mode: headless sessions are challenged more often")

        proxies = proxy_candidates()
        if len(proxies) > 1:
            log.info("Proxy rotation enabled with %d endpoints", len(proxies))
        elif proxies[0]:
            log.info("Using proxy %s", proxies[0]["server"])

        # The persistent profile is the anti-captcha asset: never delete it from
        # the retry path. Egress rotates between attempts; the profile does not.
        for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
            proxy = proxies[(attempt - 1) % len(proxies)]
            log.info(
                "Download attempt %d/%d (proxy=%s)",
                attempt,
                MAX_DOWNLOAD_ATTEMPTS,
                proxy["server"] if proxy else "direct",
            )
            if attempt >= 2:
                kill_orphan_browser_processes()
                cleanup_browser_locks()

            try:
                csv_path = asyncio.run(
                    download_youtube_charts(
                        chart=args.chart,
                        country=args.country,
                        show_browser=show_browser,
                        use_chrome=args.use_chrome,
                        keep_profile=not args.no_profile,
                        proxy=proxy,
                    )
                )
            except ChallengeDetected as exc:
                challenged = True
                csv_path = None
                log.warning(
                    "Attempt %d/%d blocked by a challenge: %s",
                    attempt,
                    MAX_DOWNLOAD_ATTEMPTS,
                    exc.url,
                )
            except Exception as exc:
                log.error(
                    "Playwright download failed (attempt %d): %s",
                    attempt,
                    exc,
                    exc_info=True,
                )
                csv_path = None
                if is_browser_launch_error(exc) and attempt < MAX_DOWNLOAD_ATTEMPTS:
                    log.warning(
                        "Browser launch failure; reaping orphans and retrying "
                        "(profile preserved)"
                    )

            if csv_path and Path(csv_path).exists():
                try:
                    with open(csv_path, "r", encoding="utf-8", errors="ignore") as handle:
                        rows = sum(1 for _ in handle) - 1
                    if rows >= MIN_ROWS_PRIMARY:
                        break
                    log.warning(
                        "CSV has %d rows (<%d); retrying", rows, MIN_ROWS_PRIMARY
                    )
                except Exception:
                    pass

            if attempt < MAX_DOWNLOAD_ATTEMPTS:
                backoff = RETRY_BACKOFF_SECONDS * attempt
                log.info("Waiting %ds before retry", backoff)
                time.sleep(backoff)
            else:
                log.error("All download attempts failed; profile left untouched")
                log.error(
                    "If this persists, reset manually: --wipe-profile --use-chrome"
                )
                csv_path = None

    if csv_path is None or not Path(csv_path).exists():
        log.info("Trying direct HTTP")
        csv_path = download_via_http(chart=args.chart, country=args.country)

    print("\n2. VALIDATING CSV...")
    if csv_path is None or not Path(csv_path).exists():
        log.warning("Automatic download failed")
        if args.allow_fallback:
            log.warning("Writing SYNTHETIC rows because --allow-fallback is set")
            csv_path = create_fallback_file(week_id, reason="download failed")
            is_synthetic = True
        else:
            log.error("CRITICAL: no CSV available; refusing to write placeholder data")
            log.error("For tests, run with --allow-fallback")
            if challenged:
                log.error(
                    "Every attempt was blocked by a challenge; egress rotation "
                    "exhausted"
                )
                return ExitCode.CAPTCHA_BLOCKED
            return ExitCode.NO_DATA

    try:
        with open(csv_path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
        num_songs = len(lines) - 1 if len(lines) > 1 else 0
        log.info("Songs in CSV: %d", num_songs)
        if lines:
            log.info("Headers: %s", lines[0].strip()[:200])
        if num_songs < MIN_ROWS_PRIMARY:
            log.warning(
                "CSV holds few songs (%d); it may be incomplete", num_songs
            )
            if not is_synthetic and args.allow_fallback:
                log.warning("Incomplete CSV; switching to synthetic fallback")
                csv_path = create_fallback_file(
                    week_id, reason=f"CSV incomplete with {num_songs} rows"
                )
                is_synthetic = True
            elif not is_synthetic:
                log.error(
                    "CSV incomplete and --allow-fallback is off; aborting "
                    "without writing"
                )
                return ExitCode.NO_DATA
    except Exception as exc:
        log.error("Could not read CSV: %s", exc)
        return ExitCode.GENERIC_ERROR

    print("\n3. WRITING TO SQLITE...")
    db_path = update_sqlite_database(
        Path(csv_path), week_id, is_synthetic=is_synthetic
    )
    if not db_path:
        log.error("Database update failed")
        return ExitCode.GENERIC_ERROR

    print("\n4. CLEANING OLD FILES...")
    cleanup_old_backups(BACKUP_RETENTION_DAYS)
    cleanup_old_databases(DATABASE_RETENTION_WEEKS)

    print("\n5. SUMMARY:")
    list_available_databases()

    print("\n" + "=" * 70)
    if is_synthetic:
        print("WARNING: SYNTHETIC ROWS WERE WRITTEN (is_synthetic=1)")
    else:
        print("COMPLETED - REAL DATA")
    print("=" * 70)
    return ExitCode.OK


if __name__ == "__main__":
    sys.exit(main())
