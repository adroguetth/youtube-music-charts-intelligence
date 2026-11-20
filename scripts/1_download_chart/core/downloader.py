"""
Download Orchestration
============================================================================
Runs every extraction strategy against the candidate chart URLs until one
produces a complete enough result to persist.

Strategy order per URL, cheapest and most authoritative first:

1. Official CSV download button (when present) - complete and correctly typed.
2. ``youtubei/v1/browse`` - the internal endpoint behind the site.
3. DOM + shadow DOM extractor.
4. Embedded JSON (``__NEXT_DATA__`` / ``ytInitialData``).
5. ``body.innerText`` table heuristic.
6. Captured network JSON payloads.

Any strategy that yields at least ``MIN_ROWS_PRIMARY`` rows ends the run; a
partial result never overwrites the CSV.

Features
--------
- Warm-up navigation before the chart request.
- Consent handling in English and Spanish.
- Automatic challenge recovery with no human interaction.
- Debug artifacts preserved whenever extraction fails.
- Direct HTTP fallback through ``urllib`` when Playwright is unavailable.

Dependencies
------------
- Internal: config, persistence.csv_handler, core.browser, core.captcha,
  core.extractor.
- External: playwright (through core.browser), urllib, re (stdlib).
- Downstream: __main__.

Requirements
------------
- Python 3.10+
- A local display for headed Chrome.

Notes
-----
- GitHub Actions is rejected explicitly: the profile and display assumptions
  only hold on a physical host.
- ``ChallengeDetected`` is propagated, never swallowed, so the caller can
  rotate egress.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import logging
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import (
    DEFAULT_ACCEPT,
    DEFAULT_ACCEPT_LANGUAGE,
    IS_GITHUB_ACTIONS,
    LATEST_CSV,
    LOGS_DIR,
    MIN_ROWS_PRIMARY,
    MIN_ROWS_SECONDARY,
    USER_AGENT,
    ensure_directories,
    get_chart_urls,
)
from ..persistence.csv_handler import save_rows_to_csv
from .browser import browser_session
from .captcha import (
    ChallengeDetected,
    attempt_challenge_escape,
    detect_captcha,
    wait_for_chart,
)
from .extractor import (
    extract_rows_from_yt_json,
    extract_via_dom,
    extract_via_inner_text,
    page_text_with_shadow,
    parse_next_data,
    parse_yt_initial_data,
    save_debug_artifacts,
    try_youtubei_browse,
)

log = logging.getLogger("youtube_charts")

# ============================================================================
# CONSTANTS
# ============================================================================
CHART_RENDER_TIMEOUT = 25.0
WARM_UP_URL = "https://charts.youtube.com/"

CONSENT_LABELS = (
    r"Accept all",
    r"Reject all",
    r"Aceptar todo",
    r"Rechazar todo",
    r"Accept",
    r"Aceptar",
)

DOWNLOAD_BUTTON_PATTERNS = (r"download", r"descargar", r"export", r"csv")

DOWNLOAD_BUTTON_SELECTORS = (
    'button[aria-label*="download" i]',
    'a[aria-label*="download" i]',
    '[aria-label*="Download" i]',
    'button[title*="download" i]',
    'a[download]',
)

STATIC_ASSET_MARKERS = (
    ".js",
    ".css",
    "fonts.gstatic",
    "googletagmanager",
    "google-analytics",
    "feedback",
    "g/collect",
)


# ============================================================================
# PAGE PREPARATION
# ============================================================================
async def _accept_consent(page) -> None:
    """Dismiss the cookie/consent interstitial when it is shown."""
    for label in CONSENT_LABELS:
        try:
            button = page.get_by_role("button", name=re.compile(label, re.I))
            if await button.count() > 0:
                await button.first.click(timeout=3000)
                log.info("Consent dismissed via: %s", label)
                await page.wait_for_timeout(1500)
                return
        except Exception:
            continue


async def _warm_up(page) -> None:
    """Prime the session on the site root before requesting a chart.

    Landing on the chart directly from a cold profile is the single most common
    trigger for the interstitial: the root navigation sets the consent cookie
    and the session identifiers that the chart request then reuses.
    """
    try:
        await page.goto(WARM_UP_URL, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2000)
        await _accept_consent(page)
        log.info("Warm-up navigation completed")
    except Exception as exc:
        log.info("Warm-up navigation failed (ignored): %s", exc)


async def _scroll_page(page, steps: int = 5, delta: int = 900) -> None:
    """Trigger lazy rendering, then return to the top for stable screenshots."""
    for _ in range(steps):
        try:
            await page.evaluate(f"window.scrollBy(0, {delta})")
        except Exception:
            pass
        await page.wait_for_timeout(1200)
    try:
        await page.evaluate("window.scrollTo(0,0)")
    except Exception:
        pass
    await page.wait_for_timeout(1000)


# ============================================================================
# DIAGNOSTICS AND NETWORK CAPTURE
# ============================================================================
async def _log_page_structure(page) -> None:
    """Log element counts and shadow hosts; the layout changes without notice."""
    try:
        structure = await page.evaluate(
            """() => {
                const all = document.querySelectorAll('*');
                const counts = {};
                let shadowHosts = 0;
                const iframes = document.querySelectorAll('iframe').length;
                const ytmc = [];
                for (const el of all) {
                    const tag = el.tagName.toLowerCase();
                    counts[tag] = (counts[tag] || 0) + 1;
                    if (el.shadowRoot) shadowHosts++;
                    if (tag.startsWith('ytmc')) {
                        ytmc.push(tag + ' textLen=' + (el.innerText || '').length);
                    }
                }
                const top = Object.entries(counts)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 15)
                    .map(([k, v]) => k + ':' + v)
                    .join(', ');
                return {total: all.length, shadowHosts, iframes, top, ytmc: ytmc.slice(0, 20)};
            }"""
        )
        log.info(
            "Structure: total=%s shadowHosts=%s iframes=%s top=[%s] ytmc=%s",
            structure.get("total"),
            structure.get("shadowHosts"),
            structure.get("iframes"),
            structure.get("top"),
            structure.get("ytmc"),
        )
    except Exception as exc:
        log.info("Structure diagnostics failed: %s", exc)


async def _log_shadow_diagnostics(page) -> None:
    """Log the rendered shadow text, which is the real page content here."""
    try:
        text = await page_text_with_shadow(page)
        log.info(
            "Shadow diagnostics: len=%d snippet=%s",
            len(text),
            text[:500].replace("\n", " | "),
        )
        title = await page.evaluate("() => document.title")
        log.info(
            "Page diagnostics: title=%s final_url=%s text_len=%d",
            title,
            page.url,
            len(text),
        )
        if len(text) < 500:
            log.warning(
                "Rendered text is very short (%d). The page may be empty, "
                "blocked or challenged; run with --show-browser --use-chrome "
                "to inspect and solve it.",
                len(text),
            )
    except Exception as exc:
        log.info("Shadow diagnostics failed: %s", exc)


def _capture_network(page) -> Tuple[List[Any], List[str]]:
    """Record response URLs and JSON bodies for the network fallback."""
    payloads: List[Any] = []
    urls: List[str] = []

    async def on_response(response) -> None:
        try:
            content_type = (response.headers.get("content-type") or "").lower()
            url = response.url or ""
            urls.append(f"{response.status} {url} ct={content_type}")
            if not (
                "json" in content_type
                or "text" in content_type
                or "javascript" in content_type
            ):
                return
            try:
                payloads.append(await response.json())
            except Exception:
                try:
                    text = await response.text()
                    if len(text) > 200 and (
                        "TopSongs" in text
                        or "Weekly views" in text
                        or "chart" in text.lower()[:2000]
                    ):
                        payloads.append({"_raw_text": text[:20000], "_url": url})
                except Exception:
                    pass
        except Exception:
            pass

    page.on("response", on_response)
    return payloads, urls


# ============================================================================
# DOWNLOAD STRATEGIES
# ============================================================================
async def _try_download_button(page, filename: Path) -> Optional[Path]:
    """Click the official download control, if the page exposes one.

    Candidates are resolved by accessible role first, then by attribute, so a
    tag or icon change does not break the strategy.
    """
    candidates = []
    for pattern in DOWNLOAD_BUTTON_PATTERNS:
        try:
            locator = page.get_by_role("button", name=re.compile(pattern, re.I))
            if await locator.count() > 0:
                candidates.append(locator.first)
        except Exception:
            pass
    for selector in DOWNLOAD_BUTTON_SELECTORS:
        try:
            locator = page.locator(selector)
            if await locator.count() > 0:
                candidates.append(locator.first)
        except Exception:
            pass

    for button in candidates:
        try:
            if not await button.is_visible():
                try:
                    await button.scroll_into_view_if_needed(timeout=3000)
                except Exception:
                    pass
            async with page.expect_download(timeout=20_000) as download_info:
                await button.click(timeout=5000)
            download = await download_info.value
            await download.save_as(filename)
            if filename.exists() and filename.stat().st_size > 1000:
                log.info("Download button produced %s", filename)
                return filename
        except Exception as exc:
            log.info("Download button candidate failed: %s", str(exc)[:200])
            continue
    return None


def _log_network_capture(urls: List[str], page_url: str) -> None:
    """Log captured responses and dump the full list for post-mortem analysis."""
    try:
        log.info("Network captured: %d responses", len(urls))
        for entry in urls[:15]:
            log.info("  net: %s", entry[:300])

        interesting = [
            entry
            for entry in urls
            if not any(marker in entry for marker in STATIC_ASSET_MARKERS)
        ]
        log.info("Network interesting (static assets excluded): %d", len(interesting))
        for entry in interesting[:40]:
            log.info("  net-interesting: %s", entry[:500])

        parts = page_url.split("/")
        name = f"red_{parts[-2]}_{parts[-1]}_{datetime.now():%Y%m%d_%H%M%S}.txt"
        target = LOGS_DIR / "debug" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(urls), encoding="utf-8")
        log.info("Full network log written to %s", target)
    except Exception:
        pass


# ============================================================================
# PUBLIC API
# ============================================================================
def download_via_http(chart: str = "TopSongs", country: str = "global") -> Optional[Path]:
    """Fetch the page without a browser and parse the embedded JSON.

    Fast path for hosts without a usable display; usually blocked or empty when
    Google expects a session, in which case the Playwright path takes over.

    Parameters
    ----------
    chart : str, optional
        Chart identifier, by default ``"TopSongs"``.
    country : str, optional
        Country code, by default ``"global"``.

    Returns
    -------
    Path or None
        Path to ``latest_chart.csv`` when enough rows were parsed, else ``None``.

    Notes
    -----
    Two embedded payloads are attempted, ``ytInitialData`` first and
    ``__NEXT_DATA__`` second; the larger result wins.
    """
    for url in get_chart_urls(chart, country):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": DEFAULT_ACCEPT_LANGUAGE,
                    "Accept": DEFAULT_ACCEPT,
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                html = response.read().decode("utf-8", errors="ignore")

            rows = parse_yt_initial_data(html)
            if len(rows) < MIN_ROWS_PRIMARY:
                next_rows = parse_next_data(html)
                if len(next_rows) > len(rows):
                    rows = next_rows
                    log.info("HTTP: __NEXT_DATA__ yielded %d rows", len(rows))

            if len(rows) >= MIN_ROWS_PRIMARY:
                ensure_directories()
                return save_rows_to_csv(rows, LATEST_CSV)
            log.info("HTTP direct extraction insufficient on %s (%d rows)", url, len(rows))
        except Exception as exc:
            log.info("HTTP direct request failed on %s: %s", url, exc)
    return None


async def download_youtube_charts(
    chart: str = "TopSongs",
    country: str = "global",
    show_browser: bool = False,
    use_chrome: bool = False,
    keep_profile: bool = True,
    proxy: Optional[Dict[str, str]] = None,
) -> Optional[Path]:
    """Run every extraction strategy against the candidate chart URLs.

    Parameters
    ----------
    chart : str, optional
        Chart identifier, by default ``"TopSongs"``.
    country : str, optional
        Country code, by default ``"global"``.
    show_browser : bool, optional
        Request a headed browser, by default ``False``.
    use_chrome : bool, optional
        Use installed Google Chrome instead of bundled Chromium.
    keep_profile : bool, optional
        Reuse ``.browser-profile`` instead of an ephemeral context.
    proxy : dict or None, optional
        Playwright proxy settings for this attempt.

    Returns
    -------
    Path or None
        Path to ``latest_chart.csv`` when a strategy succeeded, else ``None``.

    Raises
    ------
    ChallengeDetected
        When the automatic recovery ladder cannot clear the challenge.

    Notes
    -----
    A detected challenge is never handed to a human: the recovery ladder reloads
    the document and, if needed, bounces through the site root. When it still
    fails, ``ChallengeDetected`` lets the caller rotate egress and retry.
    """
    if IS_GITHUB_ACTIONS:
        log.error("This build runs on local hosts only, not on GitHub Actions")
        return None

    try:
        import playwright  # noqa: F401
    except ImportError:
        log.error("Playwright is not installed")
        return None

    log.info("Downloading YouTube Charts %s / %s with Playwright", chart, country)
    ensure_directories()

    async with browser_session(
        show_browser, use_chrome, keep_profile, proxy
    ) as (_, page):
        captured_json, captured_urls = _capture_network(page)
        await _warm_up(page)

        for url in get_chart_urls(chart, country):
            log.info("Navigating to %s", url)
            try:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=90_000)
                except Exception as exc:
                    log.info("goto domcontentloaded failed, continuing: %s", exc)
                await page.wait_for_timeout(3000)

                if not await wait_for_chart(page, timeout_s=CHART_RENDER_TIMEOUT):
                    if await detect_captcha(page):
                        if not await attempt_challenge_escape(page, url):
                            raise ChallengeDetected(url)
                    else:
                        log.warning(
                            "Chart did not render and no challenge was detected; "
                            "running the extractors anyway"
                        )

                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await page.wait_for_timeout(1500)

                await _log_page_structure(page)
                await _log_shadow_diagnostics(page)
                await _accept_consent(page)
                await _scroll_page(page)

                # 1) Official download button.
                try:
                    downloaded = await _try_download_button(page, LATEST_CSV)
                    if downloaded is not None:
                        try:
                            with open(
                                downloaded, "r", encoding="utf-8", errors="ignore"
                            ) as handle:
                                lines = handle.readlines()
                            if len(lines) >= MIN_ROWS_PRIMARY + 1:
                                log.info(
                                    "CSV from download button: %d lines - using it",
                                    len(lines),
                                )
                                return downloaded
                            log.warning(
                                "CSV from download button incomplete: %d lines; "
                                "falling back to extractors",
                                len(lines),
                            )
                        except Exception:
                            pass
                except Exception as exc:
                    log.info("Download button failed on %s: %s", url, exc)

                # 2) Internal youtubei endpoint.
                try:
                    youtubei_rows = await try_youtubei_browse(page, chart, country)
                    if len(youtubei_rows) >= MIN_ROWS_SECONDARY:
                        log.info(
                            "youtubei extraction on %s: %d rows - using it",
                            url,
                            len(youtubei_rows),
                        )
                        return save_rows_to_csv(youtubei_rows, LATEST_CSV)
                except Exception as exc:
                    log.warning("youtubei failed on %s: %s", url, exc)

                # 3) DOM and shadow DOM.
                rows = await extract_via_dom(page)
                log.info("DOM extraction on %s: %d rows", url, len(rows))

                # 3b) Embedded JSON islands.
                if len(rows) < MIN_ROWS_PRIMARY:
                    try:
                        html = await page.content()
                        next_rows = parse_next_data(html)
                        log.info(
                            "__NEXT_DATA__ extraction on %s: %d rows",
                            url,
                            len(next_rows),
                        )
                        if len(next_rows) >= MIN_ROWS_PRIMARY:
                            rows = next_rows
                        else:
                            yt_rows = parse_yt_initial_data(html)
                            log.info(
                                "ytInitialData extraction on %s: %d rows",
                                url,
                                len(yt_rows),
                            )
                            if len(yt_rows) > len(rows):
                                rows = yt_rows
                    except Exception as exc:
                        log.info("Embedded JSON parsing failed: %s", exc)

                # 3c) Flat text fallback. Its rows are frequently shifted; the
                # reassembler repairs them, but the download button is better.
                if len(rows) < MIN_ROWS_SECONDARY:
                    try:
                        text_rows = await extract_via_inner_text(page)
                        log.info(
                            "innerText extraction on %s: %d rows", url, len(text_rows)
                        )
                        if len(text_rows) > len(rows):
                            rows = text_rows
                    except Exception as exc:
                        log.info("innerText extraction failed: %s", exc)

                # 3d) Preserve evidence before moving on.
                if len(rows) < MIN_ROWS_SECONDARY:
                    await save_debug_artifacts(page, url, tag="zero_rows")

                _log_network_capture(captured_urls, url)

                if len(rows) >= MIN_ROWS_PRIMARY:
                    return save_rows_to_csv(rows, LATEST_CSV)

                # 4) Captured network payloads.
                network_rows: List[Dict[str, Any]] = []
                seen_videos: set = set()
                for payload in captured_json:
                    network_rows.extend(
                        extract_rows_from_yt_json(payload, seen_videos)
                    )
                log.info("Network extraction: %d rows", len(network_rows))
                if len(network_rows) >= MIN_ROWS_PRIMARY:
                    return save_rows_to_csv(network_rows, LATEST_CSV)

                log.warning(
                    "No usable chart extracted from %s; trying next URL", url
                )
            except ChallengeDetected:
                raise
            except Exception as exc:
                log.warning("Error on %s: %s", url, exc)
                continue

        log.error("Could not download the chart from any candidate URL")
        return None
