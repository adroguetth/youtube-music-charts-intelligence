"""
YouTube Charts Weekly Downloader
============================================================================
Package entry point for the local-first YouTube Charts pipeline.

Run it with ``python -m scripts.1_download_chart``. The directory name starts
with a digit, so a normal ``import`` statement is not valid for it; the ``-m``
form is the only supported invocation.

Features
--------
- Headed Chromium with a persistent, trusted profile.
- Automatic challenge recovery with egress rotation.
- Canonical CSV plus idempotent SQLite persistence.

Dependencies
------------
- Internal: cli, config, core.*, fallbacks.*, models.*, persistence.*, utils.*.
- External: playwright.
- Downstream: none.

Requirements
------------
- Python 3.10+
- Playwright with Chromium installed in the virtualenv.

Notes
-----
- Only generated results are meant to be published upstream; the source tree
  and the browser profile stay on the local host.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

__all__ = ["config", "cli"]
