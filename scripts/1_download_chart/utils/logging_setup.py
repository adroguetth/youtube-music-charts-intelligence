"""
Logging Setup
============================================================================
Console logging for every run, plus a rotating-by-day file handler on local
hosts. The file handler is attached once, from the entry point, so wrapped or
programmatic invocations cannot duplicate log lines.

Features
--------
- Deterministic console format shared by every module.
- Daily log file at ``logs/scraper_YYYY-MM-DD.log``.
- Idempotent handler attachment.

Dependencies
------------
- Internal: config (LOGS_DIR).
- External: logging, datetime, pathlib (stdlib).
- Downstream: __main__ and every module that calls ``get_logger``.

Requirements
------------
- Python 3.10+

Notes
-----
- Failures to open the log file degrade to console-only logging; they never
  abort the run.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import LOGS_DIR


# ============================================================================
# CONSTANTS
# ============================================================================
LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
LOGGER_NAME = "youtube_charts"


# ============================================================================
# LOGGERS AND HANDLERS
# ============================================================================
def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure the root handler. Call once, from the entry point."""
    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt=LOG_DATEFMT)
    return get_logger()


def attach_file_handler(logger: logging.Logger) -> Optional[Path]:
    """Mirror logs into ``logs/scraper_YYYY-MM-DD.log``.

    Idempotent: a second call does not duplicate handlers, which matters when
    the pipeline is invoked programmatically by tests or wrappers.
    """
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOGS_DIR / f"scraper_{datetime.now():%Y-%m-%d}.log"
        already_attached = any(
            isinstance(handler, logging.FileHandler) for handler in logger.handlers
        )
        if not already_attached:
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setFormatter(
                logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
            )
            logger.addHandler(handler)
            logger.info("Log file: %s", log_file)
        return log_file
    except Exception as exc:
        logger.warning("Could not attach file handler: %s", exc)
        return None
