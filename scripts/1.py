"""
YouTube Charts Data Scraper - v5 FULL (Proxy + Argumentos Completos)
============================================================================
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("youtube_charts")

# ---------------------------------------------------------------------------
# CONSTANTS AND DIRECTORIES
# ---------------------------------------------------------------------------
try:
    BASE_DIR = Path(__file__).resolve().parent
except NameError:
    BASE_DIR = Path.cwd()

if BASE_DIR.name == "scripts":
    BASE_DIR = BASE_DIR.parent

if os.environ.get("YOUTUBE_CHARTS_BASE_DIR"):
    BASE_DIR = Path(os.environ["YOUTUBE_CHARTS_BASE_DIR"]).expanduser().resolve()

IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"
IS_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"
IS_LOCAL = not IS_GITHUB_ACTIONS

LOCAL_TIMEZONE = "America/Santiago" if IS_LOCAL else "America/New_York"

OUTPUT_DIR = BASE_DIR / "data"
ARCHIVE_DIR = BASE_DIR / "charts_archive" / "1_download-chart"
DATABASE_DIR = ARCHIVE_DIR / "databases"
BACKUP_DIR = ARCHIVE_DIR / "backup"
LOGS_DIR = BASE_DIR / "logs"
BROWSER_PROFILE_DIR = BASE_DIR / ".browser-profile"

CANONICAL_COLUMNS = [
    "Rank", "Previous Rank", "Track Name", "Artist Names",
    "Periods on Chart", "Views", "Views Raw", "Growth", "YouTube URL",
]

COLUMN_ALIASES = {
    "title": "Track Name", "song": "Track Name", "track": "Track Name",
    "track name": "Track Name", "track_name": "Track Name", "artist": "Artist Names",
    "artists": "Artist Names", "artist names": "Artist Names", "artist_names": "Artist Names",
    "rank": "Rank", "position": "Rank", "pos": "Rank", "previous rank": "Previous Rank",
    "previous_rank": "Previous Rank", "prev rank": "Previous Rank",
    "periods on chart": "Periods on Chart", "weeks on chart": "Periods on Chart",
    "views": "Views", "view count": "Views", "growth": "Growth",
    "youtube url": "YouTube URL", "url": "YouTube URL", "link": "YouTube URL",
    "video url": "YouTube URL",
}


def ensure_directories() -> None:
    for p in [OUTPUT_DIR, ARCHIVE_DIR, DATABASE_DIR, BACKUP_DIR, LOGS_DIR]:
        p.mkdir(parents=True, exist_ok=True)


def setup_file_logging() -> None:
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOGS_DIR / f"scraper_{datetime.now().strftime('%Y-%m-%d')}.log"
        if not any(isinstance(h, logging.FileHandler) for h in log.handlers):
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            log.addHandler(fh)
    except Exception as e:
        log.warning("No se pudo crear log en archivo: %s", e)


def has_display() -> bool:
    if not IS_LINUX: return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _chrome_available() -> bool:
    return bool(
        shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or Path("/opt/google/chrome/chrome").exists()
    )


def get_browser_args() -> list:
    args = [
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--window-size=1920,1080",
        "--start-maximized",
    ]
    if IS_LINUX:
        args.extend(["--no-sandbox", "--disable-dev-shm-usage"])
    return args


# ---------------------------------------------------------------------------
# PARSING HELPERS
# ---------------------------------------------------------------------------
def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _parse_views(value: Any) -> Optional[int]:
    if value is None or value == "": return None
    if isinstance(value, (int, float)): return int(value)
    s = str(value).strip().replace(",", "").replace(" ", "")
    s = re.sub(r"(views|reproducciones|vistas)$", "", s, flags=re.I).strip()
    if not s: return None
    mult = 1
    if s[-1] in ("K", "k"): mult, s = 1_000, s[:-1]
    elif s[-1] in ("M", "m"): mult, s = 1_000_000, s[:-1]
    elif s[-1] in ("B", "b"): mult, s = 1_000_000_000, s[:-1]
    try: return int(float(s) * mult)
    except ValueError:
        m = re.search(r"[\d.]+", s)
        if m:
            try: return int(float(m.group(0)) * mult)
            except ValueError: return None
        return None


def _parse_int(value: Any) -> Optional[int]:
    if value is None or value == "": return None
    if isinstance(value, int): return value
    if isinstance(value, float): return int(value)
    s = re.sub(r"[^0-9-]", "", str(value))
    if not s or s == "-": return None
    try: return int(s)
    except ValueError: return None


def _normalize_row(raw: Dict[str, Any], rank_fallback: int = 0) -> Dict[str, Any]:
    out: Dict[str, Any] = {c: "" for c in CANONICAL_COLUMNS}
    for k, v in raw.items():
        key = str(k).strip().lower()
        canon = COLUMN_ALIASES.get(key, str(k).strip())
        if canon in out: out[canon] = v
    if not _parse_int(out.get("Rank")): out["Rank"] = rank_fallback
    views_raw = _clean_text(out.get("Views Raw") or out.get("Views"))
    parsed = _parse_views(out.get("Views"))
    if parsed is not None:
        out["Views"] = parsed
        if not out.get("Views Raw"): out["Views Raw"] = views_raw
    else:
        out["Views"] = ""
        out["Views Raw"] = views_raw
    for col in ("Rank", "Previous Rank", "Periods on Chart"):
        val = _parse_int(out.get(col))
        out[col] = val if val is not None else ""
    for col in ("Track Name", "Artist Names", "Growth", "YouTube URL", "Views Raw"):
        out[col] = _clean_text(out.get(col))
    if not out["YouTube URL"] and raw.get("videoId"):
        out["YouTube URL"] = f"https://www.youtube.com/watch?v={raw['videoId']}"
    return out


def save_rows_to_csv(rows: List[Dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = [_normalize_row(r, i + 1) for i, r in enumerate(rows)]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        writer.writerows(normalized)
    log.info("CSV guardado: %s (%d filas)", path, len(normalized))
    return path


def _read_csv_normalized(csv_path: Path) -> List[Dict[str, Any]]:
    rows = []
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(csv_path, "r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None: return []
                for i, raw in enumerate(reader):
                    rows.append(_normalize_row(raw, i + 1))
            break
        except UnicodeDecodeError: continue
    return rows


# ---------------------------------------------------------------------------
# SQLITE
# ---------------------------------------------------------------------------
def create_backup_before_update(week_id: str) -> Optional[Path]:
    db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
    if not db_path.exists(): return None
    ensure_directories()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = BACKUP_DIR / f"backup_{week_id}_{timestamp}.db"
    try:
        shutil.copy2(db_path, backup_path)
        return backup_path
    except Exception as e:
        log.warning("Error creando backup: %s", e)
        return None


def cleanup_old_backups(days: int = 7) -> None:
    if not BACKUP_DIR.exists(): return
    cutoff = datetime.now() - timedelta(days=days)
    for backup in BACKUP_DIR.glob("backup_*.db"):
        if backup.stat().st_mtime < cutoff.timestamp(): backup.unlink()


def cleanup_old_databases(weeks: int = 52) -> None:
    if not DATABASE_DIR.exists(): return
    cutoff = datetime.now() - timedelta(weeks=weeks)
    for db in DATABASE_DIR.glob("youtube_charts_*.db"):
        try:
            week_id = db.stem.replace("youtube_charts_", "")
            year_str, week_str = week_id.split("-W")
            if datetime.fromisocalendar(int(year_str), int(week_str), 1) < cutoff:
                db.unlink()
        except Exception: pass


def update_sqlite_database(csv_path: Path, week_id: str) -> Optional[Path]:
    rows = _read_csv_normalized(Path(csv_path))
    if not rows:
        log.error("CSV vacio o sin filas validas: %s", csv_path)
        return None
    ensure_directories()
    db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
    if db_path.exists(): create_backup_before_update(week_id)

    now = datetime.now()
    all_cols = CANONICAL_COLUMNS + ["download_date", "download_time", "week_id", "timestamp", "is_synthetic"]

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chart_data (
                "Rank" INTEGER, "Previous Rank" INTEGER, "Track Name" TEXT,
                "Artist Names" TEXT, "Periods on Chart" INTEGER, "Views" INTEGER,
                "Views Raw" TEXT, "Growth" TEXT, "YouTube URL" TEXT,
                download_date TEXT, download_time TEXT, week_id TEXT,
                timestamp TEXT, is_synthetic INTEGER DEFAULT 0
            )
        """)
        cur.execute("DELETE FROM chart_data WHERE week_id = ?", (week_id,))
        placeholders = ", ".join(["?"] * len(all_cols))
        quoted = ", ".join([f'"{c}"' for c in all_cols])
        sql = f"INSERT INTO chart_data ({quoted}) VALUES ({placeholders})"

        to_insert = []
        for r in rows:
            vals = []
            for c in CANONICAL_COLUMNS:
                v = r.get(c, "")
                if c in ("Rank", "Previous Rank", "Periods on Chart", "Views") and v == "": v = None
                vals.append(v)
            vals.extend([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), week_id, now.strftime("%Y%m%d_%H%M%S"), 0])
            to_insert.append(tuple(vals))

        cur.executemany(sql, to_insert)
        conn.commit()
        log.info("DB actualizada: total=%d path=%s", len(rows), db_path)
        conn.close()
        return db_path
    except Exception as e:
        log.error("Error SQLite: %s", e)
        return None


# ---------------------------------------------------------------------------
# EXTRACCION DOM
# ---------------------------------------------------------------------------
_JS_EXTRACT_DOM = r"""
() => {
  const rows = [];
  const seen = new Set();
  const getText = (el) => (el.innerText || el.textContent || '').trim();
  const allEls = [];
  const collect = (root) => {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll('*').forEach((el) => {
      allEls.push(el);
      if (el.shadowRoot) collect(el.shadowRoot);
    });
  };
  collect(document);

  for (const el of allEls) {
    if (el.tagName !== 'A') continue;
    const href = el.getAttribute('href') || '';
    if (!href) continue;
    const m = href.match(/v=([A-Za-z0-9_-]{11})/) || href.match(/youtu\.be\/([A-Za-z0-9_-]{11})/);
    const vid = m ? m[1] : '';
    const container = el.closest ? el.closest('tr, li, [role="row"], [class*="row"], [class*="item"], [class*="chart"]') : null;
    const text = container ? container.innerText : getText(el);
    const lines = (text || '').split('\n').map(s => s.trim()).filter(Boolean);
    if (vid) {
      if (seen.has(vid)) continue;
      seen.add(vid);
    } else {
      if (lines.length < 3) continue;
      const key = (getText(el) + '|' + lines.join('|')).slice(0,200);
      if (seen.has(key)) continue;
      if (!/[0-9]/.test(text)) continue;
      seen.add(key);
    }
    let title = (el.getAttribute('aria-label') || getText(el) || '').trim().split('\n')[0] || (lines[1] || lines[0] || '');
    title = title.replace(/^\d+\.\s*/, '').replace(/^\d+\s+/, '');
    let artist = '', viewsRaw = '';
    for (const l of lines) {
      if (/[\d,.]+\s*[KMB]?\s*(views|reproducciones|vistas)/i.test(l)) viewsRaw = l;
    }
    for (const l of lines) {
      if (l !== title && l !== viewsRaw && !/^\d+$/.test(l) && l.length > 1 && l.length < 90) { artist = l; break; }
    }
    rows.push({
      Rank: rows.length+1, 'Track Name': title, 'Artist Names': artist, 'Views': viewsRaw, 'Views Raw': viewsRaw, 'YouTube URL': vid ? 'https://www.youtube.com/watch?v=' + vid : href
    });
  }
  return rows;
}
"""


async def _extract_via_dom(page) -> List[Dict[str, Any]]:
    try:
        data = await page.evaluate(_JS_EXTRACT_DOM)
        if not isinstance(data, list): return []
        out = [r for r in data if _clean_text(r.get("Track Name"))]
        seen = set()
        dedup = []
        for r in out:
            u = r.get("YouTube URL", "")
            if u and u in seen: continue
            seen.add(u)
            dedup.append(r)
        for i, r in enumerate(dedup, 1): r["Rank"] = i
        log.info("Extraccion DOM: %d filas", len(dedup))
        return dedup
    except Exception as e:
        log.info("Extraccion DOM fallo: %s", e)
        return []


async def _get_page_text_with_shadow(page) -> str:
    try:
        txt = await page.evaluate("""
            () => {
                const out = [];
                const walk = (root) => {
                    if (!root) return;
                    try {
                        const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                        let n;
                        while ((n = tw.nextNode())) {
                            const p = n.parentElement;
                            if (!p) continue;
                            const tag = (p.tagName || '').toUpperCase();
                            if (tag === 'STYLE' || tag === 'SCRIPT' || tag === 'NOSCRIPT' || tag === 'TEMPLATE') continue;
                            const v = (n.nodeValue || '').trim();
                            if (v) out.push(v);
                        }
                    } catch (e) {}
                    if (root.querySelectorAll) {
                        root.querySelectorAll('*').forEach((el) => { if (el.shadowRoot) walk(el.shadowRoot); });
                    }
                };
                walk(document);
                if (document.body && document.body.innerText) out.push(document.body.innerText);
                return out.join('\\n');
            }
        """)
        return txt or ""
    except Exception: return ""


async def _detect_captcha(page) -> bool:
    try:
        shadow_txt = await _get_page_text_with_shadow(page)
        low = (shadow_txt or "").lower()
        has_chart = ("weekly top songs" in low or "weekly top artists" in low) and ("weekly views" in low or "rank" in low)
        if has_chart: return False
        if "select all images" in low and "click verify" in low: return True
        
        has_visible = await page.evaluate("""
            () => {
                const cands = document.querySelectorAll('[class*="recaptcha"], iframe[src*="recaptcha"]');
                for (const el of cands) {
                    const r = el.getBoundingClientRect ? el.getBoundingClientRect() : {width:0,height:0};
                    if (r.width >= 300 && r.height >= 100) return true;
                }
                return false;
            }
        """)
        if has_visible and not has_chart: return True
        return False
    except Exception: return False


# ---------------------------------------------------------------------------
# DESCARGA PRINCIPAL (CON SOPORTE DE PROXY)
# ---------------------------------------------------------------------------
async def download_youtube_charts(chart: str, country: str, show_browser: bool, use_chrome: bool, terminal_mode: bool, wait_s: int) -> Optional[Path]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.error("Playwright no instalado")
        return None

    filename = ARCHIVE_DIR / "latest_chart.csv"
    
    proxy_server = os.environ.get("PROXY_SERVER", "").strip()
    proxy_user = os.environ.get("PROXY_USER", "").strip()
    proxy_pass = os.environ.get("PROXY_PASS", "").strip()
    proxy_config = None
    
    if proxy_server and proxy_user and proxy_pass:
        proxy_config = {
            "server": proxy_server,
            "username": proxy_user,
            "password": proxy_pass,
        }
        log.info("✅ Proxy configurado: %s", proxy_server)
    else:
        log.warning("⚠️ Sin proxy: Google bloqueará la IP de Azure con reCAPTCHA")

    async with async_playwright() as p:
        headless = not show_browser
        if terminal_mode and has_display():
            headless = False
            show_browser = True

        browser_args = get_browser_args()
        if headless: browser_args.append("--headless=new")

        launch_kwargs = dict(headless=headless, args=browser_args)
        if proxy_config:
            launch_kwargs["proxy"] = proxy_config
        if use_chrome and _chrome_available():
            launch_kwargs["channel"] = "chrome"

        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US"
        )
        
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        
        page = await context.new_page()
        page.set_default_timeout(60000)

        urls = [
            f"https://charts.youtube.com/charts/{chart}/{country}",
            f"https://charts.youtube.com/charts/{chart}/{country}/weekly"
        ]

        try:
            for url in urls:
                log.info("Navegando a %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(8000)
                
                # Poll esperando el chart
                for _ in range(wait_s // 3):
                    txt = await _get_page_text_with_shadow(page)
                    if "Weekly Top Songs" in txt and "Weekly views" in txt:
                        log.info("✅ Chart visible en shadow")
                        break
                    await page.wait_for_timeout(3000)

                # Consentimiento
                for label in [r"Accept all", r"Aceptar todo"]:
                    try:
                        btn = page.get_by_role("button", name=re.compile(label, re.I))
                        if await btn.count() > 0: await btn.first.click(timeout=3000)
                    except Exception: pass

                # Scroll
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 1000)")
                    await page.wait_for_timeout(1000)

                rows = await _extract_via_dom(page)
                if len(rows) >= 50:
                    return save_rows_to_csv(rows, filename)
                
                log.warning("Pocas filas (%d) en %s", len(rows), url)
        finally:
            await context.close()
            await browser.close()
            
    return None


# ---------------------------------------------------------------------------
# MAIN COMPLETO CON ARGPARSE Y LÓGICA
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube Charts Scraper v5")
    parser.add_argument("--country", default="global")
    parser.add_argument("--chart", default="TopSongs")
    parser.add_argument("--week", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--terminal", action="store_true")
    parser.add_argument("--show-browser", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--use-chrome", action="store_true")
    parser.add_argument("--no-profile", action="store_true")
    parser.add_argument("--wait", type=int, default=90)
    parser.add_argument("--min-rows", type=int, default=50)
    parser.add_argument("--pause", action="store_true")
    parser.add_argument("--open-folder", action="store_true")
    args = parser.parse_args()

    ensure_directories()
    setup_file_logging()
    
    week_id = args.week or f"{datetime.now().isocalendar()[0]}-W{datetime.now().isocalendar()[1]:02d}"
    log.info("Semana: %s | base=%s", week_id, BASE_DIR)
    
    if not args.force:
        db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            try:
                cnt = conn.execute("SELECT COUNT(*) FROM chart_data").fetchone()[0]
                if cnt >= args.min_rows:
                    log.info("Semana ya tiene %d datos. Saltando (usa --force para forzar).", cnt)
                    return 0
            finally:
                conn.close()

    show_browser = True
    if args.headless:
        show_browser = False
    elif args.terminal:
        show_browser = has_display()

    csv_path = asyncio.run(download_youtube_charts(
        chart=args.chart,
        country=args.country,
        show_browser=show_browser,
        use_chrome=args.use_chrome,
        terminal_mode=args.terminal,
        wait_s=args.wait
    ))
    
    if not csv_path or not csv_path.exists():
        log.error("❌ CRITICO: No se obtuvieron datos reales.")
        if args.pause:
            try: input("\nPresiona Enter para cerrar...")
            except: pass
        return 2

    if not update_sqlite_database(csv_path, week_id):
        return 1

    cleanup_old_backups()
    cleanup_old_databases()
    
    log.info("✅ PROCESO COMPLETADO - DATOS REALES")
    
    if args.pause:
        try: input("\nPresiona Enter para cerrar...")
        except: pass
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
