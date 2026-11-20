"""
Operating-System Helpers
============================================================================
Process and desktop integration helpers: orphan Chromium reaping and folder
opening. Kept separate from ``browser`` so they can be unit-tested without
Playwright installed.

Features
--------
- Reaps browser processes still holding the persistent profile.
- Frees the profile lock without discarding cookies or consent state.
- Opens the archive folder without blocking the run.

Dependencies
------------
- Internal: config (BROWSER_PROFILE_DIR).
- External: logging, os, signal, subprocess, time (stdlib).
- Downstream: __main__, core.browser.

Requirements
------------
- Python 3.10+
- ``pgrep`` available (procps); missing ``pgrep`` degrades to a no-op.

Notes
-----
- Only processes matching the profile path or the Playwright Chromium pattern
  are signalled; the current process is always excluded.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path

from ..config import BROWSER_PROFILE_DIR

log = logging.getLogger("youtube_charts")


# ============================================================================
# CONSTANTS
# ============================================================================
_ORPHAN_PATTERNS = ("playwright.*chromium",)


# ============================================================================
# ORPHAN PROCESS REAPING
# ============================================================================
def kill_orphan_browser_processes() -> int:
    """Terminate browser processes still holding the persistent profile.

    A crashed Chromium keeps the profile lock, which surfaces on the next run
    as ``TargetClosedError`` / ``Connection closed``. Reaping the process frees
    the profile without discarding cookies or consent state.

    Returns the number of processes signalled.
    """
    profile_path = str(BROWSER_PROFILE_DIR.resolve())
    pids: set[int] = set()

    for pattern in (profile_path, *_ORPHAN_PATTERNS):
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError:
            log.debug("pgrep is unavailable; skipping orphan reaping")
            return 0
        except Exception as exc:
            log.warning("pgrep failed for %r: %s", pattern, exc)
            continue
        for token in result.stdout.split():
            if token.isdigit() and int(token) != os.getpid():
                pids.add(int(token))

    killed = 0
    for pid in sorted(pids):
        try:
            os.kill(pid, signal.SIGTERM)
            killed += 1
            log.info("Signalled orphan browser process: PID %d", pid)
        except ProcessLookupError:
            continue
        except PermissionError:
            log.warning("No permission to signal PID %d", pid)
        except Exception as exc:
            log.warning("Could not signal PID %d: %s", pid, exc)

    if killed:
        # Give the kernel time to release the profile lock before a retry.
        time.sleep(2)
    return killed


# ============================================================================
# DESKTOP INTEGRATION
# ============================================================================
def open_folder(path: Path) -> None:
    """Open a directory in the desktop file manager, never blocking the run."""
    try:
        resolved = str(Path(path).resolve())
        log.info("Opening folder: %s", resolved)
        subprocess.Popen(
            ["xdg-open", resolved],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        log.warning("Could not open %s: %s", path, exc)
        log.info("Open it manually: %s", path)
