"""
Automatic Challenge Detection and Recovery
============================================================================
Detection and automatic recovery for the reCAPTCHA interstitial that
charts.youtube.com serves to untrusted sessions.

The challenge is a cross-origin reCAPTCHA iframe nested inside shadow roots:
``document.querySelectorAll('iframe[src*=recaptcha]')`` never sees it and
``body.innerText`` is empty on this Polymer page. Detection therefore relies on
Playwright frames, Playwright locators (which pierce shadow DOM) and a deep JS
walk.

There is no human in the loop. A detected challenge triggers an automatic
recovery ladder (reload, then a bounce through the site root) and, if it
survives, the caller rotates egress and retries with backoff.

Features
--------
- Multi-signal detection: frames, shadow-piercing locators, deep JS walk, text.
- Layout-size discrimination so 1px background iframes are ignored.
- Two-rung automatic recovery without user interaction.
- Explicit ``ChallengeDetected`` signal consumed by the retry loop.

Dependencies
------------
- Internal: core.extractor (shadow text).
- External: asyncio, logging, time (stdlib).
- Downstream: core.downloader, __main__.

Requirements
------------
- Python 3.10+
- Playwright (used through the caller's page object).

Notes
-----
- Solving a reCAPTCHA programmatically is not attempted. The reliable levers
  are a trusted profile, a headed browser, a warm session and a fresh IP.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time

from .extractor import page_text_with_shadow

log = logging.getLogger("youtube_charts")


# ============================================================================
# JAVASCRIPT PROBE
# ============================================================================
JS_CAPTCHA_PROBE = """() => {
    const SKIP = new Set(['STYLE','SCRIPT','NOSCRIPT','TEMPLATE','LINK','META','HEAD']);
    let found = false;
    let foundText = '';
    function walk(root) {
        if (!root || found) return;
        const els = root.querySelectorAll ? root.querySelectorAll('*') : [];
        for (const el of els) {
            if (found) break;
            // reCAPTCHA iframe at any nesting level.
            if (el.tagName === 'IFRAME') {
                const s = (el.getAttribute('src') || '').toLowerCase();
                if (s.includes('recaptcha') || s.includes('api2') || s.includes('bframe')) {
                    const r = el.getBoundingClientRect ? el.getBoundingClientRect() : {width:0,height:0};
                    if (r.width >= 200 && r.height >= 80) { found = true; foundText = 'iframe:'+s.slice(0,80); break; }
                }
            }
            const cls = (el.className || '').toString().toLowerCase();
            const id = (el.id || '').toLowerCase();
            if (cls.includes('recaptcha') || id.includes('recaptcha')) {
                const r = el.getBoundingClientRect ? el.getBoundingClientRect() : {width:0,height:0};
                if (r.width >= 200 && r.height >= 80) { found = true; foundText = 'class/id recaptcha'; break; }
            }
            if (el.shadowRoot) walk(el.shadowRoot);
        }
        // Challenge text rendered directly in this root.
        try {
            const iter = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
            let n;
            while (n = iter.nextNode()) {
                const p = n.parentElement;
                if (!p || SKIP.has(p.tagName)) continue;
                const v = (n.nodeValue || '').toLowerCase();
                if (v.includes('select all images') || v.includes('click verify') || v.includes("i'm not a robot") || v.includes('no soy un robot')) {
                    found = true; foundText = 'text:'+v.slice(0,80); break;
                }
            }
        } catch(e) {}
    }
    walk(document);
    return found ? foundText : '';
}"""

# ============================================================================
# CONTENT AND SIGNAL CONSTANTS
# ============================================================================
CHALLENGE_TEXTS = (
    "Select all images",
    "Click verify",
    "I'm not a robot",
    "No soy un robot",
)

CHART_HEADERS = ("weekly top songs", "weekly top artists")
CHART_METRICS = ("weekly views", "rank")


# ============================================================================
# EXCEPTIONS AND CONTENT CHECKS
# ============================================================================
class ChallengeDetected(RuntimeError):
    """Raised when an anti-bot challenge blocks the chart after recovery."""

    def __init__(self, url: str, detail: str = ""):
        self.url = url
        self.detail = detail
        message = f"captcha challenge blocked {url}"
        if detail:
            message = f"{message} ({detail})"
        super().__init__(message)


def has_chart_content(text: str) -> bool:
    """True when the rendered text contains the chart header and its metrics."""
    lowered = (text or "").lower()
    return any(marker in lowered for marker in CHART_HEADERS) and any(
        marker in lowered for marker in CHART_METRICS
    )


# ============================================================================
# DETECTION
# ============================================================================
async def wait_for_chart(
    page, timeout_s: float = 20.0, poll_s: float = 1.0
) -> bool:
    """Poll the rendered shadow text until the chart appears or time runs out."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if has_chart_content(await page_text_with_shadow(page)):
                return True
        except Exception:
            pass
        await asyncio.sleep(poll_s)
    return False


async def detect_captcha(page) -> bool:
    """True when a visible captcha is present and the chart is not rendered."""
    try:
        shadow_text = await page_text_with_shadow(page)
        lowered = (shadow_text or "").lower()

        if has_chart_content(shadow_text):
            return False
        if len(shadow_text) > 2000 and (
            "weekly top songs" in lowered or "top songs" in lowered
        ):
            return False

        # Playwright frames are the most reliable signal: the reCAPTCHA iframe
        # is cross-origin, but its URL is still listed here.
        try:
            for frame in page.frames:
                frame_url = (frame.url or "").lower()
                if (
                    "recaptcha" in frame_url
                    or "google.com/recaptcha" in frame_url
                    or "/api2/" in frame_url
                    or "bframe" in frame_url
                    or "/anchor" in frame_url
                ):
                    log.info("Captcha detected via frame: %s", frame.url[:200])
                    return True
        except Exception:
            pass

        # Locators pierce shadow DOM, unlike document.querySelectorAll.
        try:
            locator = page.locator(
                'iframe[src*="recaptcha"], iframe[src*="google.com/recaptcha"],'
                ' iframe[src*="api2"]'
            )
            if await locator.count() > 0:
                for index in range(await locator.count()):
                    try:
                        box = await locator.nth(index).bounding_box(timeout=1000)
                        if (
                            box
                            and box.get("width", 0) >= 200
                            and box.get("height", 0) >= 80
                        ):
                            log.info(
                                "Captcha detected via visible iframe: %sx%s",
                                box.get("width"),
                                box.get("height"),
                            )
                            return True
                    except Exception:
                        continue
        except Exception:
            pass

        # Deep walk over light and shadow trees, including layout size checks
        # so background 1px iframes are not reported as challenges.
        try:
            marker = await page.evaluate(JS_CAPTCHA_PROBE)
            if marker:
                log.info("Captcha detected via deep walk: %s", marker)
                return True
        except Exception as exc:
            log.info("Captcha deep-walk probe failed: %s", exc)

        try:
            for text in CHALLENGE_TEXTS:
                locator = page.get_by_text(text, exact=False)
                if await locator.count() > 0:
                    log.info("Captcha detected via visible text: %s", text)
                    return True
        except Exception:
            pass

        return False
    except Exception as exc:
        log.info("Captcha detection failed: %s", exc)
        return False


# ============================================================================
# AUTOMATIC RECOVERY
# ============================================================================
async def _reload_and_check(page, settle_s: float) -> bool:
    """Recovery rung 1: reload the same URL with a fresh challenge token."""
    try:
        await page.reload(wait_until="domcontentloaded", timeout=60_000)
    except Exception as exc:
        log.info("Reload during recovery failed: %s", exc)
        return False
    await asyncio.sleep(settle_s)
    return await wait_for_chart(page, timeout_s=10.0)


async def _root_cycle_and_check(
    page, url: str, settle_s: float, root_url: str = "https://charts.youtube.com/"
) -> bool:
    """Recovery rung 2: bounce through the site root, then retry the chart.

    The interstitial is issued per navigation and its token is tied to the
    session's last top-level document. A root navigation re-issues consent and
    session state, so the subsequent chart request is usually served normally.
    """
    try:
        await page.goto(root_url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(settle_s)
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except Exception as exc:
        log.info("Root cycle during recovery failed: %s", exc)
        return False
    await asyncio.sleep(settle_s)
    return await wait_for_chart(page, timeout_s=15.0)


async def attempt_challenge_escape(
    page, url: str, settle_s: float = 8.0
) -> bool:
    """Run the automatic recovery ladder; no human is ever involved.

    Rung 1 reloads the document, which clears half-rendered interstitials.
    Rung 2 re-enters from the site root, which re-issues the session state the
    challenge token is bound to. If both fail, the caller rotates egress and
    retries with backoff; the profile is left untouched.
    """
    log.warning("Challenge detected at %s; attempting automatic recovery", url)
    if await _reload_and_check(page, settle_s):
        log.info("Challenge cleared after reload; resuming extraction")
        return True
    log.info("Reload did not clear the challenge; retrying via the site root")
    if await _root_cycle_and_check(page, url, settle_s):
        log.info("Challenge cleared after root cycle; resuming extraction")
        return True
    return False
