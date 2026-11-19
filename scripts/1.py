"""
YouTube Charts Data Scraper - v4 FINAL (GitHub Actions ready)
=============================================================
Descarga el chart semanal (TopSongs / global, 100 canciones) y lo guarda
como CSV + SQLite. Si no puede obtener datos REALES sale con codigo 2 y no
escribe nada en la DB (no hay datos sinteticos).

Disenado para correr en GitHub Actions (ubuntu-latest) con xvfb-run.
Tambien funciona en local con Chrome instalado.

Como se invoca
--------------
GitHub Actions (lo que usa el workflow):
    xvfb-run -a --server-args="-screen 0 1920x1080x24" \\
        python 1.py --terminal --wait 90 --min-rows 50

Local PC Linux (con escritorio, ventana visible):
    python 1.py --show-browser --use-chrome --pause

Local PC Linux (sin escritorio, monitor virtual):
    xvfb-run -a --server-args="-screen 0 1920x1080x24" \\
        python 1.py --terminal

Por que --terminal NO es --headless
------------------------------------
--terminal significa "no interactivo" (sin input(), sin esperar Enter,
captcha maximo 20s). NO significa "sin ventana". Con xvfb-run -a hay
DISPLAY, entonces Playwright corre en modo HEADED (con ventana virtual),
que es lo que evita el captcha de Google. Si corres --terminal SIN
xvfb-run y SIN DISPLAY, el script falla rapido con error claro (antes
caia a headless silenciosamente y se comia el captcha).

Que cambio respecto a v3
------------------------
- --terminal sin DISPLAY ahora falla con exit 1 y mensaje claro.
- --use-chrome se ignora automaticamente si Chrome no esta instalado
  (GitHub Actions no trae Chrome, solo Chromium de Playwright).
- Codigo muerto de youtubei eliminado (Charts 2026 no lo usa).
- Deteccion de captcha corregida para Polymer: usa texto de shadow DOM,
  no body.innerText (que en Polymer siempre es 0 aunque el chart este
  visible). Esto evita el falso positivo "captcha" cuando en realidad
  el chart ya cargo.

Codigos de salida: 0 ok, 1 error, 2 sin datos reales (captcha, bloqueo, etc.)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
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
    for p in [OUTPUT_DIR, ARCHIVE_DIR, DATABASE_DIR, BACKUP_DIR, LOGS_DIR]:
        p.mkdir(parents=True, exist_ok=True)


def setup_local_logging() -> None:
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOGS_DIR / f"scraper_{datetime.now().strftime('%Y-%m-%d')}.log"
        if not any(isinstance(h, logging.FileHandler) for h in log.handlers):
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            log.addHandler(fh)
            log.info("Log en: %s", log_file)
    except Exception as e:
        log.warning("No se pudo crear log en archivo: %s", e)


def has_display() -> bool:
    if not IS_LINUX:
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _chrome_available() -> bool:
    """True si Google Chrome esta instalado (no Chromium de Playwright)."""
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
        args.insert(0, "--no-sandbox")
        args.insert(1, "--disable-dev-shm-usage")
    elif not IS_WINDOWS:
        args.insert(0, "--no-sandbox")
        args.insert(1, "--disable-dev-shm-usage")
    return args


def open_folder_local(path: Path) -> None:
    try:
        p = str(Path(path).resolve())
        log.info("Abriendo carpeta: %s", p)
        if IS_LINUX:
            subprocess.Popen(
                ["xdg-open", p],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif IS_MAC:
            subprocess.run(["open", p], check=False)
        elif IS_WINDOWS:
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", p], check=False)
    except Exception as e:
        log.warning("No se pudo abrir la carpeta %s: %s", path, e)


# ---------------------------------------------------------------------------
# DEPENDENCY MANAGEMENT
# ---------------------------------------------------------------------------
def install_playwright() -> bool:
    log.info("Verificando Playwright...")
    import importlib.util

    if importlib.util.find_spec("playwright") is None:
        log.error("Playwright no esta instalado en este venv.")
        log.error("Activa tu venv y corre: pip install playwright pandas")
        log.error("Luego: python -m playwright install chromium")
        return False
    log.info("Playwright esta instalado")

    dry = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
        capture_output=True,
        text=True,
    )
    if dry.returncode == 0:
        log.info("Chromium ya esta instalado")
        return True

    log.info("Instalando Chromium...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        log.info("Chromium instalado")
        return True
    log.error("Error instalando Chromium: %s", result.stderr[-2000:])
    return False


# ---------------------------------------------------------------------------
# WEEK IDENTIFIER
# ---------------------------------------------------------------------------
def get_week_identifier(date: Optional[datetime] = None) -> str:
    if date is None:
        date = datetime.now()
    year, week_num, _ = date.isocalendar()
    return f"{year}-W{week_num:02d}"


def get_chart_urls(chart: str = "TopSongs", country: str = "global") -> List[str]:
    chart = chart.strip() or "TopSongs"
    country = country.strip() or "global"
    return [
        f"https://charts.youtube.com/charts/{chart}/{country}",
        f"https://charts.youtube.com/charts/{chart}/{country}/weekly",
    ]


# ---------------------------------------------------------------------------
# PARSING HELPERS
# ---------------------------------------------------------------------------
def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_views(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().replace(",", "").replace(" ", "")
    s = re.sub(r"(views|reproducciones|vistas)$", "", s, flags=re.I).strip()
    if not s:
        return None
    mult = 1
    if s[-1] in ("K", "k"):
        mult, s = 1_000, s[:-1]
    elif s[-1] in ("M", "m"):
        mult, s = 1_000_000, s[:-1]
    elif s[-1] in ("B", "b"):
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
    if not out["YouTube URL"] and raw.get("videoId"):
        out["YouTube URL"] = f"https://www.youtube.com/watch?v={raw['videoId']}"
    if not out["YouTube URL"] and raw.get("video_id"):
        out["YouTube URL"] = f"https://www.youtube.com/watch?v={raw['video_id']}"
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
    rows: List[Dict[str, Any]] = []
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(csv_path, "r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    return []
                has_synth = any(
                    (fn or "").strip().lower() in ("is_synthetic", "is-synthetic")
                    for fn in reader.fieldnames
                )
                for i, raw in enumerate(reader):
                    norm = _normalize_row(raw, i + 1)
                    if has_synth:
                        for k, v in raw.items():
                            if str(k).strip().lower() in ("is_synthetic", "is-synthetic"):
                                try:
                                    norm["_is_synthetic"] = (
                                        int(float(str(v)))
                                        if str(v).strip() != ""
                                        else 0
                                    )
                                except ValueError:
                                    norm["_is_synthetic"] = (
                                        1
                                        if str(v).strip().lower()
                                        in ("1", "true", "yes")
                                        else 0
                                    )
                    rows.append(norm)
            break
        except UnicodeDecodeError:
            continue
    return rows


# ---------------------------------------------------------------------------
# BACKUP MANAGEMENT
# ---------------------------------------------------------------------------
def create_backup_before_update(week_id: str) -> Optional[Path]:
    db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
    if not db_path.exists():
        return None
    ensure_directories()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = BACKUP_DIR / f"backup_{week_id}_{timestamp}.db"
    try:
        shutil.copy2(db_path, backup_path)
        log.info("Backup creado: %s", backup_path.name)
        return backup_path
    except Exception as e:
        log.warning("Error creando backup: %s", e)
        return None


def cleanup_old_backups(days: int = 7) -> None:
    log.info("Limpiando backups con mas de %d dias...", days)
    if not BACKUP_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=days)
    deleted = 0
    for backup in BACKUP_DIR.glob("backup_*.db"):
        try:
            if backup.stat().st_mtime < cutoff.timestamp():
                backup.unlink()
                deleted += 1
        except Exception as e:
            log.warning("Error borrando %s: %s", backup.name, e)
    log.info("Backups eliminados: %d", deleted)


def cleanup_old_databases(weeks: int = 52) -> None:
    log.info("Limpiando bases con mas de %d semanas...", weeks)
    if not DATABASE_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(weeks=weeks)
    deleted = 0
    for db in DATABASE_DIR.glob("youtube_charts_*.db"):
        try:
            week_id = db.stem.replace("youtube_charts_", "")
            year_str, week_str = week_id.split("-W")
            year, week = int(year_str), int(week_str)
            db_date = datetime.fromisocalendar(year, week, 1)
            if db_date < cutoff:
                db.unlink()
                deleted += 1
                log.info("Eliminada: %s", db.name)
        except Exception as e:
            log.warning("Error procesando %s: %s", db.name, e)
    log.info("Bases eliminadas: %d", deleted)


# ---------------------------------------------------------------------------
# SQLITE DATABASE UPDATE
# ---------------------------------------------------------------------------
def update_sqlite_database(
    csv_path: Path, week_id: str, is_synthetic: bool = False
) -> Optional[Path]:
    log.info("Procesando chart data desde %s ...", csv_path)
    rows = _read_csv_normalized(Path(csv_path))
    if not rows:
        log.error("CSV vacio o sin filas validas: %s", csv_path)
        return None

    for r in rows:
        if "_is_synthetic" not in r:
            r["_is_synthetic"] = 1 if is_synthetic else 0

    log.info("Canciones cargadas: %d", len(rows))
    for i, r in enumerate(rows[:5]):
        log.info(
            "  %d. %s - %s",
            i + 1,
            str(r.get("Track Name", ""))[:40],
            str(r.get("Artist Names", ""))[:40],
        )

    ensure_directories()
    db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
    if db_path.exists():
        log.info("Creando backup antes de actualizar...")
        create_backup_before_update(week_id)

    now = datetime.now()
    download_date = now.strftime("%Y-%m-%d")
    download_time = now.strftime("%H:%M:%S")
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    all_cols = CANONICAL_COLUMNS + [
        "download_date",
        "download_time",
        "week_id",
        "timestamp",
        "is_synthetic",
    ]

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
                    cur.execute(
                        "ALTER TABLE chart_data ADD COLUMN is_synthetic INTEGER DEFAULT 0"
                    )
                except sqlite3.OperationalError:
                    pass

            cur.execute("DELETE FROM chart_data WHERE week_id = ?", (week_id,))
            deleted = cur.rowcount
            if deleted:
                log.info("Eliminados %d registros viejos para %s", deleted, week_id)

            placeholders = ", ".join(["?"] * len(all_cols))
            quoted = ", ".join([f'"{c}"' for c in all_cols])
            sql = f"INSERT INTO chart_data ({quoted}) VALUES ({placeholders})"

            to_insert = []
            for r in rows:
                vals = []
                for c in CANONICAL_COLUMNS:
                    v = r.get(c, "")
                    if c in ("Rank", "Previous Rank", "Periods on Chart", "Views") and v == "":
                        v = None
                    vals.append(v)
                vals.extend(
                    [
                        download_date,
                        download_time,
                        week_id,
                        timestamp,
                        int(r.get("_is_synthetic", 0)),
                    ]
                )
                to_insert.append(tuple(vals))

            cur.executemany(sql, to_insert)

            indices = [
                ("idx_date", "chart_data(download_date)"),
                ("idx_week", "chart_data(week_id)"),
                ("idx_rank", 'chart_data("Rank")'),
                ("idx_artist", 'chart_data("Artist Names")'),
            ]
            for idx_name, idx_cols in indices:
                try:
                    cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_cols}")
                except sqlite3.OperationalError as e:
                    log.warning("No se pudo crear indice %s: %s", idx_name, e)

            conn.commit()

            cur.execute("SELECT COUNT(*) FROM chart_data")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT download_date) FROM chart_data")
            uniq = cur.fetchone()[0]
            log.info(
                "DB actualizada: total=%d fechas_distintas=%d path=%s",
                total,
                uniq,
                db_path,
            )
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
        log.info("Check idempotencia fallo (ignorado): %s", e)
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
            log.info(
                "  %s: %d registros, %.1f KB",
                db.stem.replace("youtube_charts_", ""),
                count,
                db.stat().st_size / 1024,
            )
        except Exception as e:
            log.warning("Error leyendo %s: %s", db.name, e)
    log.info("TOTAL: %d registros en %d bases", total, len(dbs))


# ---------------------------------------------------------------------------
# FALLBACK (solo para pruebas manuales)
# ---------------------------------------------------------------------------
def create_fallback_file(week_id: str, reason: str = "") -> Optional[Path]:
    log.warning("Creando fallback SINTETICO (no es dato real). Motivo: %s", reason)
    ensure_directories()
    rows: List[Dict[str, Any]] = []
    for i in range(1, 101):
        rows.append(
            {
                "Rank": i,
                "Previous Rank": max(1, i - 1) if i > 1 else 1,
                "Track Name": f"Popular Song {i}",
                "Artist Names": f"Artist {chr(65 + ((i - 1) % 26))} and Collaborators",
                "Periods on Chart": 10 + (i % 40),
                "Views": 5_000_000 + (100 - i) * 50_000,
                "Growth": f"{((101 - i) / 100):.2f}%",
                "YouTube URL": f"https://www.youtube.com/watch?v=example{i:03d}",
            }
        )
    filename = ARCHIVE_DIR / f"fallback_chart_{week_id}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        fieldnames = CANONICAL_COLUMNS + ["is_synthetic"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            norm = _normalize_row(r, r["Rank"])
            norm["is_synthetic"] = 1
            writer.writerow({**norm, "is_synthetic": 1})
    log.warning("Fallback creado en %s (100 registros SINTETICOS)", filename)
    return filename


# ---------------------------------------------------------------------------
# EXTRACCION DOM (con shadow roots)
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

  // 1) Tablas clasicas
  const tableRows = document.querySelectorAll('table tbody tr');
  if (tableRows.length >= 20) {
    tableRows.forEach((tr, idx) => {
      const cells = Array.from(tr.querySelectorAll('td, th'))
        .map((c) => c.innerText.trim())
        .filter(Boolean);
      const link = tr.querySelector('a[href]');
      const href = link ? link.getAttribute('href') : '';
      if (cells.length >= 2) {
        rows.push({
          Rank: idx + 1,
          'Track Name': cells[1] || '',
          'Artist Names': cells[2] || '',
          'Views': cells[3] || '',
          'YouTube URL': href || '',
        });
      }
    });
    if (rows.length >= 20) return rows;
  }

  // 2) Filas de chart por clase
  const rowCands = allEls.filter((el) => {
    const cls = (el.className || '').toString().toLowerCase();
    return cls.includes('chart-row') || cls.includes('chart-item') || cls.includes('row-chart');
  });
  for (const rowEl of rowCands) {
    const txt = getText(rowEl);
    if (!txt || txt.length < 10 || txt.length > 500) continue;
    const lines = txt.split('\n').map((s) => s.trim()).filter(Boolean);
    if (lines.length < 3) continue;
    let rank = parseInt(lines[0], 10);
    if (isNaN(rank) || rank < 1 || rank > 200) {
      const m = txt.match(/^\s*(\d{1,3})\s/);
      if (!m) continue;
      rank = parseInt(m[1], 10);
    }
    const hrefEl = rowEl.querySelector ? rowEl.querySelector('a[href*="watch"], a[href*="youtu"]') : null;
    let href = hrefEl ? hrefEl.getAttribute('href') || '' : '';
    if (!href) {
      const a2 = rowEl.querySelector ? rowEl.querySelector('a[href]') : null;
      if (a2) href = a2.getAttribute('href') || '';
    }
    let vid = '';
    if (href) {
      const mm = href.match(/v=([A-Za-z0-9_-]{11})/) || href.match(/youtu\.be\/([A-Za-z0-9_-]{11})/);
      if (mm) vid = mm[1];
    }
    let title = '', artist = '', viewsRaw = '';
    const nonRank = lines.filter((l) => !/^\d+$/.test(l));
    if (nonRank.length >= 1) title = nonRank[0];
    if (nonRank.length >= 2) artist = nonRank[1];
    for (const l of lines) {
      if (/[\d,.]+\s*[KMB]?\s*(views|reproducciones|vistas)/i.test(l) || /^[\d,.]+[KMB]?$/.test(l)) viewsRaw = l;
    }
    if (title && artist) {
      const key = rank + '|' + title;
      if (!seen.has(key)) {
        seen.add(key);
        rows.push({
          Rank: rank,
          'Track Name': title,
          'Artist Names': artist,
          'Views': viewsRaw,
          'Views Raw': viewsRaw,
          'YouTube URL': vid ? 'https://www.youtube.com/watch?v=' + vid : href,
          videoId: vid,
        });
      }
    }
  }
  if (rows.length >= 20) {
    rows.sort((a, b) => a.Rank - b.Rank);
    return rows;
  }

  // 3) Links a videos
  for (const el of allEls) {
    if (el.tagName !== 'A') continue;
    const href = el.getAttribute('href') || '';
    if (!href) continue;
    const m =
      href.match(/v=([A-Za-z0-9_-]{11})/) ||
      href.match(/youtu\.be\/([A-Za-z0-9_-]{11})/) ||
      href.match(/\/watch\/([A-Za-z0-9_-]{11})/);
    const vid = m ? m[1] : '';
    const container = el.closest ? el.closest('tr, li, [role="row"], [class*="row"], [class*="item"], [class*="chart"]') : null;
    const text = container ? container.innerText : getText(el);
    const lines = (text || '').split('\n').map((s) => s.trim()).filter(Boolean);
    if (vid) {
      if (seen.has(vid)) continue;
      seen.add(vid);
    } else {
      if (lines.length < 3) continue;
      const key = (getText(el) + '|' + lines.join('|')).slice(0, 200);
      if (seen.has(key)) continue;
      if (!/[0-9]/.test(text)) continue;
      seen.add(key);
    }
    let title = (el.getAttribute('aria-label') || getText(el) || '').trim().split('\n')[0] || lines[1] || lines[0] || '';
    title = title.replace(/^\d+\.\s*/, '').replace(/^\d+\s+/, '');
    let artist = '', viewsRaw = '';
    for (const l of lines) {
      if (/[\d,.]+\s*[KMB]?\s*(views|reproducciones|vistas)/i.test(l)) viewsRaw = l;
    }
    for (const l of lines) {
      if (l !== title && l !== viewsRaw && !/^\d+$/.test(l) && l.length > 1 && l.length < 90) {
        artist = l;
        break;
      }
    }
    rows.push({
      Rank: rows.length + 1,
      'Track Name': title,
      'Artist Names': artist,
      'Views': viewsRaw,
      'Views Raw': viewsRaw,
      'YouTube URL': vid ? 'https://www.youtube.com/watch?v=' + vid : href,
      videoId: vid,
    });
  }
  return rows;
}
"""


async def _extract_via_dom(page) -> List[Dict[str, Any]]:
    try:
        data = await page.evaluate(_JS_EXTRACT_DOM)
        if not isinstance(data, list):
            return []
        out = [r for r in data if _clean_text(r.get("Track Name"))]
        seen = set()
        dedup = []
        for r in out:
            u = r.get("YouTube URL", "")
            if u and u in seen:
                continue
            seen.add(u)
            dedup.append(r)
        for i, r in enumerate(dedup, 1):
            r["Rank"] = i
        log.info("Extraccion DOM: %d filas", len(dedup))
        return dedup
    except Exception as e:
        log.info("Extraccion DOM fallo: %s", e)
        return []


async def _get_page_text_with_shadow(page) -> str:
    """Charts es Polymer: el texto real esta en shadow DOM, NO en body.innerText."""
    try:
        txt = await page.evaluate(
            """() => {
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
                        root.querySelectorAll('*').forEach((el) => {
                            if (el.shadowRoot) walk(el.shadowRoot);
                        });
                    }
                };
                walk(document);
                if (document.body && document.body.innerText) out.push(document.body.innerText);
                return out.join('\\n');
            }"""
        )
        return txt or ""
    except Exception as e:
        log.info("Shadow text fallo: %s", e)
        return ""


async def _detect_captcha(page) -> bool:
    """Detecta captcha REAL. Polymer: body.innerText es 0 aunque el chart este visible."""
    try:
        shadow_txt = await _get_page_text_with_shadow(page)
        low = (shadow_txt or "").lower()
        has_chart = ("weekly top songs" in low
