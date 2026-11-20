"""
Process Locking
============================================================================
Process-level mutual exclusion and cleanup of stale Chromium singleton files.

cron does not prevent overlapping runs; two Chromium instances sharing the same
user-data directory corrupt the persistent profile, so the second run must
abort before touching it.

Features
--------
- Non-blocking ``flock`` acquired for the whole process lifetime.
- Safe removal of ``SingletonLock``/``SingletonCookie``/``SingletonSocket``.
- Typed ``LockBusy`` error mapped to exit code 30 by the entry point.

Dependencies
------------
- Internal: config (BROWSER_PROFILE_DIR).
- External: fcntl, contextlib, logging, pathlib (stdlib).
- Downstream: __main__, core.browser.

Requirements
------------
- Python 3.10+
- A POSIX platform (``fcntl``).

Notes
-----
- ``cleanup_browser_locks`` is safe only while the process lock is held.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import fcntl
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO

from ..config import BROWSER_PROFILE_DIR

log = logging.getLogger("youtube_charts")


# ============================================================================
# CONSTANTS
# ============================================================================
CHROME_SINGLETON_FILES = ("SingletonLock", "SingletonCookie", "SingletonSocket")


# ============================================================================
# PROCESS LOCK
# ============================================================================
class LockBusy(RuntimeError):
    """Raised when another instance already holds the process lock."""


@contextmanager
def process_lock(path: Path) -> Iterator[TextIO]:
    """Hold an exclusive, non-blocking ``flock`` for the process lifetime.

    cron does not prevent overlapping runs; two Chromium instances sharing the
    same user-data-dir corrupt the profile, so the second run must abort.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    locked = False
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except BlockingIOError as exc:
            raise LockBusy(str(path)) from exc
        yield handle
    finally:
        if locked:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


# ============================================================================
# PROFILE LOCK CLEANUP
# ============================================================================
def cleanup_browser_locks() -> None:
    """Remove Chrome singleton files left behind by a killed process.

    Safe only while the process lock is held: the profile cannot be in use by
    another instance of this scraper at that point.
    """
    if not BROWSER_PROFILE_DIR.exists():
        return
    for name in CHROME_SINGLETON_FILES:
        stale = BROWSER_PROFILE_DIR / name
        if not stale.exists():
            continue
        try:
            stale.unlink()
            log.info("Removed stale Chrome lock: %s", name)
        except OSError as exc:
            log.warning("Could not remove %s: %s", name, exc)
