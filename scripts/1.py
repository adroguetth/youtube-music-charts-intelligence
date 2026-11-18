#!/usr/bin/env python3
"""
YouTube Charts scraper (scripts/1.py) - v3
==========================================
Descarga el chart semanal (TopSongs / global, 100 canciones) y lo guarda
como CSV + SQLite. Si no puede obtener datos REALES sale con codigo 2 y no
escribe nada en la DB (no hay datos sinteticos).

Pensado para correr en un equipo PROPIO (tu PC o un runner self-hosted de
GitHub Actions) con Google Chrome instalado, en modo ventana (headed) y con
un perfil persistente. Los runners hospedados por GitHub usan IPs de
datacenter que reCAPTCHA Enterprise puntua muy bajo, y esto no se arregla
con cambios de codigo.

Que cambio respecto a la version anterior
-----------------------------------------
- BASE_DIR es la raiz del repo (no scripts/), asi CSV y logs quedan donde el
  workflow los busca (charts_archive/ y logs/ en la raiz).
- Ya NO fuerza user-agent, ni parchea navigator.plugins/languages, ni usa
  --disable-gpu. Quita --enable-automation. Menos incoherencias = menos
  puntaje de bot. Registra el user-agent real en el log para comprobarlo.
- Perfil persistente en YOUTUBE_PROFILE_DIR (por defecto .browser-profile/).
  En un runner self-hosted ponlo FUERA del workspace: actions/checkout
  ejecuta git clean -ffdx y borraria el perfil.
- --terminal = no interactivo (nunca espera Enter ni captcha manual).
  NO significa headless. Headless solo con --headless explicito.
- Falla rapido si hay captcha y no hay humano (CAPTCHA_GRACE_S).
- Los rangos se renumeran 1..N tras deduplicar (antes podian quedar huecos).
- Codigo muerto eliminado: youtubei (siempre 0), HTTP directo,
  __NEXT_DATA__, innerText con regex mal escapada, fallback sintetico.

Uso
---
    python scripts/1.py --use-chrome                   # ventana, interactivo
    xvfb-run -a -s "-screen 0 1920x1080x24" \\
        python scripts/1.py --terminal --use-chrome --force   # CI / cron

Variables de entorno opcionales
-------------------------------
    YOUTUBE_PROFILE_DIR      carpeta del perfil persistente de Chrome
    YOUTUBE_CHARTS_BASE_DIR  raiz de salida (charts_archive/, logs/)
    YOUTUBE_TZ               zona horaria del navegador (vacio = la del sistema)

Primera vez: corre una vez en ventana y, si sale captcha, resuelvelo a mano
con el MISMO YOUTUBE_PROFILE_DIR que usara el workflow.

Codigos de salida: 0 ok, 1 error, 2 sin datos reales (captcha, bloqueo, etc.)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
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
# RUTAS Y CONSTANTES (sin efectos al importar)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent if SCRIPT_DIR.name == "scripts" else SCRIPT_DIR
if os.environ.get("YOUTUBE_CHARTS_BASE_DIR"):
    BASE_DIR = Path(os.environ["YOUTUBE_CHARTS_BASE_DIR"]).expanduser().resolve()

ARCHIVE_DIR = BASE_DIR / "charts_archive" / "1_download-chart"
DATABASE_DIR = ARCHIVE_DIR / "databases"
BACKUP_DIR = ARCHIVE_DIR / "backup"
LOGS_DIR = BASE_DIR / "logs"
PROFILE_DIR = Path(
    os.environ.get("YOUTUBE_PROFILE_DIR") or (BASE_DIR / ".browser-profile")
).expanduser().resolve()
BROWSER_TZ = os.environ.get("YOUTUBE_TZ", "").strip()

IS_LINUX = sys.platform.startswith("linux")
IS_CI = os.environ.get("GITHUB_ACTIONS") == "true"

CAPTCHA_GRACE_S = 15  # sin humano: si el captcha sigue tras N s, abortar

CANONICAL_COLUMNS = [
    "Rank",
    "Previous Rank",
    "Track Name",
    "Artist Names",
    "Periods on Chart",
    "Views",
    "Views Raw",
    "Growth",
    "YouTube URL",
]

COLUMN_ALIASES = {
    "title": "Track Name",
    "song": "Track Name",
    "track": "Track Name",
    "track name": "Track Name",
    "track_name": "Track Name",
    "artist": "Artist Names",
    "artists": "Artist Names",
    "artist names": "Artist Names",
    "artist_names": "Artist Names",
    "rank": "Rank",
    "position": "Rank",
    "pos": "Rank",
    "previous rank": "Previous Rank",
    "previous_rank": "Previous Rank",
    "prev rank": "Previous Rank",
    "periods on chart": "Periods on Chart",
    "weeks on chart": "Periods on Chart",
    "views": "Views",
    "view count": "Views",
    "growth": "Growth",
    "youtube url": "YouTube URL",
    "url": "YouTube URL",
    "link": "YouTube URL",
    "video url": "YouTube URL",
}


def ensure_directories() -> None:
    for p in (ARCHIVE_DIR, DATABASE_DIR, BACKUP_DIR, LOGS_DIR):
        p.mkdir(parents=True, exist_ok=True)


def setup_file_logging() -> None:
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOGS_DIR / f"scraper_{datetime.now().strftime('%Y-%m-%d')}.log"
        if not any(isinstance(h, logging.FileHandler) for h in log.handlers):
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            )
            log.addHandler(fh)
            log.info("Log en: %s", log_file)
    except Exception as e:
        log.warning("No se pudo crear log en archivo: %s", e)


def open_folder(path: Path) -> None:
    try:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log.warning("No se pudo abrir la carpeta %s: %s", path, e)


def chrome_available() -> bool:
    if not IS_LINUX:
        return True
    return bool(
        shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or Path("/opt/google/chrome/chrome").exists()
    )


def has_display() -> bool:
    if not IS_LINUX:
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


# ---------------------------------------------------------------------------
# SEMANA Y URLS
# ---------------------------------------------------------------------------
def get_week_identifier(date: Optional[datetime] = None) -> str:
    date = date or datetime.now()
    year, week_num, _ = date.isocalendar()
    return f"{year}-W{week_num:02d}"


def get_chart_urls(chart: str = "TopSongs", country: str = "global") -> List[str]:
    chart = chart.strip() or "TopSongs"
    country = country.strip() or "global"
    base = f"https://charts.youtube.com/charts/{chart}/{country}"
    return [base, base + "/weekly"]


# ---------------------------------------------------------------------------
# PARSING
# ---------------------------------------------------------------------------
def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _parse_views(value: Any) -> Optional[int]:
    """'1,234,567', '5.2M', '1.1B', '850K' -> int. None si no se puede."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().replace(",", "").replace(" ", "")
    s = re.sub(r"(views|reproducciones|vistas)$", "", s, flags=re.I).strip()
    if not s:
        return None
    mult = 1
    if s[-1] in "Kk":
        mult, s = 1_000, s[:-1]
    elif s[-1] in "Mm":
        mult, s = 1_000_000, s[:-1]
    elif s[-1] in "Bb":
        mult, s = 1_000_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        m = re.search(r"[\d.]+", s)
        if m:
            try:
                return int(float(m.group(0)) * mult)
            except ValueError:
                return None
        return None


def _parse_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    s = re.sub(r"[^0-9-]", "", str(value))
    if not s or s == "-":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _normalize_row(raw: Dict[str, Any], rank_fallback: int = 0) -> Dict[str, Any]:
    out: Dict[str, Any] = {c: "" for c in CANONICAL_COLUMNS}
    for k, v in raw.items():
        key = str(k).strip().lower()
        canon = COLUMN_ALIASES.get(key, str(k).strip())
        if canon in out:
            out[canon] = v
    if not _parse_int(out.get("Rank")):
        out["Rank"] = rank_fallback
    views_raw = _clean_text(out.get("Views Raw") or out.get("Views"))
    parsed = _parse_views(out.get("Views"))
    if parsed is not None:
        out["Views"] = parsed
        if not out.get("Views Raw"):
            out["Views Raw"] = views_raw
    else:
        out["Views"] = ""
        out["Views Raw"] = views_raw
    for col in ("Rank", "Previous Rank", "Periods on Chart"):
        val = _parse_int(out.get(col))
        out[col] = val if val is not None else ""
    for col in ("Track Name", "Artist Names", "Growth", "YouTube URL", "Views Raw"):
        out[col] = _clean_text(out.get(col))
    if not out["YouTube URL"]:
        vid = raw.get("videoId") or raw.get("video_id")
        if vid:
            out["YouTube URL"] = f"https://www.youtube.com/watch?v={vid}"
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
    for enc in ("utf-8-sig", "latin-1"):
        try:
            with open(csv_path, "r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                return [_normalize_row(raw, i + 1) for i, raw in enumerate(reader)]
        except UnicodeDecodeError:
            continue
    return []


# ---------------------------------------------------------------------------
# BACKUPS Y LIMPIEZA
# ---------------------------------------------------------------------------
def create_backup_before_update(week_id: str) -> Optional[Path]:
    db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
    if not db_path.exists():
        return None
    ensure_directories()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = BACKUP_DIR / f"backup_{week_id}_{stamp}.db"
    try:
        shutil.copy2(db_path, backup_path)
        log.info("Backup creado: %s", backup_path.name)
        return backup_path
    except Exception as e:
        log.warning("Error creando backup: %s", e)
        return None


def cleanup_old_backups(days: int = 7) -> None:
    if not BACKUP_DIR.exists():
        return
    cutoff = (datetime.now() - timedelta(days=days)).timestamp()
    deleted = 0
    for backup in BACKUP_DIR.glob("backup_*.db"):
        try:
            if backup.stat().st_mtime < cutoff:
                backup.unlink()
                deleted += 1
        except Exception as e:
            log.warning("Error borrando %s: %s", backup.name, e)
    log.info("Backups eliminados (>%d dias): %d", days, deleted)


def cleanup_old_databases(weeks: int = 52) -> None:
    if not DATABASE_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(weeks=weeks)
    deleted = 0
    for db in DATABASE_DIR.glob("youtube_charts_*.db"):
        try:
            week_id = db.stem.replace("youtube_charts_", "")
            year_str, week_str = week_id.split("-W")
            if datetime.fromisocalendar(int(year_str), int(week_str), 1) < cutoff:
                db.unlink()
                deleted += 1
                log.info("Eliminada: %s", db.name)
        except Exception as e:
            log.warning("Error procesando %s: %s", db.name, e)
    log.info("Bases eliminadas (>%d semanas): %d", weeks, deleted)


# ---------------------------------------------------------------------------
# SQLITE
# ---------------------------------------------------------------------------
def update_sqlite_database(csv_path: Path, week_id: str) -> Optional[Path]:
    """DELETE por week_id + INSERT en una transaccion. Todo es dato real
    (is_synthetic = 0; la columna se mantiene por compatibilidad)."""
    rows = _read_csv_normalized(Path(csv_path))
    if not rows:
        log.error("CSV vacio o sin filas validas: %s", csv_path)
        return None
    log.info("Canciones cargadas: %d", len(rows))
    for i, r in enumerate(rows[:5]):
        log.info("  %d. %s - %s", i + 1, str(r.get("Track Name", ""))[:40], str(r.get("Artist Names", ""))[:40])

    ensure_directories()
    db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
    if db_path.exists():
        create_backup_before_update(week_id)

    now = datetime.now()
    download_date = now.strftime("%Y-%m-%d")
    download_time = now.strftime("%H:%M:%S")
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    all_cols = CANONICAL_COLUMNS + ["download_date", "download_time", "week_id", "timestamp", "is_synthetic"]

    try:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chart_data (
                    "Rank" INTEGER,
                    "Previous Rank" INTEGER,
                    "Track Name" TEXT,
                    "Artist Names" TEXT,
                    "Periods on Chart" INTEGER,
                    "Views" INTEGER,
                    "Views Raw" TEXT,
                    "Growth" TEXT,
                    "YouTube URL" TEXT,
                    download_date TEXT,
                    download_time TEXT,
                    week_id TEXT,
                    timestamp TEXT,
                    is_synthetic INTEGER DEFAULT 0
                )
                """
            )
            cur.execute("PRAGMA table_info(chart_data)")
            existing = {row[1] for row in cur.fetchall()}
            if "is_synthetic" not in existing:
                try:
                    cur.execute("ALTER TABLE chart_data ADD COLUMN is_synthetic INTEGER DEFAULT 0")
                except sqlite3.OperationalError:
                    pass

            cur.execute("DELETE FROM chart_data WHERE week_id = ?", (week_id,))
            if cur.rowcount:
                log.info("Eliminados %d registros viejos de %s", cur.rowcount, week_id)

            placeholders = ", ".join(["?"] * len(all_cols))
            quoted = ", ".join(f'"{c}"' for c in all_cols)
            sql = f"INSERT INTO chart_data ({quoted}) VALUES ({placeholders})"

            to_insert = []
            for r in rows:
                vals = []
                for c in CANONICAL_COLUMNS:
                    v = r.get(c, "")
                    if c in ("Rank", "Previous Rank", "Periods on Chart", "Views") and v == "":
                        v = None
                    vals.append(v)
                vals.extend([download_date, download_time, week_id, timestamp, 0])
                to_insert.append(tuple(vals))
            cur.executemany(sql, to_insert)

            for idx_name, idx_cols in (
                ("idx_date", "chart_data(download_date)"),
                ("idx_week", "chart_data(week_id)"),
                ("idx_rank", 'chart_data("Rank")'),
                ("idx_artist", 'chart_data("Artist Names")'),
            ):
                try:
                    cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_cols}")
                except sqlite3.OperationalError as e:
                    log.warning("No se pudo crear indice %s: %s", idx_name, e)

            conn.commit()
            cur.execute("SELECT COUNT(*) FROM chart_data")
            log.info("DB actualizada: total=%d path=%s", cur.fetchone()[0], db_path)
            return db_path
        finally:
            conn.close()
    except Exception as e:
        log.error("Error SQLite: %s", e, exc_info=True)
        return None


def week_already_done(week_id: str, min_real: int = 50) -> bool:
    db = DATABASE_DIR / f"youtube_charts_{week_id}.db"
    if not db.exists():
        return False
    try:
        conn = sqlite3.connect(db)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM chart_data WHERE week_id = ? AND COALESCE(is_synthetic, 0) = 0",
                (week_id,),
            ).fetchone()[0]
        finally:
            conn.close()
        return n >= min_real
    except Exception as e:
        log.info("Check de idempotencia fallo (ignorado): %s", e)
        return False


def list_available_databases() -> None:
    dbs = sorted(DATABASE_DIR.glob("youtube_charts_*.db"))
    if not dbs:
        log.info("No hay bases disponibles aun")
        return
    total = 0
    log.info("Bases disponibles (%d):", len(dbs))
    for db in dbs:
        try:
            conn = sqlite3.connect(db)
            try:
                count = conn.execute("SELECT COUNT(*) FROM chart_data").fetchone()[0]
            finally:
                conn.close()
            total += count
            log.info("  %s: %d registros, %.1f KB", db.stem.replace("youtube_charts_", ""), count, db.stat().st_size / 1024)
        except Exception as e:
            log.warning("Error leyendo %s: %s", db.name, e)
    log.info("TOTAL: %d registros en %d bases", total, len(dbs))


# ---------------------------------------------------------------------------
# EXTRACCION EN EL NAVEGADOR
# ---------------------------------------------------------------------------
# Misma logica que la version que funciona en tu PC (filas a partir de links
# de video y su contenedor). Cambio: recorre tambien los shadowRoot de TODOS
# los elementos, en orden de documento.
_JS_EXTRACT_DOM = r"""
() => {
  const rows = [];
  const seen = new Set();
  const getText = (el) => (el.innerText || el.textContent || '').trim();
  const links = [];
  const walk = (root) => {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll('*').forEach((el) => {
      if (el.tagName === 'A') {
        const href = el.getAttribute('href') || '';
        if (href) links.push({href, txt: getText(el).slice(0, 150), el});
      }
      if (el.shadowRoot) walk(el.shadowRoot);
    });
  };
  walk(document);

  const tableRows = document.querySelectorAll('table tbody tr');
  if (tableRows.length >= 20) {
    tableRows.forEach((tr, idx) => {
      const cells = Array.from(tr.querySelectorAll('td, th')).map(c => c.innerText.trim()).filter(Boolean);
      const link = tr.querySelector('a[href]');
      const href = link ? link.getAttribute('href') : '';
      if (cells.length >= 2) {
        rows.push({Rank: idx + 1, 'Track Name': cells[1] || '', 'Artist Names': cells[2] || '', 'Views': cells[3] || '', 'YouTube URL': href || ''});
      }
    });
    if (rows.length >= 20) return rows;
  }

  for (const item of links) {
    const href = item.href || '';
    const m = href.match(/v=([A-Za-z0-9_-]{11})/) || href.match(/youtu\.be\/([A-Za-z0-9_-]{11})/) || href.match(/\/watch\/([A-Za-z0-9_-]{11})/);
    const vid = m ? m[1] : '';
    const container = item.el.closest ? item.el.closest('tr, li, [role="row"], [class*="row"], [class*="item"], [class*="chart"]') : null;
    const text = container ? container.innerText : item.txt;
    const lines = (text || '').split('\n').map(s => s.trim()).filter(Boolean);
    if (vid) {
      if (seen.has(vid)) continue;
      seen.add(vid);
    } else {
      if (lines.length < 3) continue;
      const key = (item.txt + '|' + lines.join('|')).slice(0, 200);
      if (seen.has(key)) continue;
      if (!/[0-9]/.test(text || '')) continue;
      seen.add(key);
    }
    let title = (item.el.getAttribute('aria-label') || item.txt || '').trim().split('\n')[0] || (lines[1] || lines[0] || '');
    title = title.replace(/^\d+\.\s*/, '').replace(/^\d+\s+/, '');
    let artist = '';
    let viewsRaw = '';
    for (const l of lines) {
      if (/[\d,.]+\s*[KMB]?\s*(views|reproducciones|vistas)/i.test(l)) viewsRaw = l;
    }
    for (const l of lines) {
      if (l !== title && l !== viewsRaw && !/^\d+$/.test(l) && l.length > 1 && l.length < 90) { artist = l; break; }
    }
    rows.push({Rank: rows.length + 1, 'Track Name': title, 'Artist Names': artist, 'Views': viewsRaw, 'Views Raw': viewsRaw, 'YouTube URL': vid ? 'https://www.youtube.com/watch?v=' + vid : href, videoId: vid});
  }
  return rows;
}
"""

# Texto visible de toda la pagina, entrando en shadow roots.
_JS_PAGE_TEXT = r"""
() => {
  const out = [];
  const walk = (root) => {
    if (!root) return;
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = tw.nextNode())) {
      const p = n.parentElement;
      const t = p ? p.tagName : '';
      if (t === 'STYLE' || t === 'SCRIPT' || t === 'NOSCRIPT' || t === 'TEMPLATE') continue;
      const v = (n.nodeValue || '').trim();
      if (v) out.push(v);
    }
    if (root.querySelectorAll) {
      root.querySelectorAll('*').forEach((el) => { if (el.shadowRoot) walk(el.shadowRoot); });
    }
  };
  walk(document);
  return out.join('\n');
}
"""

_JS_CAPTCHA = r"""
() => {
  const low = (document.body ? document.body.innerText : '').toLowerCase();
  if (low.includes('select all images') || low.includes("i'm not a robot") || low.includes('unusual traffic')) return true;
  for (const el of document.querySelectorAll('iframe[src*="recaptcha"]')) {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.width >= 300 && r.height >= 100 && cs.visibility !== 'hidden' && cs.display !== 'none') return true;
  }
  return false;
}
"""


async def page_text(page) -> str:
    try:
        return await page.evaluate(_JS_PAGE_TEXT) or ""
    except Exception:
        return ""


def chart_ready(text: str) -> bool:
    return "Weekly views" in text or "Weekly Top Songs" in text or len(text) > 3000


async def detect_captcha(page) -> bool:
    try:
        return bool(await page.evaluate(_JS_CAPTCHA))
    except Exception:
        return False


async def humanize(page) -> None:
    """Movimientos de mouse y scroll leves; barato y no hace dano."""
    try:
        for x, y in ((300, 300), (640, 420), (900, 300), (500, 600)):
            await page.mouse.move(x, y, steps=12)
            await page.wait_for_timeout(250)
        await page.mouse.wheel(0, 300)
    except Exception:
        pass


async def accept_consent(page) -> None:
    for label in (r"^Accept all$", r"^Reject all$", r"^Aceptar todo$", r"^Rechazar todo$"):
        try:
            btn = page.get_by_role("button", name=re.compile(label, re.I))
            if await btn.count() > 0:
                await btn.first.click(timeout=3000)
                log.info("Click en consentimiento: %s", label)
                await page.wait_for_timeout(1500)
                return
        except Exception:
            continue


async def wait_for_chart(page, wait_s: int, interactive: bool) -> str:
    """Devuelve 'ok', 'captcha' o 'timeout'."""
    start = time.monotonic()
    limit = max(wait_s, 180) if interactive else wait_s
    captcha_since: Optional[float] = None
    while time.monotonic() - start < limit:
        if chart_ready(await page_text(page)):
            return "ok"
        if await detect_captcha(page):
            if captcha_since is None:
                captcha_since = time.monotonic()
                if interactive:
                    log.warning("Captcha visible: resuelvelo a mano en la ventana (hasta %d s).", limit)
                else:
                    log.warning("Captcha visible y no hay humano: se esperan %d s por si se resuelve solo.", CAPTCHA_GRACE_S)
            if not interactive and time.monotonic() - captcha_since > CAPTCHA_GRACE_S:
                return "captcha"
        else:
            captcha_since = None
        await asyncio.sleep(3)
    return "captcha" if await detect_captcha(page) else "timeout"


async def extract_rows(page) -> List[Dict[str, Any]]:
    try:
        data = await page.evaluate(_JS_EXTRACT_DOM)
    except Exception as e:
        log.info("Extraccion DOM fallo: %s", e)
        return []
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for r in data:
        if not _clean_text(r.get("Track Name")):
            continue
        url = r.get("YouTube URL", "")
        if url and url in seen:
            continue
        seen.add(url)
        out.append(r)
    for i, r in enumerate(out, 1):  # sin huecos en el ranking
        r["Rank"] = i
    return out


async def save_debug(page, url: str, tag: str) -> None:
    """Captura + HTML + texto en logs/debug/ (el workflow sube logs/)."""
    try:
        dbg = LOGS_DIR / "debug"
        dbg.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            await page.screenshot(path=str(dbg / f"debug_{tag}_{ts}.png"), timeout=15_000)
            log.info("Debug: screenshot logs/debug/debug_%s_%s.png", tag, ts)
        except Exception as e:
            log.info("Debug screenshot fallo: %s", e)
        try:
            html = await page.content()
            (dbg / f"debug_{tag}_{ts}.html").write_text(html, encoding="utf-8")
        except Exception as e:
            log.info("Debug HTML fallo: %s", e)
        txt = await page_text(page)
        (dbg / f"debug_{tag}_{ts}.txt").write_text(
            f"URL: {url}\nFinal URL: {page.url}\nTexto ({len(txt)} chars):\n{txt[:8000]}", encoding="utf-8"
        )
        log.info("Debug: texto visible %d chars, snippet: %s", len(txt), txt[:300].replace("\n", " | "))
    except Exception as e:
        log.info("Debug fallo: %s", e)


def browser_args(headless: bool) -> List[str]:
    args = ["--disable-blink-features=AutomationControlled", "--window-size=1920,1080"]
    if not headless:
        args.append("--start-maximized")
    if IS_LINUX:
        args.append("--disable-dev-shm-usage")
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            args.append("--no-sandbox")  # solo hace falta como root
    return args


async def download_youtube_charts(
    chart: str,
    country: str,
    *,
    headless: bool,
    use_chrome: bool,
    keep_profile: bool,
    interactive: bool,
    wait_s: int,
    min_rows: int,
) -> Optional[Path]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.error("Playwright no esta instalado en este entorno")
        return None

    ensure_directories()
    filename = ARCHIVE_DIR / "latest_chart.csv"
    log.info("Descargando YouTube Charts %s / %s (headless=%s, chrome=%s, perfil=%s)", chart, country, headless, use_chrome, keep_profile)

    async with async_playwright() as p:
        browser = None
        context = None
        try:
            ctx_opts: Dict[str, Any] = {"locale": "en-US"}  # el parser busca textos en ingles
            if BROWSER_TZ:
                ctx_opts["timezone_id"] = BROWSER_TZ
            if headless:
                ctx_opts["viewport"] = {"width": 1920, "height": 1080}
            else:
                ctx_opts["no_viewport"] = True  # ventana y viewport coherentes

            launch_opts: Dict[str, Any] = dict(
                headless=headless,
                args=browser_args(headless),
                ignore_default_args=["--enable-automation"],
            )
            if use_chrome:
                launch_opts["channel"] = "chrome"

            if keep_profile:
                PROFILE_DIR.mkdir(parents=True, exist_ok=True)
                log.info("Perfil persistente: %s", PROFILE_DIR)
                try:
                    context = await p.chromium.launch_persistent_context(str(PROFILE_DIR), **launch_opts, **ctx_opts)
                except Exception as e:
                    log.error("No se pudo abrir el perfil (si hay otro Chrome usando %s, cierralo): %s", PROFILE_DIR, e)
                    return None
            else:
                browser = await p.chromium.launch(**launch_opts)
                context = await browser.new_context(**ctx_opts)

            page = context.pages[0] if context.pages else await context.new_page()
            page.set_default_timeout(60_000)
            try:
                log.info("User-Agent real: %s", await page.evaluate("navigator.userAgent"))
            except Exception:
                pass

            for url in get_chart_urls(chart, country):
                log.info("Navegando a %s", url)
                try:
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                    except Exception as e:
                        log.info("goto fallo, sigo: %s", e)
                    await page.wait_for_timeout(3000)
                    await humanize(page)
                    await accept_consent(page)

                    state = await wait_for_chart(page, wait_s, interactive)
                    log.info("Estado de la pagina: %s", state)

                    for _ in range(5):  # carga contenido dinamico
                        try:
                            await page.evaluate("window.scrollBy(0, 900)")
                        except Exception:
                            pass
                        await page.wait_for_timeout(1200)
                    try:
                        await page.evaluate("window.scrollTo(0, 0)")
                    except Exception:
                        pass
                    await page.wait_for_timeout(1000)

                    rows = await extract_rows(page)
                    log.info("Filas extraidas en %s: %d", url, len(rows))
                    if len(rows) >= min_rows:
                        return save_rows_to_csv(rows, filename)

                    await save_debug(page, url, state)
                    if state == "captcha":
                        log.error("CAPTCHA en %s. Sin humano no se puede continuar (ver README: perfil persistente / runner propio).", url)
                        break  # la otra URL daria lo mismo
                    log.warning("Pocas filas (%d < %d) en %s, pruebo la siguiente URL...", len(rows), min_rows, url)
                except Exception as e:
                    log.warning("Error en %s: %s", url, e)

            log.error("No se pudo descargar el chart desde ninguna URL")
            return None
        finally:
            for closable in (context, browser):
                try:
                    if closable is not None:
                        await closable.close()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def _main_inner(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="YouTube Charts scraper (v3)")
    ap.add_argument("--country", default="global", help="global, us, cl ...")
    ap.add_argument("--chart", default="TopSongs", help="TopSongs, TopArtists ...")
    ap.add_argument("--week", default=None, help="Forzar week_id (ej. 2026-W47). Por defecto, la semana ISO actual")
    ap.add_argument("--force", action="store_true", help="Re-scrapear aunque la semana ya tenga datos reales")
    ap.add_argument("--terminal", action="store_true", help="No interactivo: nunca espera Enter ni captcha manual. NO es headless")
    ap.add_argument("--headless", action="store_true", help="Sin ventana (NO recomendado: mas captcha)")
    ap.add_argument("--use-chrome", action="store_true", help="Usa Google Chrome instalado (channel=chrome)")
    ap.add_argument("--no-profile", action="store_true", help="Perfil temporal limpio en vez del persistente")
    ap.add_argument("--wait", type=int, default=75, help="Segundos max. esperando el chart (modo no interactivo)")
    ap.add_argument("--min-rows", type=int, default=50, help="Minimo de filas para aceptar el resultado")
    ap.add_argument("--open-folder", action="store_true", help="Abre la carpeta de salida al terminar bien")
    ap.add_argument("--pause", action="store_true", help="Espera Enter al terminar")
    # Compatibilidad con lanzadores viejos (ignorados):
    ap.add_argument("--show-browser", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--allow-fallback", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    print("\n" + "=" * 70)
    print("YOUTUBE CHARTS - EXTRACTOR v3")
    print(f"Chart: {args.chart} / Pais: {args.country}")
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 70)

    ensure_directories()
    setup_file_logging()
    if args.allow_fallback:
        log.warning("--allow-fallback ya no existe: nunca se guardan datos sinteticos")
    if args.no_browser:
        log.warning("--no-browser ya no existe: solo hay extraccion con navegador")

    week_id = args.week or get_week_identifier()
    log.info("Semana: %s | base=%s", week_id, BASE_DIR)
    if not args.force and week_already_done(week_id):
        log.info("Semana %s ya tiene datos reales. Saltando (usa --force para re-scrapear).", week_id)
        return 0

    print("\n0. VERIFICANDO ENTORNO...")
    import importlib.util

    if importlib.util.find_spec("playwright") is None:
        log.error("Playwright no esta instalado. Activa tu venv: pip install -r requirements-ci.txt")
        return 1
    if args.use_chrome and not chrome_available():
        log.error("--use-chrome pedido pero no encuentro Google Chrome (sudo apt install ./google-chrome-stable_current_amd64.deb)")
        return 1
    headless = args.headless
    if not headless and not has_display():
        log.error("No hay DISPLAY. Corre con xvfb-run -a -s \"-screen 0 1920x1080x24\" <comando> (o --headless, con mas riesgo de captcha).")
        return 1
    if headless:
        log.warning("--headless explicito: en headless Google muestra captcha con mucha mas frecuencia.")
    interactive = (not args.terminal) and (not headless)

    print("\n1. DESCARGANDO YOUTUBE CHARTS...")
    csv_path: Optional[Path] = None
    try:
        csv_path = asyncio.run(
            download_youtube_charts(
                args.chart,
                args.country,
                headless=headless,
                use_chrome=args.use_chrome,
                keep_profile=not args.no_profile,
                interactive=interactive,
                wait_s=args.wait,
                min_rows=args.min_rows,
            )
        )
    except Exception as e:
        log.error("Error en descarga: %s", e, exc_info=True)

    print("\n2. VALIDANDO CSV...")
    if csv_path is None or not Path(csv_path).exists():
        log.error("CRITICO: no se obtuvo el chart real. No se guarda nada en la DB.")
        return 2
    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
        num_songs = max(sum(1 for _ in f) - 1, 0)
    log.info("Canciones en CSV: %d", num_songs)
    if num_songs < args.min_rows:
        log.error("CSV con %d canciones (< %d). Abortando sin guardar en la DB.", num_songs, args.min_rows)
        return 2
    if num_songs < 100:
        log.warning("El chart deberia tener 100 canciones y se obtuvieron %d. Revisa el screenshot de logs/debug/.", num_songs)

    print("\n3. GUARDANDO EN SQLITE...")
    if not update_sqlite_database(Path(csv_path), week_id):
        log.error("Error critico actualizando la DB")
        return 1

    print("\n4. LIMPIANDO ARCHIVOS VIEJOS...")
    cleanup_old_backups(7)
    cleanup_old_databases(52)

    print("\n5. RESUMEN FINAL:")
    list_available_databases()
    print("\n" + "=" * 70)
    print("PROCESO COMPLETADO - DATOS REALES")
    print("=" * 70)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    code = _main_inner(argv)
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    if "--open-folder" in argv_list and code == 0:
        open_folder(ARCHIVE_DIR)
    try:
        has_tty = sys.stdin.isatty()
    except Exception:
        has_tty = False
    non_interactive = IS_CI or "--terminal" in argv_list
    if not non_interactive and ("--pause" in argv_list or not has_tty):
        try:
            input("\nPresiona Enter para cerrar...")
        except Exception:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
