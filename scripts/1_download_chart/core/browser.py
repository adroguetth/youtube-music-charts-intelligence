"""
Browser Lifecycle
============================================================================
Dependency verification, Chromium launch, persistent-profile handling and
deterministic teardown.

The persistent profile is the primary anti-captcha measure: Google trusts the
accumulated cookies and consent state. It is never discarded automatically;
``--wipe-profile`` is the explicit, manual reset path.

Features
--------
- Preflight check for the Playwright package and Chromium build.
- Headed-by-default launch with ``--headless=new`` fallback.
- Persistent profile with stale-lock cleanup, or an ephemeral context.
- Proxy injection per retry, with shared context options.
- Guaranteed context/browser teardown via an async context manager.

Dependencies
------------
- Internal: config, utils.locking.
- External: playwright.async_api, contextlib, subprocess (stdlib).
- Downstream: core.downloader, __main__.

Requirements
------------
- Python 3.10+
- Playwright and a Chromium build (installed by the operator, not at runtime).

Notes
-----
- On local Linux the module never runs ``pip install``; PEP 668 environments
  would break, and the virtualenv belongs to the operator.
- ``show_browser`` maps to headed mode; headless sessions are challenged far
  more often, which is why headed is the default.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional, Tuple

from ..config import (
    BROWSER_PROFILE_DIR,
    DEFAULT_ACCEPT,
    DEFAULT_ACCEPT_LANGUAGE,
    IS_LINUX,
    IS_LOCAL,
    LOCAL_TIMEZONE,
    USER_AGENT,
    get_browser_args,
)
from ..utils.locking import cleanup_browser_locks

log = logging.getLogger("youtube_charts")

# ============================================================================
# CONSTANTS
# ============================================================================
ANTI_DETECTION_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
"""

# Playwright surfaces launch failures as generic messages; only these indicate
# that retrying without the profile can help.
_LAUNCH_ERROR_SIGNATURES = (
    "connection closed while reading",
    "target page, context or browser has been closed",
    "targetclosederror",
    "browser has been closed",
    "failed to launch",
    "failed to connect",
    "protocol error",
    "playwright process did not close cleanly",
)


# ============================================================================
# DEPENDENCY VERIFICATION
# ============================================================================
def is_browser_launch_error(error: BaseException) -> bool:
    """True when the failure happened while starting the browser process."""
    message = str(error).lower()
    return any(signature in message for signature in _LAUNCH_ERROR_SIGNATURES)


def ensure_playwright_available() -> bool:
    """Verify the Playwright package and Chromium build.

    On local Linux the script never installs anything: the virtualenv and the
    system packages are owned by the operator, and ``pip install`` at runtime
    breaks PEP 668 environments.
    """
    log.info("Checking Playwright availability")
    if importlib.util.find_spec("playwright") is None:
        if IS_LINUX and IS_LOCAL:
            log.error("Playwright is not installed in this virtualenv")
            log.error("Activate the venv and run: pip install -r requirements.txt")
            log.error("Then run: python -m playwright install chromium --with-deps")
            return False
        log.info("Playwright is missing, installing with pip")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.error("pip install playwright failed: %s", result.stderr[-2000:])
            return False
        log.info("Playwright installed")

    dry_run = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
        capture_output=True,
        text=True,
    )
    if dry_run.returncode == 0:
        log.info("Chromium build is installed")
        return True

    if IS_LINUX and IS_LOCAL:
        log.error("The Playwright Chromium build is missing")
        log.error("Run inside the venv: python -m playwright install chromium --with-deps")
        return False

    log.info("Installing Chromium")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        log.info("Chromium installed")
        return True

    log.error("Chromium installation failed: %s", result.stderr[-2000:])
    return False


# ============================================================================
# PROFILE MANAGEMENT
# ============================================================================
def wipe_browser_profile() -> bool:
    """Delete the persistent profile. Manual, opt-in, and destructive.

    A fresh profile loses the trust Google accumulated, so the next run will
    most likely face a captcha. Never call this from the retry loop.
    """
    if not BROWSER_PROFILE_DIR.exists():
        return False
    try:
        shutil.rmtree(BROWSER_PROFILE_DIR)
        log.warning("Persistent profile deleted: %s", BROWSER_PROFILE_DIR)
        log.warning("Expect a captcha on the next run: the profile is new")
        return True
    except Exception as exc:
        log.error("Could not delete %s: %s", BROWSER_PROFILE_DIR, exc)
        return False


# ============================================================================
# CONTEXT OPTIONS
# ============================================================================
def _context_options(
    proxy: Optional[Dict[str, str]] = None,
    accept_downloads: bool = True,
) -> Dict[str, Any]:
    """Options shared by persistent and ephemeral contexts."""
    options: Dict[str, Any] = {
        "accept_downloads": accept_downloads,
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": USER_AGENT,
        "locale": "en-US",
        "timezone_id": LOCAL_TIMEZONE,
        "extra_http_headers": {
            "Accept-Language": DEFAULT_ACCEPT_LANGUAGE,
            "Accept": DEFAULT_ACCEPT,
            "Referer": "https://charts.youtube.com/",
        },
    }
    if proxy:
        options["proxy"] = proxy
        log.info("Routing browser traffic through proxy %s", proxy["server"])
    return options


def _resolve_headless(show_browser: bool) -> bool:
    """Headless only when requested, or when there is no display server."""
    if not show_browser:
        return True
    if IS_LINUX and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        log.warning("--show-browser requested without DISPLAY/WAYLAND_DISPLAY")
        log.warning("Falling back to headless; run from a desktop session instead")
        return True
    return False


# ============================================================================
# SESSION
# ============================================================================
@asynccontextmanager
async def browser_session(
    show_browser: bool,
    use_chrome: bool,
    keep_profile: bool,
    proxy: Optional[Dict[str, str]] = None,
) -> AsyncIterator[Tuple[Any, Any]]:
    """Yield ``(context, page)`` and always tear the browser down.

    ``show_browser`` maps directly to headed mode: headless Chrome is far more
    likely to be challenged, so the default for local runs is headed.
    ``proxy`` is the rotation unit between retries.
    """
    from playwright.async_api import async_playwright

    headless = _resolve_headless(show_browser)
    browser_args = get_browser_args()
    if headless and "--headless=new" not in browser_args:
        browser_args.append("--headless=new")
        log.info("Headless mode uses --headless=new to reduce fingerprinting")

    async with async_playwright() as playwright:
        browser = None
        context = None
        try:
            if keep_profile and IS_LOCAL:
                log.info("Using persistent profile: %s", BROWSER_PROFILE_DIR)
                BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
                cleanup_browser_locks()

                launch_kwargs: Dict[str, Any] = {
                    "headless": headless,
                    "args": browser_args,
                    **_context_options(proxy),
                }
                if use_chrome:
                    launch_kwargs["channel"] = "chrome"
                    log.info("Using installed Google Chrome (channel=chrome)")
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(BROWSER_PROFILE_DIR),
                    **launch_kwargs,
                )
            else:
                launch_kwargs = {"headless": headless, "args": browser_args}
                if use_chrome:
                    launch_kwargs["channel"] = "chrome"
                    log.info("Using installed Google Chrome (channel=chrome)")
                browser = await playwright.chromium.launch(**launch_kwargs)
                context = await browser.new_context(**_context_options(proxy))

            await context.add_init_script(ANTI_DETECTION_SCRIPT)

            # A persistent context restores the previous session's tab.
            if keep_profile and IS_LOCAL and context.pages:
                page = context.pages[0]
            else:
                page = await context.new_page()

            try:
                page.set_default_timeout(60_000)
            except Exception:
                pass

            yield context, page
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass
