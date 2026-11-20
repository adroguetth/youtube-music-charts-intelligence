"""
Chart Extraction Strategies
============================================================================
Independent extractors for the chart payload: DOM and shadow DOM walking,
embedded JSON (``__NEXT_DATA__``, ``ytInitialData``), the internal
``youtubei/v1/browse`` endpoint, and captured network JSON.

Each strategy returns raw dictionaries; normalization happens exactly once, at
the persistence boundary (``models.chart.ChartEntry``).

Features
--------
- Shadow-DOM-aware DOM extractor with video-link pairing.
- Paid and organic row parsing shared across JSON shapes.
- Two-pass extraction: structured rows first, text heuristic second.
- Debug artifacts (HTML, text, screenshot) when extraction fails.

Dependencies
------------
- Internal: config, utils.parsers.
- External: json, re, datetime, pathlib (stdlib); Playwright page object.
- Downstream: core.downloader, core.captcha (shadow text).

Requirements
------------
- Python 3.10+

Notes
-----
- JavaScript blobs are plain functions evaluated with ``page.evaluate``; they
  must stay dependency-free and ES5-compatible for older Chromium builds.
- Debug artifacts are written to ``logs/debug`` only on failure, never on the
  happy path.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import DEBUG_DIR, USER_AGENT
from ..utils.parsers import clean_text

log = logging.getLogger("youtube_charts")


# ============================================================================
# JAVASCRIPT EXTRACTORS
# ============================================================================
# Walks the light and shadow trees, pairs every video link with its row text and
# parses rank, title, artist, views, growth, previous rank and periods. Both
# passes always run: video links alone miss rows rendered as custom containers,
# and containers alone miss rows without a parseable label.
JS_EXTRACT_DOM = r"""
() => {
  const rows = [];
  const seen = new Set();
  const SKIP = new Set(['STYLE','SCRIPT','NOSCRIPT','TEMPLATE','LINK','META','HEAD']);
  const BLOCK_TITLES = new Set(['release date','release dates','last week','weekly views','weekly top songs','weekly top artists','top songs','top artists','views','rank','artist','track name','new','same','chart']);
  const DATE_RE = /^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2},\s*\d{4}$/i;
  const DATE_RE2 = /^\d{1,2}\/\d{1,2}\/\d{4}$/;
  function getText(el) {
    try {
      let s = el.innerText || '';
      if (s && s.trim()) return s.trim();
      let parts = [];
      for (const n of el.childNodes || []) {
        if (n.nodeType === 3) { const v = (n.nodeValue||'').trim(); if (v) parts.push(v); }
        else if (n.nodeType === 1 && !SKIP.has(n.tagName)) { const v = getText(n); if (v) parts.push(v); }
      }
      return parts.join('\n').trim();
    } catch(e) { return ''; }
  }
  function collectAll(root, out, depth) {
    if (!root || depth > 8) return;
    const els = root.querySelectorAll ? root.querySelectorAll('*') : [];
    for (const el of els) {
      out.push(el);
      if (el.shadowRoot) collectAll(el.shadowRoot, out, depth+1);
    }
  }
  function findVideoIdIn(el) {
    // Look for a video id on the element itself and on its descendants.
    try {
      const html = el.outerHTML || '';
      let m = html.match(/v=([A-Za-z0-9_-]{11})/) || html.match(/youtu\.be\/([A-Za-z0-9_-]{11})/) || html.match(/\/vi\/([A-Za-z0-9_-]{11})\//) || html.match(/videoId["'\s:=]+([A-Za-z0-9_-]{11})/) || html.match(/data-video-id=["']([A-Za-z0-9_-]{11})/) || html.match(/watch\/([A-Za-z0-9_-]{11})/);
      if (m) return m[1];
      // Inspect anchors and thumbnails, light and shadow.
      const stack = [el];
      let guard = 0;
      while (stack.length && guard < 200) {
        guard++;
        const cur = stack.pop();
        if (!cur) continue;
        if (cur.tagName === 'A') {
          const h = cur.getAttribute('href') || '';
          let mm = h.match(/v=([A-Za-z0-9_-]{11})/) || h.match(/youtu\.be\/([A-Za-z0-9_-]{11})/);
          if (mm) return mm[1];
        }
        if (cur.tagName === 'IMG') {
          const s = cur.getAttribute('src') || cur.getAttribute('data-src') || '';
          let mm = s.match(/\/vi\/([A-Za-z0-9_-]{11})\//);
          if (mm) return mm[1];
        }
        if (cur.shadowRoot) stack.push(cur.shadowRoot);
        if (cur.querySelectorAll) {
          for (const c of cur.querySelectorAll('a, img')) stack.push(c);
          for (const c of cur.querySelectorAll('*')) { if (c.shadowRoot) stack.push(c.shadowRoot); }
        }
      }
    } catch(e) {}
    return '';
  }
  function isViewsLine(l, rankVal) {
    const s = l.trim();
    // "12,345,678", "12.3M", "850K", "1.1B", "45.2M views".
    if (/^[\d]{1,3}(,[\d]{3})+$/.test(s)) return true;
    if (/^[\d]+(\.[\d]+)?\s*[KMB]\s*(views|reproducciones|vistas)?$/i.test(s)) return true;
    if (/^[\d,.]+\s*[KMB]?\s*(views|reproducciones|vistas)$/i.test(s)) return true;
    // Large bare integer: not a rank, not a year.
    if (/^\d{4,}$/.test(s)) {
      const n = parseInt(s, 10);
      if (n > 1000 && n < 1000000000 && String(n) !== String(rankVal)) return true;
    }
    return false;
  }
  function parseRowLines(rawLines, rankHint) {
    // Drop metadata lines: "Release date" plus its value, bare dates, headers.
    let lines = [];
    for (let i=0;i<rawLines.length;i++) {
      let l = rawLines[i].trim();
      if (!l) continue;
      const ll = l.toLowerCase();
      if (ll === 'release date' || ll === 'release dates') {
        // Skip the value line that follows the label.
        if (i+1 < rawLines.length && (DATE_RE.test(rawLines[i+1].trim()) || DATE_RE2.test(rawLines[i+1].trim()))) i++;
        continue;
      }
      if (DATE_RE.test(l) || DATE_RE2.test(l)) continue;
      if (ll === 'weekly top songs' || ll === 'weekly top artists' || ll === 'weekly views' || ll === 'top songs') continue;
      lines.push(l);
    }
    if (lines.length < 3) return null;
    // Rank: first standalone integer in 1..100.
    let rank = rankHint || '';
    for (const l of lines) { if (/^\d{1,3}$/.test(l)) { const n = parseInt(l,10); if (n>=1 && n<=100) { rank = n; break; } } }
    // Views: the first line that parses as a view count.
    let viewsRaw = '';
    for (const l of lines) { if (isViewsLine(l, rank)) { viewsRaw = l; break; } }
    // Movement: NEW, arrows, "Same", "Up 2", "Down 1".
    let growth = '';
    for (const l of lines) {
      const ll = l.toLowerCase();
      if (/^new$/i.test(l) || /^[↑▲▼↓]\s*\d+/.test(l) || /^(up|down)\s*\d+/i.test(l) || /^same$/i.test(l) || /^[+-]\d+$/.test(l)) { growth = l; break; }
    }
    // Periods: "3 weeks", "1 week", "12 weeks on chart".
    let periods = '';
    for (const l of lines) { const m = l.match(/^(\d+)\s*(weeks?|periods?|semanas?)/i); if (m) { periods = m[1]; break; } }
    // Previous rank: "Last week 5", "Prev 5", "Last 5".
    let prevRank = '';
    for (const l of lines) { const m = l.match(/(?:last week|prev(?:ious)?(?: rank)?|last)\s*:?\s*(\d{1,3})/i); if (m) { prevRank = m[1]; break; } }
    // Title and artist: everything that is not a metric or a movement label.
    let cands = lines.filter(l => l !== String(rank) && l !== viewsRaw && l !== growth && l !== prevRank && !/^(\d+)\s*(weeks?|periods?)/i.test(l) && !/(?:last week|prev)/i.test(l) && !/^\d{1,3}$/.test(l));
    cands = cands.filter(l => l.length > 1);
    if (cands.length < 2) return null;
    let title = cands[0] || '';
    let artist = cands[1] || '';
    // Reject rows whose "title" is really a header or a date.
    if (BLOCK_TITLES.has(title.toLowerCase().trim())) return null;
    if (DATE_RE.test(title) || DATE_RE.test(artist)) return null;
    if (/^\d+$/.test(artist) && artist.length <= 3) return null;
    return {Rank: rank, 'Track Name': title, 'Artist Names': artist, Views: viewsRaw, 'Views Raw': viewsRaw, Growth: growth, 'Previous Rank': prevRank, 'Periods on Chart': periods};
  }
  const allEls = [];
  collectAll(document, allEls, 0);
  // Pass 1: anchors carrying a video id, resolved through the nearest container.
  for (const el of allEls) {
    if (el.tagName !== 'A') continue;
    const href = el.getAttribute('href') || '';
    let m = href.match(/v=([A-Za-z0-9_-]{11})/) || href.match(/youtu\.be\/([A-Za-z0-9_-]{11})/);
    let vid = m ? m[1] : '';
    if (!vid) {
      // The anchor may be href-less; the thumbnail in its container still holds the id.
      let container = el;
      for (let i=0;i<4;i++) { let p = container.parentNode; if (!p || p === document) break; if (p.nodeType===11) { container = p.host || container; continue; } container = p; }
      vid = findVideoIdIn(container);
    }
    if (!vid) continue;
    if (seen.has(vid)) continue;
    seen.add(vid);
    let container = el;
    for (let i=0;i<6;i++) {
      let p = container.parentNode;
      if (!p || p === document) break;
      if (p.nodeType === 11) { container = p.host || container; continue; }
      container = p;
      const txt = getText(container);
      if (txt && txt.split('\n').length >= 2 && txt.length > 20) break;
    }
    let text = getText(container) || getText(el);
    if (text.length > 1200) { text = getText(el); }
    let lines = text.split('\n').map(s=>s.trim()).filter(Boolean);
    let parsed = parseRowLines(lines, '');
    if (!parsed) continue;
    // aria-label is usually "Title - Artist" and beats the text heuristic.
    let aria = (el.getAttribute('aria-label') || '').trim();
    if (aria && aria.length > 2 && !BLOCK_TITLES.has(aria.toLowerCase())) {
      let parts = aria.split(' - ');
      if (parts.length >= 2) { parsed['Track Name'] = parts[0].trim(); parsed['Artist Names'] = parts.slice(1).join(' - ').trim(); }
      else if (parsed['Track Name'] === 'Release date') parsed['Track Name'] = aria;
    }
    parsed['YouTube URL'] = 'https://www.youtube.com/watch?v=' + vid;
    parsed['videoId'] = vid;
    rows.push(parsed);
  }
  // NOTE: an earlier revision returned early once pass 1 produced >= 20 rows,
  // which skipped pass 2 entirely. Pass 1 only sees anchors that expose a video
  // id, while Charts renders most rows as ytmc-chart-row containers that only
  // pass 2 parses. Both passes now always run and are merged below.
  // Pass 2: Polymer row containers, innermost only.
  for (const el of allEls) {
    const tag = (el.tagName||'').toLowerCase();
    const cls = (el.className||'').toString().toLowerCase();
    const isRow = tag === 'ytmc-chart-row' || tag === 'ytmc-v2-chart-row' || tag === 'ytmc-chart-item' || tag.includes('chart-row') || (tag.includes('chart') && tag.includes('row')) || el.getAttribute('role')==='row' || (cls.includes('chart-row'));
    if (!isRow) continue;
    // Skip parents that contain another row: each row must be counted once.
    let hasRowChild = false;
    try {
      for (const c of el.querySelectorAll('*')) {
        const ct = (c.tagName||'').toLowerCase();
        if (ct === 'ytmc-chart-row' || ct === 'ytmc-v2-chart-row' || ct.includes('chart-row')) { hasRowChild = true; break; }
        if (c.shadowRoot) {
          for (const sc of c.shadowRoot.querySelectorAll('*')) { const sct=(sc.tagName||'').toLowerCase(); if (sct.includes('chart-row')) { hasRowChild=true; break; } }
          if (hasRowChild) break;
        }
      }
    } catch(e) {}
    if (hasRowChild) continue;
    // Rows inside a detail/expand panel are metadata, not chart positions.
    let anc = el.parentNode;
    let inDetail = false;
    for (let i=0;i<5 && anc;i++) {
      const ac = ((anc.className||'').toString().toLowerCase() || '') + ' ' + ((anc.tagName||'').toLowerCase() || '');
      if (ac.includes('detail') || ac.includes('expand') || ac.includes('info-panel')) { inDetail = true; break; }
      anc = anc.parentNode; if (anc && anc.nodeType===11) anc = anc.host;
    }
    if (inDetail) continue;
    const txt = getText(el);
    if (!txt || txt.length < 15 || txt.length > 1200) continue;
    const lines = txt.split('\n').map(s=>s.trim()).filter(Boolean);
    if (lines.length < 3) continue;
    let parsed = parseRowLines(lines, '');
    if (!parsed) continue;
    // Resolve the video id from inside the row.
    let vid = findVideoIdIn(el);
    if (vid) { parsed['YouTube URL'] = 'https://www.youtube.com/watch?v=' + vid; parsed['videoId'] = vid; }
    const key = (parsed['Track Name']||'').toLowerCase() + '|' + (parsed['Artist Names']||'').toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push(parsed);
  }
  // Merge both passes. Rows with a video id win over label-only duplicates.
  const dedAll = new Map();
  for (const r of rows) {
    const vid = r['videoId'] || '';
    const k = vid ? ('vid:' + vid) : (('t:' + (r['Track Name']||'').toLowerCase()) + '|a:' + (r['Artist Names']||'').toLowerCase());
    if (!dedAll.has(k)) {
      dedAll.set(k, r);
    } else {
      const existing = dedAll.get(k);
      if (!existing['videoId'] && vid) {
        dedAll.set(k, r);
      }
    }
  }
  let finalOut = Array.from(dedAll.values());
  finalOut.sort((a,b)=> (a.Rank||999)-(b.Rank||999));
  return finalOut;
}
"""

JS_SHADOW_TEXT = """() => {
    let out = [];
    const SKIP = new Set(['STYLE','SCRIPT','NOSCRIPT','TEMPLATE','LINK','META','HEAD']);
    function walk(root) {
        if (!root) return;
        try {
            const iter = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
                acceptNode: (n) => {
                    const p = n.parentElement;
                    if (!p) return NodeFilter.FILTER_REJECT;
                    if (SKIP.has(p.tagName)) return NodeFilter.FILTER_REJECT;
                    return NodeFilter.FILTER_ACCEPT;
                }
            }, false);
            let n;
            while (n = iter.nextNode()) {
                const v = (n.nodeValue || '').trim();
                if (v && v.length < 500) out.push(v);
            }
        } catch(e) {}
        const els = root.querySelectorAll ? root.querySelectorAll('*') : [];
        for (const el of els) {
            if (el.shadowRoot) walk(el.shadowRoot);
        }
        if (root === document && document.documentElement && document.documentElement.shadowRoot) {
            walk(document.documentElement.shadowRoot);
        }
    }
    walk(document);
    return out.join('\\n');
}"""

# ============================================================================
# DOM EXTRACTION
# ============================================================================
async def page_text_with_shadow(page) -> str:
    """Collect visible text across the shadow trees.

    Charts is a Polymer application: ``document.body.innerText`` is empty even
    when the chart is rendered, so plain body text is useless for detection.
    """
    try:
        text = await page.evaluate(JS_SHADOW_TEXT)
        return text or ""
    except Exception as exc:
        log.info("Shadow text extraction failed: %s", exc)
        return ""


async def extract_via_dom(page) -> List[Dict[str, Any]]:
    """Run the DOM extractor and drop empty or duplicate rows."""
    try:
        try:
            diagnostics = await page.evaluate(
                "() => ({links: document.querySelectorAll('a').length,"
                " bodyLen: document.body ? document.body.innerText.length : 0,"
                " title: document.title})"
            )
            log.info(
                "DOM diagnostics: links=%s bodyLen=%s title=%s",
                diagnostics.get("links"),
                diagnostics.get("bodyLen"),
                diagnostics.get("title"),
            )
        except Exception:
            pass

        data = await page.evaluate(JS_EXTRACT_DOM)
        if not isinstance(data, list):
            return []

        rows = [row for row in data if clean_text(row.get("Track Name"))]
        seen: set[str] = set()
        deduplicated = []
        for row in rows:
            url = row.get("YouTube URL", "")
            if url and url in seen:
                continue
            seen.add(url)
            deduplicated.append(row)
        return deduplicated
    except Exception as exc:
        log.info("DOM extraction failed: %s", exc)
        return []


async def extract_via_inner_text(page) -> List[Dict[str, Any]]:
    """Last-resort parser over ``body.innerText`` as a flat table.

    Emits a row only when a rank line is followed by title, artist and a numeric
    view count; never fabricates data.
    """
    try:
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
    except Exception as exc:
        log.info("innerText extraction failed: %s", exc)
        return []

    if not text or len(text) < 1000:
        log.info("innerText too short: len=%d", len(text) if text else 0)
        return []

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    rows: List[Dict[str, Any]] = []
    index = 0
    while index < len(lines):
        if re.fullmatch(r"(\d{1,3})", lines[index] or "") and index + 3 < len(lines):
            rank = int(lines[index])
            if 1 <= rank <= 100:
                title = lines[index + 1]
                artist = lines[index + 2]
                views = lines[index + 3] if index + 3 < len(lines) else ""
                if (
                    re.search(r"[\d,.]+", views)
                    and 1 < len(title) < 120
                    and len(artist) < 120
                ):
                    if title.lower() not in (
                        "last week",
                        "weeks on chart",
                        "weekly views",
                        "title",
                        "artist",
                    ):
                        rows.append(
                            {
                                "Rank": rank,
                                "Track Name": title,
                                "Artist Names": artist,
                                "Views": views,
                                "Views Raw": views,
                                "YouTube URL": "",
                            }
                        )
                        index += 4
                        continue
        index += 1

    log.info("innerText rows parsed: %d from %d lines", len(rows), len(lines))
    return rows


# ============================================================================
# JSON EXTRACTION
# ============================================================================
def text_from_yt_node(node: Any) -> str:
    """Flatten a YouTube text node (``simpleText``, ``runs`` or ``text``)."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if "simpleText" in node:
            return str(node["simpleText"])
        if isinstance(node.get("runs"), list):
            return "".join(
                str(run.get("text", "")) for run in node["runs"] if isinstance(run, dict)
            )
        if isinstance(node.get("text"), str):
            return node["text"]
    return ""


def extract_rows_from_yt_json(
    payload: Any, seen: Optional[set] = None
) -> List[Dict[str, Any]]:
    """Recursively harvest any object carrying a ``videoId`` and a title.

    Structure-agnostic on purpose: YouTube reshapes the payload without notice,
    but the video id, title, byline and view count keys are stable.
    """
    seen = seen if seen is not None else set()
    rows: List[Dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            video_id = node.get("videoId") or node.get("video_id")
            if (
                isinstance(video_id, str)
                and len(video_id) == 11
                and video_id not in seen
            ):
                title = ""
                artist = ""
                views_raw = ""
                for key in ("title", "headline"):
                    if key in node:
                        candidate = text_from_yt_node(node[key])
                        if candidate:
                            title = candidate
                            break
                for key in ("subtitle", "shortBylineText", "longBylineText", "bylineText"):
                    if key in node:
                        candidate = text_from_yt_node(node[key])
                        if candidate:
                            artist = candidate
                            break
                for key in ("viewCountText", "views", "viewCount"):
                    if key in node:
                        candidate = text_from_yt_node(node[key])
                        if candidate:
                            views_raw = candidate
                            break
                if title:
                    seen.add(video_id)
                    rows.append(
                        {
                            "Rank": len(rows) + 1,
                            "Track Name": title,
                            "Artist Names": artist,
                            "Views": views_raw,
                            "Views Raw": views_raw,
                            "YouTube URL": f"https://www.youtube.com/watch?v={video_id}",
                            "videoId": video_id,
                        }
                    )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return rows


def extract_rows_from_generic_json(payload: Any) -> List[Dict[str, Any]]:
    """Fallback for payloads without ``videoId``: title plus artist or views."""
    rows: List[Dict[str, Any]] = []
    seen: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            title = (
                node.get("title")
                or node.get("name")
                or node.get("track")
                or node.get("songTitle")
            )
            artist = (
                node.get("artist")
                or node.get("artistName")
                or node.get("artists")
                or node.get("artistNames")
            )
            views = (
                node.get("views")
                or node.get("weeklyViews")
                or node.get("viewCount")
                or node.get("viewsCount")
            )
            rank = node.get("rank") or node.get("position") or node.get("chartPosition")
            if isinstance(title, str) and title and isinstance(artist, (str, list)):
                if isinstance(artist, list):
                    artist = ", ".join(
                        str(item.get("name", item) if isinstance(item, dict) else item)
                        for item in artist
                    )
                key = (title, str(artist))
                if key not in seen:
                    seen.add(key)
                    rows.append(
                        {
                            "Rank": rank or len(rows) + 1,
                            "Track Name": title,
                            "Artist Names": str(artist),
                            "Views": "" if views is None else str(views),
                            "Views Raw": "" if views is None else str(views),
                            "YouTube URL": node.get("url") or node.get("youtubeUrl") or "",
                        }
                    )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return rows


def parse_next_data(html: str) -> List[Dict[str, Any]]:
    """Extract rows from the Next.js ``__NEXT_DATA__`` island, if present."""
    match = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, flags=re.DOTALL
    )
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
        rows = extract_rows_from_yt_json(payload)
        if len(rows) >= 10:
            return rows
        return extract_rows_from_generic_json(payload)
    except Exception as exc:
        log.info("__NEXT_DATA__ parsing failed: %s", exc)
        return []


def parse_yt_initial_data(html: str) -> List[Dict[str, Any]]:
    """Extract rows from the ``ytInitialData`` bootstrap object."""
    patterns = (
        r"var\s+ytInitialData\s*=\s*(\{.+?\});\s*</script>",
        r"ytInitialData\s*=\s*(\{.+?\});",
        r"window\[\"ytInitialData\"\]\s*=\s*(\{.+?\});",
    )
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.DOTALL)
        if not match:
            continue
        try:
            rows = extract_rows_from_yt_json(json.loads(match.group(1)))
            if len(rows) >= 10:
                return rows
        except Exception:
            continue
    return []


def extract_rows_from_youtubei_json(payload: Any) -> List[Dict[str, Any]]:
    """Parse a ``youtubei/v1/browse`` response for chart renderers."""
    rows: List[Dict[str, Any]] = []

    def flatten(node: Any) -> str:
        if isinstance(node, str):
            return node
        if isinstance(node, dict):
            if "simpleText" in node:
                return str(node.get("simpleText") or "")
            if isinstance(node.get("runs"), list):
                return "".join(
                    str(run.get("text", ""))
                    for run in node["runs"]
                    if isinstance(run, dict)
                )
        return ""

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "musicResponsiveListItemRenderer" in node:
                renderer = node["musicResponsiveListItemRenderer"]
                columns = renderer.get("flexColumns", []) or []
                texts: List[str] = []
                for column in columns:
                    cell = column.get("musicResponsiveListItemFlexColumnRenderer") or {}
                    runs = (cell.get("text") or {}).get("runs", []) or []
                    for run in runs:
                        if isinstance(run, dict) and run.get("text"):
                            texts.append(str(run["text"]))

                video_id = ""
                try:
                    navigation = renderer.get("navigationEndpoint", {}) or {}
                    watch = navigation.get("watchEndpoint", {}) or {}
                    video_id = watch.get("videoId", "") or ""
                except Exception:
                    pass
                if not video_id:
                    match = re.search(
                        r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"',
                        json.dumps(renderer),
                    )
                    if match:
                        video_id = match.group(1)

                if texts:
                    # Column order varies between chart layouts; keep the
                    # positional heuristic and let normalization sort it out.
                    title = texts[1] if len(texts) > 1 else texts[0]
                    artist = texts[2] if len(texts) > 2 else ""
                    views = texts[-1] if len(texts) > 3 else ""
                    if len(texts) == 2:
                        title, artist = texts[0], texts[1]
                    rows.append(
                        {
                            "Rank": len(rows) + 1,
                            "Track Name": title.strip(),
                            "Artist Names": artist.strip(),
                            "Views": views.strip(),
                            "Views Raw": views.strip(),
                            "YouTube URL": (
                                f"https://www.youtube.com/watch?v={video_id}"
                                if video_id
                                else ""
                            ),
                            "videoId": video_id,
                        }
                    )
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return rows


# ============================================================================
# NETWORK AND DEBUG
# ============================================================================
async def try_youtubei_browse(
    page, chart: str = "TopSongs", country: str = "global"
) -> List[Dict[str, Any]]:
    """Query the internal ``youtubei/v1/browse`` endpoint used by the site.

    Charts may answer 404 for this browse id; that is a layout change, not a
    captcha, so the caller falls through to the DOM strategies.
    """
    try:
        html = await page.content()
    except Exception as exc:
        log.info("youtubei: page.content unavailable: %s", exc)
        return []

    key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html)
    if not key_match:
        key_match = re.search(r'innertubeApiKey["\']?\s*[:=]\s*["\']([^"\']+)', html)
    api_key = (
        key_match.group(1) if key_match else "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
    )

    version_match = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([^"]+)"', html)
    client_version = version_match.group(1) if version_match else "2.20240111.09.00"
    log.info(
        "youtubei: api_key=%s... client_version=%s", api_key[:8], client_version
    )

    region = "US" if country == "global" else country
    payloads = (
        {
            "context": {
                "client": {
                    "hl": "en",
                    "gl": region,
                    "clientName": "WEB",
                    "clientVersion": client_version,
                }
            },
            "browseId": "FEmusic_charts",
            "params": "ggM6Y2hhcnRz",
        },
        {
            "context": {
                "client": {
                    "hl": "en",
                    "gl": "US",
                    "clientName": "WEB",
                    "clientVersion": client_version,
                }
            },
            "browseId": "FEmusic_charts",
        },
    )

    for index, payload in enumerate(payloads, start=1):
        try:
            log.info("youtubei: attempt %d POST /youtubei/v1/browse", index)
            response = await page.request.post(
                f"https://www.youtube.com/youtubei/v1/browse?key={api_key}&prettyPrint=false",
                data=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT,
                },
                timeout=30000,
            )
            log.info("youtubei: attempt %d status=%s", index, response.status)
            if response.status == 404:
                log.info("youtubei: 404 for browseId, Charts does not expose it")
                return []
            if response.status != 200:
                try:
                    body = await response.text()
                    log.info("youtubei: attempt %d body[:500]=%s", index, body[:500])
                except Exception:
                    pass
                continue

            data = await response.json()
            rows = extract_rows_from_youtubei_json(data)
            log.info("youtubei: attempt %d rows=%d", index, len(rows))
            if len(rows) >= 10:
                return rows
            try:
                keys = list(data.keys()) if isinstance(data, dict) else f"list len {len(data)}"
                log.info("youtubei: keys=%s", keys)
            except Exception:
                pass
        except Exception as exc:
            log.info("youtubei: attempt %d failed: %s", index, exc)

    return []


async def save_debug_artifacts(page, url: str, tag: str = "fail") -> None:
    """Persist screenshot, HTML and text when extraction returns nothing.

    Kept in the run itself so a failed cron execution leaves evidence without
    requiring a manual reproduction.
    """
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            await page.screenshot(
                path=str(DEBUG_DIR / f"debug_{tag}_{stamp}.png"),
                full_page=False,
                timeout=15000,
            )
            log.info("Debug screenshot: logs/debug/debug_%s_%s.png", tag, stamp)
        except Exception as exc:
            log.info("Debug screenshot failed: %s", exc)

        try:
            html = await page.content()
            (DEBUG_DIR / f"debug_{tag}_{stamp}.html").write_text(html, encoding="utf-8")
            log.info("Debug HTML: %d bytes", len(html))
        except Exception as exc:
            log.info("Debug HTML failed: %s", exc)

        try:
            text = await page_text_with_shadow(page)
            title = await page.evaluate("() => document.title")
            body = (
                f"URL: {url}\nTitle: {title}\nFinal URL: {page.url}\n"
                f"Body len: {len(text)}\n\n--- BODY ---\n{text[:8000]}"
            )
            (DEBUG_DIR / f"debug_{tag}_{stamp}.txt").write_text(body, encoding="utf-8")
            log.info("Debug text: %d chars", len(text))
            log.info("Debug body snippet[:800]: %s", text[:800].replace("\n", " | "))
        except Exception as exc:
            log.info("Debug text failed: %s", exc)
    except Exception as exc:
        log.info("Debug artifact collection failed: %s", exc)
