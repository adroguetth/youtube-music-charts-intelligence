"""
YouTube Charts Data Scraper - VERSION LOCAL PC (NO GitHub Actions)
================================================
Scraper automatizado para descargar datos semanales de YouTube Charts
y guardarlos en SQLite.

VERSION LOCAL PC LINUX - NO GitHub Actions, NO Windows
-----------------------------------
Esta version esta pensada para correr en TU PC con Linux
desde terminal o con doble clic en run_local.sh, no en un runner de CI
ni en Windows.
Diferencias clave vs la version para CI:
- Usa tu Chrome instalado si lo tienes (--use-chrome) en vez de solo Chromium
  descargado: se ve menos como bot y no tienes que instalar nada extra.
- Guarda un perfil persistente en .browser-profile/ : guarda cookies y el
  consentimiento, asi no tienes que aceptar cookies en cada corrida y
  YouTube te bloquea menos.
- CON --no-sandbox y --disable-dev-shm-usage en Linux (en Linux si hacen
  falta, sobre todo si corres como root o sin /dev/shm grande).
- Usa venv .venv/ porque en Ubuntu/Debian pip install sin venv esta
  bloqueado por PEP 668 (externally-managed-environment).
- Zona horaria local America/Santiago por defecto en PC local.
- Logs en logs/scraper_YYYY-MM-DD.log ademas de pantalla.
- --show-browser para ver el navegador y resolver captcha a mano si aparece.
    ap.add_argument("--headless", action="store_true", help="Forzar modo sin ventana (NO recomendado: en headless Google muestra captcha)")
- --pause para que la ventana no se cierre al hacer doble clic.
- --open-folder para abrir la carpeta con el CSV y la DB al terminar.
- Detecta si lo corres por error en GitHub Actions y avisa.
- Lanzadores Linux incluidos: run_local.sh (doble clic o ./run_local.sh) y
  setup_local.sh (instala Python, venv y dependencias del sistema).

POR QUE DEJO DE FUNCIONAR DE UN DIA PARA OTRO
----------------------------------------------
1. YouTube redisenio Charts (julio 2025, cuando Trending paso a ser Charts).
   El boton viejo de descarga desaparecio:
   - #download-button  -> ya no existe
   - paper-icon-button[title="download"] -> ya no existe (era Polymer)
   El script buscaba solo ese boton, asi que siempre terminaba en None
   y caia al fallback con datos falsos.
2. La URL cambio: antes era
   https://charts.youtube.com/charts/TopSongs/global/weekly
   ahora la canonica es
   https://charts.youtube.com/charts/TopSongs/global
   La version con /weekly redirige y a veces rompe el flujo.
3. Aparecio muro de consentimiento / cookies que tapa la tabla si no
   se hace click en Aceptar / Rechazar.
4. Deteccion anti-bot mas estricta en headless.

COMO LO ARREGLA ESTA VERSION
----------------------------
- Ya NO depende del boton de descarga. Estrategia en orden:
  1. Extrae la tabla renderizada en el DOM y construye el CSV.
  2. Intercepta las respuestas JSON de youtubei / charts y las parsea.
  3. Intenta el boton de descarga con selectores modernos (rol ARIA,
     texto download / descargar / export) solo como ultimo recurso.
  4. Intenta HTTP directo parseando ytInitialData del HTML.
- Prueba las dos URLs (nueva y vieja) con reintentos.
- Maneja el banner de consentimiento.
- Cierra el navegador siempre con try/finally.
- Corrige bugs del script original:
  * Path | None rompia en Python 3.7-3.9 -> ahora usa Optional y
    from __future__ import annotations.
  * install_playwright() capturaba ImportError pero subprocess
    lanza CalledProcessError -> ahora lo maneja bien.
  * No se creaban carpetas al importar -> ahora solo en main().
  * Rutas relativas a cwd -> ahora relativas a __file__.
  * cleanup_old_databases() usaba %W (no ISO) -> ahora fromisocalendar.
  * Indices con "Artist Names" sin comillas fallaban en silencio ->
    ahora con identificadores entre comillas.
  * El fallback se guardaba como si fuera real -> ahora lleva
    columna is_synthetic=1, archivo separado fallback_chart_*.csv
    y por defecto NO se escribe a la DB. Solo se escribe si pasas
    --allow-fallback. Asi nunca mas contaminas el historico.
  * update_sqlite_database() usaba to_sql + temp table + DROP en
    mismatch (perdia datos) -> ahora esquema explicito, DELETE por
    week_id + INSERT con lista de columnas, en transaccion.
  * OUTPUT_DIR sin uso, pasos numerados 0,1,3,4,5, etc.

Uso:
    python youtube_charts_scraper_fixed.py
    python youtube_charts_scraper_fixed.py --country global --chart TopSongs
    python youtube_charts_scraper_fixed.py --allow-fallback   # solo pruebas
    python youtube_charts_scraper_fixed.py --no-browser       # solo HTTP

Requisitos: Python 3.8+, playwright (se auto-instala si falta).
Autor original: Alfonso Droguett
Repo: https://github.com/adroguetth/youtube-music-charts-intelligence
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
# CONSTANTS AND DIRECTORIES - sin efectos al importar
# ---------------------------------------------------------------------------
try:
    BASE_DIR = Path(__file__).resolve().parent
except NameError:
    BASE_DIR = Path.cwd()

# Permite sobreescribir la base con variable de entorno
if os.environ.get("YOUTUBE_CHARTS_BASE_DIR"):
    BASE_DIR = Path(os.environ["YOUTUBE_CHARTS_BASE_DIR"]).expanduser().resolve()

# --- MODO LOCAL vs CI ---
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"
IS_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"
IS_LOCAL = not IS_GITHUB_ACTIONS
# En tu PC en Chile, usa tu zona horaria. En CI se usaba America/New_York.
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
    """Crea las carpetas. Se llama solo desde main(), no al importar."""
    for p in [OUTPUT_DIR, ARCHIVE_DIR, DATABASE_DIR, BACKUP_DIR, LOGS_DIR]:
        p.mkdir(parents=True, exist_ok=True)

def setup_local_logging() -> None:
    """En PC local guarda log en archivo ademas de pantalla. En CI solo pantalla."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOGS_DIR / f"scraper_{datetime.now().strftime('%Y-%m-%d')}.log"
        # Evita duplicar handlers si se llama dos veces
        if not any(isinstance(h, logging.FileHandler) for h in log.handlers):
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
            log.addHandler(fh)
            log.info("Log local en: %s", log_file)
    except Exception as e:
        log.warning("No se pudo crear log en archivo: %s", e)


def get_browser_args() -> list:
    """Args segun SO. En Linux SI se usa --no-sandbox y --disable-dev-shm-usage."""
    args = [
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--window-size=1920,1080",
        "--start-maximized",
    ]
    if IS_LINUX:
        # En Linux hace falta, sobre todo como root o sin /dev/shm grande
        args.insert(0, "--no-sandbox")
        args.insert(1, "--disable-dev-shm-usage")
        args.insert(2, "--disable-setuid-sandbox")
        args.insert(3, "--disable-dev-shm-usage")
    elif not IS_WINDOWS:
        args.insert(0, "--no-sandbox")
        args.insert(1, "--disable-dev-shm-usage")
    return args


def open_folder_local(path: Path) -> None:
    """Abre la carpeta en el explorador de tu PC Linux con xdg-open."""
    try:
        p = str(Path(path).resolve())
        log.info("Abriendo carpeta: %s", p)
        if IS_LINUX:
            # No bloquea la terminal, y funciona en GNOME / KDE / XFCE
            subprocess.Popen(["xdg-open", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif IS_MAC:
            subprocess.run(["open", p], check=False)
        elif IS_WINDOWS:
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", p], check=False)
    except Exception as e:
        log.warning("No se pudo abrir la carpeta %s: %s", path, e)
        log.info("Abrela a mano: %s", path)




# ---------------------------------------------------------------------------
# DEPENDENCY MANAGEMENT - CORREGIDO
# ---------------------------------------------------------------------------
def install_playwright() -> bool:
    """
    Verifica e instala Playwright + Chromium si falta.
    Antes capturaba ImportError pero subprocess.run(check=True) lanza
    CalledProcessError, asi que nunca instalaba nada y main() crasheaba.
    """
    log.info("Verificando Playwright... (Linux: se recomienda usar .venv, ver setup_local.sh)")
    import importlib.util

    # 1. Paquete Python
    # En PC LOCAL LINUX el usuario crea su propio venv e instala con
    # pip install -r requirements.txt. El script NO instala solo con pip,
    # para no romper el venv ni instalar en el Python del sistema (PEP 668).
    if importlib.util.find_spec("playwright") is None:
        if IS_LINUX and IS_LOCAL:
            log.error("Playwright no esta instalado en este venv.")
            log.error("Activa tu venv y corre: pip install -r requirements.txt")
            log.error("Luego: python -m playwright install chromium --with-deps")
            log.error("No se intentara pip install automatico en Linux local.")
            return False
        log.info("Playwright no instalado, instalando con pip...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.error("Error instalando Playwright: %s", result.stderr[-2000:])
            return False
        log.info("Playwright instalado")
    else:
        log.info("Playwright esta instalado")

    # 2. Binarios del navegador
    # --dry-run devuelve 0 si ya esta, distinto de 0 si falta.
    dry = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
        capture_output=True,
        text=True,
    )
    if dry.returncode == 0:
        log.info("Chromium ya esta instalado")
        return True

    if IS_LINUX and IS_LOCAL:
        log.error("Chromium de Playwright no esta instalado.")
        log.error("Corre en tu venv: python -m playwright install chromium --with-deps")
        return False
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
    """Devuelve URLs a probar: primero la nueva, luego la vieja con /weekly."""
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
    """Convierte '1,234,567', '5.2M', '1.1B', '850K' a int. Devuelve None si no se puede."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().replace(",", "").replace(" ", "")
    # Quita sufijos como ' views' / ' reproducciones'
    s = re.sub(r"(views|reproducciones|vistas)$", "", s, flags=re.I).strip()
    if not s:
        return None
    mult = 1
    if s[-1] in ("K", "k"):
        mult = 1_000
        s = s[:-1]
    elif s[-1] in ("M", "m"):
        mult = 1_000_000
        s = s[:-1]
    elif s[-1] in ("B", "b"):
        mult = 1_000_000_000
        s = s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        # Intenta extraer el primer numero
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
    """Normaliza un dict con claves variadas a columnas canonicas."""
    out: Dict[str, Any] = {c: "" for c in CANONICAL_COLUMNS}
    for k, v in raw.items():
        key = str(k).strip().lower()
        canon = COLUMN_ALIASES.get(key, str(k).strip())
        if canon in out:
            out[canon] = v
    # Rank por defecto segun orden
    if not _parse_int(out.get("Rank")):
        out["Rank"] = rank_fallback
    # Views: si viene como texto con M/K, parsea a int y guarda raw
    views_raw = _clean_text(out.get("Views Raw") or out.get("Views"))
    parsed = _parse_views(out.get("Views"))
    if parsed is not None:
        out["Views"] = parsed
        if not out.get("Views Raw"):
            out["Views Raw"] = views_raw
    else:
        out["Views"] = ""
        out["Views Raw"] = views_raw
    # Asegura tipos
    for col in ("Rank", "Previous Rank", "Periods on Chart"):
        val = _parse_int(out.get(col))
        out[col] = val if val is not None else ""
    for col in ("Track Name", "Artist Names", "Growth", "YouTube URL", "Views Raw"):
        out[col] = _clean_text(out.get(col))
    # YouTube URL: si solo viene videoId, construye URL
    if not out["YouTube URL"] and raw.get("videoId"):
        out["YouTube URL"] = f"https://www.youtube.com/watch?v={raw['videoId']}"
    if not out["YouTube URL"] and raw.get("video_id"):
        out["YouTube URL"] = f"https://www.youtube.com/watch?v={raw['video_id']}"
    return out


def save_rows_to_csv(rows: List[Dict[str, Any]], path: Path) -> Path:
    """Guarda filas normalizadas a CSV con header canonico."""
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = [_normalize_row(r, i + 1) for i, r in enumerate(rows)]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        writer.writerows(normalized)
    log.info("CSV guardado: %s (%d filas)", path, len(normalized))
    return path


def _read_csv_normalized(csv_path: Path) -> List[Dict[str, Any]]:
    """Lee un CSV y lo normaliza a columnas canonicas."""
    rows: List[Dict[str, Any]] = []
    # Detecta encoding
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(csv_path, "r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    return []
                # Guarda si hay columna is_synthetic
                has_synth = any(
                    (fn or "").strip().lower() in ("is_synthetic", "is-synthetic")
                    for fn in reader.fieldnames
                )
                for i, raw in enumerate(reader):
                    norm = _normalize_row(raw, i + 1)
                    # Preserva flag sintetico si viene en el CSV
                    if has_synth:
                        for k, v in raw.items():
                            if str(k).strip().lower() in ("is_synthetic", "is-synthetic"):
                                try:
                                    norm["_is_synthetic"] = int(float(str(v))) if str(v).strip() != "" else 0
                                except ValueError:
                                    norm["_is_synthetic"] = 1 if str(v).strip().lower() in ("1", "true", "yes") else 0
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
    # Microsegundos para no pisar un backup del mismo segundo
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
    """CORREGIDO: usa fromisocalendar, no %W que no es ISO."""
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
# SQLITE DATABASE UPDATE - REESCRITO SIN to_sql FRAGIL
# ---------------------------------------------------------------------------
def update_sqlite_database(
    csv_path: Path, week_id: str, is_synthetic: bool = False
) -> Optional[Path]:
    """
    Actualiza SQLite con esquema explicito y transaccion.
    Ya no usa temp table + DROP en mismatch. Hace DELETE por week_id
    y luego INSERT con lista de columnas.
    """
    log.info("Procesando chart data desde %s ...", csv_path)
    rows = _read_csv_normalized(Path(csv_path))
    if not rows:
        log.error("CSV vacio o sin filas validas: %s", csv_path)
        return None

    # Si alguna fila trae _is_synthetic, respeta eso; si no, usa el parametro
    for r in rows:
        if "_is_synthetic" not in r:
            r["_is_synthetic"] = 1 if is_synthetic else 0

    log.info("Canciones cargadas: %d", len(rows))
    for i, r in enumerate(rows[:5]):
        log.info("  %d. %s - %s", i + 1, str(r.get("Track Name", ""))[:40], str(r.get("Artist Names", ""))[:40])

    ensure_directories()
    db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"
    if db_path.exists():
        log.info("Creando backup antes de actualizar...")
        create_backup_before_update(week_id)

    now = datetime.now()
    download_date = now.strftime("%Y-%m-%d")
    download_time = now.strftime("%H:%M:%S")
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    # Columnas: canonicas + metadata
    all_cols = CANONICAL_COLUMNS + ["download_date", "download_time", "week_id", "timestamp", "is_synthetic"]

    try:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            # Esquema explicito con comillas en columnas con espacios
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
            # Migracion suave: si la tabla vieja no tiene is_synthetic, agregala
            cur.execute("PRAGMA table_info(chart_data)")
            existing = {row[1] for row in cur.fetchall()}
            if "is_synthetic" not in existing:
                try:
                    cur.execute("ALTER TABLE chart_data ADD COLUMN is_synthetic INTEGER DEFAULT 0")
                except sqlite3.OperationalError:
                    pass

            # Borrado idempotente solo de esta semana
            cur.execute("DELETE FROM chart_data WHERE week_id = ?", (week_id,))
            deleted = cur.rowcount
            if deleted:
                log.info("Eliminados %d registros viejos para %s", deleted, week_id)

            placeholders = ", ".join(["?"] * len(all_cols))
            quoted = ", ".join([f'"{c}"' for c in all_cols])
            sql = f'INSERT INTO chart_data ({quoted}) VALUES ({placeholders})'

            to_insert = []
            for r in rows:
                vals = []
                for c in CANONICAL_COLUMNS:
                    v = r.get(c, "")
                    # Normaliza vacios a None para INTEGER
                    if c in ("Rank", "Previous Rank", "Periods on Chart", "Views") and v == "":
                        v = None
                    vals.append(v)
                vals.extend([download_date, download_time, week_id, timestamp, int(r.get("_is_synthetic", 0))])
                to_insert.append(tuple(vals))

            cur.executemany(sql, to_insert)

            # Indices con identificadores entre comillas (antes fallaban en silencio)
            indices = [
                ("idx_date", 'chart_data(download_date)'),
                ("idx_week", 'chart_data(week_id)'),
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
            log.info("DB actualizada: total=%d fechas_distintas=%d path=%s", total, uniq, db_path)
            return db_path
        finally:
            conn.close()
    except Exception as e:
        log.error("Error SQLite: %s", e, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# FALLBACK DATA - AHORA MARCADO COMO SINTETICO Y EN ARCHIVO SEPARADO
# ---------------------------------------------------------------------------
def create_fallback_file(week_id: str, reason: str = "") -> Optional[Path]:
    """
    Crea datos sinteticos SOLO para pruebas. Ya no pisa latest_chart.csv
    ni se hace pasar por real: lleva columna is_synthetic y nombre distinto.
    """
    log.warning("Creando fallback SINTETICO (no es dato real). Motivo: %s", reason or "scraping fallo")
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
    # Guarda con columna extra is_synthetic
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
# DATABASE INVENTORY
# ---------------------------------------------------------------------------
def list_available_databases() -> List[Dict[str, Any]]:
    ensure_directories()
    dbs = sorted(DATABASE_DIR.glob("youtube_charts_*.db"))
    if not dbs:
        log.info("No hay bases disponibles aun")
        return []
    log.info("Bases disponibles (%d):", len(dbs))
    total = 0
    out: List[Dict[str, Any]] = []
    for db in dbs:
        try:
            conn = sqlite3.connect(db)
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM chart_data")
                count = cur.fetchone()[0]
                try:
                    cur.execute("SELECT COUNT(*) FROM chart_data WHERE is_synthetic = 1")
                    synth = cur.fetchone()[0]
                except sqlite3.OperationalError:
                    synth = 0
                cur.execute("SELECT MIN(download_date), MAX(download_date) FROM chart_data")
                min_d, max_d = cur.fetchone()
            finally:
                conn.close()
            size_kb = db.stat().st_size / 1024
            week_id = db.stem.replace("youtube_charts_", "")
            total += count
            log.info("  %s: %d registros (%d sinteticos), %.1f KB %s a %s", week_id, count, synth, size_kb, min_d, max_d)
            out.append({"week_id": week_id, "count": count, "synthetic": synth, "size_kb": size_kb})
        except Exception as e:
            log.warning("Error leyendo %s: %s", db.name, e)
    log.info("TOTAL: %d registros en %d bases", total, len(dbs))
    return out


# ---------------------------------------------------------------------------
# EXTRACCION DESDE JSON (youtubei / ytInitialData)
# ---------------------------------------------------------------------------
def _text_from_yt_node(node: Any) -> str:
    """Extrae texto de nodos de YouTube (simpleText / runs)."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if "simpleText" in node:
            return str(node["simpleText"])
        if "runs" in node and isinstance(node["runs"], list):
            return "".join(str(r.get("text", "")) for r in node["runs"] if isinstance(r, dict))
        if "text" in node and isinstance(node["text"], str):
            return node["text"]
    return ""


def _extract_rows_from_yt_json(obj: Any, _seen: Optional[set] = None) -> List[Dict[str, Any]]:
    """
    Busca recursivamente objetos con videoId + titulo en cualquier JSON
    de YouTube. Funciona aunque cambie la forma exacta del payload.
    """
    if _seen is None:
        _seen = set()
    rows: List[Dict[str, Any]] = []

    def walk(o: Any):
        if isinstance(o, dict):
            vid = o.get("videoId") or o.get("video_id")
            if isinstance(vid, str) and len(vid) == 11 and vid not in _seen:
                title = ""
                artist = ""
                views_raw = ""
                # title puede estar en varias claves
                for k in ("title", "headline"):
                    if k in o:
                        t = _text_from_yt_node(o[k])
                        if t:
                            title = t
                            break
                # artista / subtitulo
                for k in ("subtitle", "shortBylineText", "longBylineText", "bylineText"):
                    if k in o:
                        a = _text_from_yt_node(o[k])
                        if a:
                            artist = a
                            break
                # vistas
                for k in ("viewCountText", "views", "viewCount"):
                    if k in o:
                        v = _text_from_yt_node(o[k])
                        if v:
                            views_raw = v
                            break
                if title:
                    _seen.add(vid)
                    rows.append(
                        {
                            "Rank": len(rows) + 1,
                            "Track Name": title,
                            "Artist Names": artist,
                            "Views": views_raw,
                            "Views Raw": views_raw,
                            "YouTube URL": f"https://www.youtube.com/watch?v={vid}",
                            "videoId": vid,
                        }
                    )
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return rows


def _parse_next_data(html: str) -> List[Dict[str, Any]]:
    """Busca __NEXT_DATA__ (Next.js) en HTML. Charts 2026 usa este formato."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, flags=re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        rows = _extract_rows_from_yt_json(data)
        if len(rows) >= 10:
            return rows
        # Si no hay videoId, busca estructuras genericas de chart: props.pageProps
        # Recorre todo el JSON buscando dicts con title + views / artist
        rows2 = _extract_rows_from_generic_json(data)
        return rows2
    except Exception as e:
        log.info("Parse __NEXT_DATA__ fallo: %s", e)
        return []


def _extract_rows_from_generic_json(obj: Any) -> List[Dict[str, Any]]:
    """Busca filas de chart aunque no tengan videoId: dicts con titulo + artista/vistas."""
    rows: List[Dict[str, Any]] = []
    seen = set()
    def walk(o: Any):
        if isinstance(o, dict):
            # Un chart row tipico tiene: title/name + artist + views / rank
            title = o.get("title") or o.get("name") or o.get("track") or o.get("songTitle")
            artist = o.get("artist") or o.get("artistName") or o.get("artists") or o.get("artistNames")
            views = o.get("views") or o.get("weeklyViews") or o.get("viewCount") or o.get("viewsCount")
            rank = o.get("rank") or o.get("position") or o.get("chartPosition")
            if isinstance(title, str) and title and isinstance(artist, (str, list)):
                if isinstance(artist, list):
                    artist = ", ".join(str(a.get("name", a) if isinstance(a, dict) else a) for a in artist)
                key = (title, str(artist))
                if key not in seen:
                    seen.add(key)
                    rows.append({"Rank": rank or len(rows)+1, "Track Name": title, "Artist Names": str(artist), "Views": str(views) if views is not None else "", "Views Raw": str(views) if views is not None else "", "YouTube URL": o.get("url") or o.get("youtubeUrl") or ""})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    return rows


def _parse_yt_initial_data(html: str) -> List[Dict[str, Any]]:
    """Busca ytInitialData en HTML y lo parsea."""
    patterns = [
        r"var\s+ytInitialData\s*=\s*(\{.+?\});\s*</script>",
        r"ytInitialData\s*=\s*(\{.+?\});",
        r"window\[\"ytInitialData\"\]\s*=\s*(\{.+?\});",
    ]
    for pat in patterns:
        m = re.search(pat, html, flags=re.DOTALL)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
            rows = _extract_rows_from_yt_json(data)
            if len(rows) >= 10:
                return rows
        except Exception:
            continue
    return []


# ---------------------------------------------------------------------------
# HTTP DIRECTO (sin navegador) - intento rapido
# ---------------------------------------------------------------------------
def download_via_http(chart: str = "TopSongs", country: str = "global") -> Optional[Path]:
    """Intenta bajar el HTML y extraer ytInitialData sin Playwright."""
    for url in get_chart_urls(chart, country):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            rows = _parse_yt_initial_data(html)
            if len(rows) < 20:
                rows_next = _parse_next_data(html)
                if len(rows_next) > len(rows):
                    rows = rows_next
                    log.info('HTTP: encontrado via __NEXT_DATA__: %d filas', len(rows))
            if len(rows) >= 20:
                out = ARCHIVE_DIR / "latest_chart.csv"
                ensure_directories()
                return save_rows_to_csv(rows, out)
            log.info("HTTP directo no encontro suficientes filas en %s (%d)", url, len(rows))
        except Exception as e:
            log.info("HTTP directo fallo en %s: %s", url, e)
    return None


# ---------------------------------------------------------------------------
# PLAYWRIGHT - ESTRATEGIA PRINCIPAL: DOM + RED + BOTON (en ese orden)
# ---------------------------------------------------------------------------
_JS_EXTRACT_DOM = r'''
() => {
  const rows = [];
  const seen = new Set();
  function getText(el) { return (el.innerText || el.textContent || '').trim(); }
  function collectAll(root, out) {
    if (!root || !root.querySelectorAll) return;
    const all = root.querySelectorAll('*');
    all.forEach(el => {
      out.push(el);
      if (el.shadowRoot) collectAll(el.shadowRoot, out);
    });
  }
  const allEls = [];
  collectAll(document, allEls);
  const tableRows = document.querySelectorAll('table tbody tr');
  if (tableRows.length >= 20) {
    tableRows.forEach((tr, idx) => {
      const cells = Array.from(tr.querySelectorAll('td, th')).map(c => c.innerText.trim()).filter(Boolean);
      const link = tr.querySelector('a[href]');
      const href = link ? link.getAttribute('href') : '';
      if (cells.length >= 2) {
        rows.push({Rank: idx+1, 'Track Name': cells[1] || '', 'Artist Names': cells[2] || '', 'Views': cells[3] || '', 'YouTube URL': href || ''});
      }
    });
    if (rows.length >= 20) return rows;
  }
  const rowCands = allEls.filter(el => {
    const tag = (el.tagName || '').toLowerCase();
    const cls = (el.className || '').toString().toLowerCase();
    return tag.includes('chart-row') || tag.includes('chart-item') || cls.includes('chart-row') || cls.includes('chart-item') || (cls.includes('row') && cls.includes('chart'));
  });
  for (const rowEl of rowCands) {
    const txt = getText(rowEl);
    if (!txt || txt.length < 10 || txt.length > 500) continue;
    const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
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
    const nonRank = lines.filter(l => !/^\d+$/.test(l));
    if (nonRank.length >= 1) title = nonRank[0];
    if (nonRank.length >= 2) artist = nonRank[1];
    for (const l of lines) { if (/[\d,.]+\s*[KMB]?\s*(views|reproducciones|vistas)/i.test(l) || /^[\d,.]+[KMB]?$/.test(l)) viewsRaw = l; }
    if (title && artist && !seen.has(rank + '|' + title)) {
      seen.add(rank + '|' + title);
      rows.push({Rank: rank, 'Track Name': title, 'Artist Names': artist, 'Views': viewsRaw, 'Views Raw': viewsRaw, 'YouTube URL': vid ? 'https://www.youtube.com/watch?v=' + vid : href, videoId: vid});
    }
  }
  if (rows.length >= 20) {
    rows.sort((a,b) => a.Rank - b.Rank);
    return rows;
  }
  for (const el of allEls) {
    if (el.tagName !== 'A') continue;
    const href = el.getAttribute('href') || '';
    if (!href) continue;
    let m = href.match(/v=([A-Za-z0-9_-]{11})/) || href.match(/youtu\.be\/([A-Za-z0-9_-]{11})/) || href.match(/\/watch\/([A-Za-z0-9_-]{11})/);
    let vid = m ? m[1] : '';
    let container = el.closest ? el.closest('tr, li, [role="row"], [class*="row"], [class*="item"], [class*="chart"]') : null;
    let text = container ? container.innerText : getText(el);
    let lines = (text || '').split('\n').map(s => s.trim()).filter(Boolean);
    if (vid) { if (seen.has(vid)) continue; seen.add(vid); }
    else {
      if (lines.length < 3) continue;
      const key = (getText(el) + '|' + lines.join('|')).slice(0,200);
      if (seen.has(key)) continue;
      if (!/[0-9]/.test(text)) continue;
      seen.add(key);
    }
    let title = (el.getAttribute('aria-label') || getText(el) || '').trim().split('\n')[0] || (lines[1] || lines[0] || '');
    title = title.replace(/^\d+\.\s*/, '').replace(/^\d+\s+/, '');
    let artist = '', viewsRaw = '';
    for (const l of lines) { if (/[\d,.]+\s*[KMB]?\s*(views|reproducciones|vistas)/i.test(l)) viewsRaw = l; }
    for (const l of lines) { if (l !== title && l !== viewsRaw && !/^\d+$/.test(l) && l.length > 1 && l.length < 90) { artist = l; break; } }
    rows.push({Rank: rows.length+1, 'Track Name': title, 'Artist Names': artist, 'Views': viewsRaw, 'Views Raw': viewsRaw, 'YouTube URL': vid ? 'https://www.youtube.com/watch?v=' + vid : href, videoId: vid});
  }
  return rows;
}
'''



async def _extract_via_dom(page) -> List[Dict[str, Any]]:
    try:
        # Diagnostico extra: cuantos links hay en total
        try:
            _diag = await page.evaluate("() => { let links=0; function walk(r){ if(!r||!r.querySelectorAll) return; links+=r.querySelectorAll('a').length; const els=r.querySelectorAll('*'); for(const el of els){ if(el.shadowRoot) walk(el.shadowRoot); } } walk(document); return {links: links, bodyLen: document.body ? document.body.innerText.length : 0, title: document.title }; }")
            log.info("Diagnostico DOM: links_shadow=%s bodyLen_light=%s title=%s", _diag.get('links'), _diag.get('bodyLen'), _diag.get('title'))
        except Exception:
            pass
        data = await page.evaluate(_JS_EXTRACT_DOM)
        if not isinstance(data, list):
            return []
        # Filtra filas sin titulo
        out = [r for r in data if _clean_text(r.get("Track Name"))]
        # Deduplica por URL
        seen = set()
        dedup = []
        for r in out:
            u = r.get("YouTube URL", "")
            if u and u in seen:
                continue
            seen.add(u)
            dedup.append(r)
        return dedup
    except Exception as e:
        log.info("Extraccion DOM fallo: %s", e)
        return []


async def _try_download_button(page, filename: Path) -> Optional[Path]:
    """
    Ultimo recurso: boton de descarga con selectores MODERNOS.
    Ya no usa #download-button ni paper-icon-button como unicos intentos.
    """
    # Candidatos por rol ARIA (funciona aunque cambie el tag)
    candidates = []
    try:
        # Por rol + nombre accesible
        for pattern in [r"download", r"descargar", r"export", r"csv"]:
            try:
                loc = page.get_by_role("button", name=re.compile(pattern, re.I))
                if await loc.count() > 0:
                    candidates.append(loc.first)
            except Exception:
                pass
        # Por atributo
        for sel in [
            'button[aria-label*="download" i]',
            'a[aria-label*="download" i]',
            '[aria-label*="Download" i]',
            'button[title*="download" i]',
            'a[download]',
        ]:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    candidates.append(loc.first)
            except Exception:
                pass
    except Exception:
        pass

    for btn in candidates:
        try:
            if not await btn.is_visible():
                try:
                    await btn.scroll_into_view_if_needed(timeout=3000)
                except Exception:
                    pass
            async with page.expect_download(timeout=20_000) as dl_info:
                await btn.click(timeout=5000)
            download = await dl_info.value
            await download.save_as(filename)
            if filename.exists() and filename.stat().st_size > 1000:
                log.info("Descarga por boton OK: %s", filename)
                return filename
        except Exception as e:
            log.info("Boton candidato fallo: %s", str(e)[:200])
            continue
    return None



def _extract_rows_from_youtubei_json(data: Any) -> List[Dict[str, Any]]:
    """Parsea respuesta de youtubei/v1/browse para Charts. Busca musicResponsiveListItemRenderer."""
    rows: List[Dict[str, Any]] = []
    def get_text(obj: Any) -> str:
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            if "simpleText" in obj:
                return str(obj.get("simpleText") or "")
            if "runs" in obj and isinstance(obj.get("runs"), list):
                return "".join(str(r.get("text", "")) for r in obj["runs"] if isinstance(r, dict))
        return ""
    def walk(o: Any):
        if isinstance(o, dict):
            if "musicResponsiveListItemRenderer" in o:
                r = o["musicResponsiveListItemRenderer"]
                flex = r.get("flexColumns", []) or []
                # flexColumns[0]=rank+title? En Charts: 0=rank, 1=title+artist, 2=views etc. Varia, por eso recorremos todo
                texts = []
                for col in flex:
                    for cell in (col.get("musicResponsiveListItemFlexColumnRenderer") or {}).get("text", {}).get("runs", []) or []:
                        if isinstance(cell, dict) and cell.get("text"):
                            texts.append(str(cell["text"]))
                # Tambien buscar navigationEndpoint con videoId
                vid = ""
                try:
                    nav = r.get("navigationEndpoint", {}) or {}
                    wid = nav.get("watchEndpoint", {}) or {}
                    vid = wid.get("videoId", "") or ""
                except Exception:
                    pass
                # Si no hay vid, busca en flexColumns
                if not vid:
                    s = json.dumps(r)
                    m = re.search(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', s)
                    if m:
                        vid = m.group(1)
                if texts:
                    # Heuristica: primer texto numerico = rank, segundo = titulo, tercero = artista, ultimo con numero = views
                    # Guardamos todo y luego el caller normaliza
                    title = texts[1] if len(texts) > 1 else texts[0]
                    artist = texts[2] if len(texts) > 2 else ""
                    views = texts[-1] if len(texts) > 3 else ""
                    # Si texts tiene solo 2, puede ser titulo + artista
                    if len(texts) == 2:
                        title, artist = texts[0], texts[1]
                    rows.append({
                        "Rank": len(rows)+1,
                        "Track Name": title.strip(),
                        "Artist Names": artist.strip(),
                        "Views": views.strip(),
                        "Views Raw": views.strip(),
                        "YouTube URL": f"https://www.youtube.com/watch?v={vid}" if vid else "",
                        "videoId": vid,
                    })
                return
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    return rows


async def _try_youtubei_browse(page, chart: str = "TopSongs", country: str = "global") -> List[Dict[str, Any]]:
    log.info("youtubei: omitido - Charts no usa youtubei/v1/browse (404 esperado), se usa DOM/shadow")
    return []



async def _extract_via_inner_text(page) -> List[Dict[str, Any]]:
    """Fallback: parsea body.innerText como tabla. No inventa, solo si hay estructura rank+titulo+artista+vistas."""
    try:
        text = await _get_page_text_with_shadow(page)
    except Exception as e:
        log.info("innerText: fallo %s", e)
        return []
    if not text or len(text) < 1000:
        log.info("innerText: muy corto len=%d", len(text) if text else 0)
        return []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # Busca bloques: linea con numero 1..100, luego titulo, luego artista, luego vistas con numero
    rows: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        # Rank solo numero
        if re.fullmatch(r"(\\d{1,3})", lines[i] or "") and i+3 < len(lines):
            rank = int(lines[i])
            if 1 <= rank <= 100:
                # Siguientes 3 lineas: titulo, artista, vistas (o titulo+artista en una)
                title = lines[i+1]
                artist = lines[i+2]
                views = lines[i+3] if i+3 < len(lines) else ""
                # Views debe tener numero
                if re.search(r"[\\d,.]+", views) and len(title) > 1 and len(title) < 120 and len(artist) < 120:
                    # Evita agarrar headers: titulo no debe ser "Last week" etc
                    if title.lower() not in ("last week", "weeks on chart", "weekly views", "title", "artist"):
                        rows.append({"Rank": rank, "Track Name": title, "Artist Names": artist, "Views": views, "Views Raw": views, "YouTube URL": ""})
                        i += 4
                        continue
        i += 1
    log.info("innerText: filas parseadas=%d de %d lineas", len(rows), len(lines))
    return rows


async def _save_auto_debug(page, url: str, tag: str = "fail"):
    """Guarda captura + HTML + texto automaticamente cuando falla, sin que tengas que correr otro script."""
    try:
        dbg_dir = BASE_DIR / "logs" / "debug"
        dbg_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            await page.screenshot(path=str(dbg_dir / f"debug_{tag}_{ts}.png"), full_page=False, timeout=15000)
            log.info("Auto-debug: screenshot en logs/debug/debug_%s_%s.png", tag, ts)
        except Exception as e:
            log.info("Auto-debug screenshot fallo: %s", e)
        try:
            html = await page.content()
            (dbg_dir / f"debug_{tag}_{ts}.html").write_text(html, encoding="utf-8")
            log.info("Auto-debug: HTML %d bytes en logs/debug/debug_%s_%s.html", len(html), tag, ts)
        except Exception as e:
            log.info("Auto-debug HTML fallo: %s", e)
        try:
            txt = await page.evaluate("() => document.body ? document.body.innerText : ''")
            (dbg_dir / f"debug_{tag}_{ts}.txt").write_text(f"URL: {url}\\nTitle: {await page.evaluate('() => document.title')}\\nFinal URL: {page.url}\\nBody len: {len(txt)}\\n\\n--- BODY ---\\n{txt[:8000]}", encoding="utf-8")
            log.info("Auto-debug: texto %d chars en logs/debug/debug_%s_%s.txt", len(txt), tag, ts)
            # Tambien loguea en terminal los primeros 800 chars para que lo veas sin abrir archivo
            log.info("Auto-debug body snippet[:800]: %s", txt[:800].replace("\\n", " | "))
        except Exception as e:
            log.info("Auto-debug texto fallo: %s", e)
    except Exception as e:
        log.info("Auto-debug fallo: %s", e)




async def _get_page_text_with_shadow(page) -> str:
    """Charts es Polymer: el texto NO esta en body.innerText, esta en Shadow DOM.
    body.innerText da 0 aunque el chart este visible. Por eso el detector viejo
    decia captcha y body_len=0 aunque la pagina tenia 1.3MB de HTML.
    Esta funcion recorre todos los shadowRoot y junta el texto real.
    """
    try:
        txt = await page.evaluate("""() => {
            let out = [];
            function isIgnorable(node) {
                if (!node || !node.parentElement) return false;
                const tag = (node.parentElement.tagName || '').toUpperCase();
                return tag === 'STYLE' || tag === 'SCRIPT' || tag === 'NOSCRIPT' || tag === 'TEMPLATE' || tag === 'HEAD';
            }
            function walk(root) {
                if (!root) return;
                // Texto directo de este root
                try {
                    const iter = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
                    let n;
                    while (n = iter.nextNode()) {
                        if (isIgnorable(n)) continue;
                        const v = (n.nodeValue || '').trim();
                        if (v) out.push(v);
                    }
                } catch(e) {}
                // Recorrer elementos y sus shadowRoot
                const els = root.querySelectorAll ? root.querySelectorAll('*') : [];
                for (const el of els) {
                    if (el.shadowRoot) walk(el.shadowRoot);
                }
                // Tambien shadowRoot del documentElement
                if (root === document && document.documentElement && document.documentElement.shadowRoot) {
                    walk(document.documentElement.shadowRoot);
                }
            }
            walk(document);
            // Tambien body.innerText como fallback
            if (document.body && document.body.innerText) out.push(document.body.innerText);
            return out.join('\\n');
        }""")
        return txt or ""
    except Exception as e:
        log.info("Shadow text fallo: %s", e)
        return ""

async def _detect_captcha(page) -> bool:
    """Detecta captcha REAL y VISIBLE. Corrige falso positivo de Polymer.
    Antes: si body.innerText era 0, decia captcha. Pero Charts es Polymer:
    body.innerText es 0 SIEMPRE, aunque el chart este visible en Shadow DOM.
    Ahora: usa _get_page_text_with_shadow. Si ese texto tiene
    'Weekly Top Songs' + 'Weekly views', NO es captcha.
    """
    try:
        shadow_txt = await _get_page_text_with_shadow(page)
        low = (shadow_txt or "").lower()
        has_chart = ("weekly top songs" in low or "weekly top artists" in low) and ("weekly views" in low or "rank" in low)
        if has_chart:
            return False
        # Si hay texto de chart, no es captcha aunque haya iframe recaptcha oculto
        if len(shadow_txt) > 2000 and ("weekly top songs" in low or "top songs" in low):
            return False
        # Solo si NO hay chart y hay texto de desafio visible
        if "select all images" in low and "click verify" in low:
            return True
        # Iframe recaptcha visible y grande (no el de 1px del fondo) + sin chart
        has_visible = await page.evaluate("""() => {
            const cands = document.querySelectorAll('[class*="recaptcha"], iframe[src*="recaptcha"]');
            for (const el of cands) {
                const r = el.getBoundingClientRect ? el.getBoundingClientRect() : {width:0,height:0};
                if (r.width >= 300 && r.height >= 100) return true;
            }
            return false;
        }""")
        if has_visible and not has_chart:
            return True
        # Si shadow text es 0 Y body es 0 Y HTML es grande, NO asumir captcha: es Polymer sin cargar aun, esperar
        # Devolver False para que no se quede 180s esperando un captcha que no existe
        return False
    except Exception as e:
        log.info("Detect captcha fallo: %s", e)
        return False


async def _wait_for_captcha_resolution(page, url: str, show_browser: bool, max_wait: int = 180, terminal_mode: bool = False) -> bool:
    """Si hay captcha, espera a que desaparezca. Si hay navegador visible, deja que lo resuelvas tu."""
    try:
        has = await _detect_captcha(page)
    except Exception:
        has = False
    if not has:
        return True
    # Doble chequeo: si el chart ya esta visible, no es captcha aunque el detector haya dicho que si
    try:
        _chart_ok = await page.evaluate("() => { const bt = document.body ? document.body.innerText : ''; return bt.includes('Weekly Top Songs') && bt.includes('Weekly views'); }")
        if _chart_ok:
            log.info('Captcha detectado pero chart YA visible (Weekly Top Songs + Weekly views). Era falso positivo, sigo sin esperar.')
            return True
    except Exception:
        pass
    log.warning("CAPTCHA DETECTADO en %s", url)
    if show_browser:
        if terminal_mode:
            log.warning("Captcha en --terminal / GitHub: no hay humano para resolverlo, se esperara solo %d s y se seguira con DOM/shadow.", max_wait)
        else:
            log.warning("Resuelve el CAPTCHA a mano en la ventana de Chrome que esta abierta.")
        log.warning("Tienes %d segundos. El scraper esperara a que el chart aparezca, no necesitas presionar nada en la terminal.", max_wait)
        log.warning("Tip: si lo resuelves una vez con tu perfil persistente (.browser-profile), Google confia en ese perfil y la proxima vez casi no sale.")
    else:
        log.warning("Estas en headless, no puedes resolver el captcha asi. Corre sin --headless (modo ventana) para resolverlo a mano.")
        log.warning("Ejemplo: python3 \"Youtube Charts Scraper Local.py\" --pause --use-chrome  (sin --headless, en ventana)")
        # Igual esperamos un poco por si el captcha 'dura unos segundos' y se va solo
        log.warning("Esperando %d s por si el captcha se va solo...", min(max_wait, 30))
    import asyncio as _asyncio
    for i in range(0, max_wait, 3):
        await _asyncio.sleep(3)
        still = await _detect_captcha(page)
        if not still:
            log.info("Captcha ya no esta (despues de %d s). Sigo con extraccion.", i+3)
            # Espera extra a que cargue el chart
            await _asyncio.sleep(3)
            return True
        # Cada 30s loguear progreso
        if (i+3) % 30 == 0:
            log.warning("Captcha sigue ahi despues de %d s... sigue esperando (max %d s)", i+3, max_wait)
    log.error("Captcha siguio despues de %d s. No se pudo extraer. Vuelve a correr sin --headless (en ventana) y resuelvelo a mano.", max_wait)
    return False


async def download_youtube_charts(chart: str = "TopSongs", country: str = "global", show_browser: bool = False, use_chrome: bool = False, keep_profile: bool = True, terminal_mode: bool = False) -> Optional[Path]:
    """
    Descarga con Playwright. Orden: DOM -> JSON de red -> boton.
    Version LOCAL: puede usar tu Chrome, perfil persistente y navegador visible.
    Cierra el navegador SIEMPRE con finally.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.error("Playwright no instalado")
        return None

    log.info("Descargando YouTube Charts %s / %s con Playwright...", chart, country)
    ensure_directories()
    filename = ARCHIVE_DIR / "latest_chart.csv"

    async with async_playwright() as p:
        browser = None
        context = None
        try:
            # CORRECCION 2026-11-18: --terminal NO significa headless. --terminal = no interactivo (sin input).
            # En CI con xvfb-run -a hay DISPLAY, entonces --terminal debe correr HEADED (headless=False) para que Google no muestre captcha.
            headless = not show_browser
            if terminal_mode and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                if headless:
                    log.info("Modo TERMINAL + DISPLAY=%s detectado (xvfb): forzando HEADED (headless=False) aunque show_browser=False. --terminal no es headless.", os.environ.get("DISPLAY"))
                    headless = False
                    show_browser = True
                else:
                    log.info("Modo TERMINAL + DISPLAY=%s (xvfb): HEADED, no headless. Asi Google no muestra captcha.", os.environ.get("DISPLAY"))
            elif terminal_mode and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                log.warning("Modo TERMINAL sin DISPLAY (sin xvfb): se usara headless=True, captcha muy probable. En CI usa xvfb-run -a.")
            # En Linux sin entorno grafico (servidor sin X / Wayland) no se puede mostrar navegador
            if show_browser and IS_LINUX and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                log.warning("Pediste --show-browser pero no hay DISPLAY ni WAYLAND_DISPLAY (Linux sin GUI). Se usara headless=True.")
                log.warning("Si tienes escritorio, corre desde la terminal grafica, no por SSH sin -X. O usa xvfb-run.")
                headless = True
                show_browser = False
            browser_args = get_browser_args()
            # En headless, usar headless=new (menos detectable que headless viejo)
            # En GitHub, mejor aun es correr con xvfb-run -a para que Chrome crea que hay ventana
            if headless and "--headless=new" not in browser_args:
                browser_args.append("--headless=new")
                log.info("Headless: usando --headless=new (menos detectable). En GitHub usa xvfb-run -a para que se vea como ventana.")
            if show_browser:
                log.info("Modo --show-browser: veras el navegador. Si aparece captcha, resuelvelo, el script esperara unos segundos.")
            if IS_GITHUB_ACTIONS:
                log.warning("Detectado GITHUB_ACTIONS=true. Esta version es para PC local, en CI usa la version CI.")
            if keep_profile and IS_LOCAL:
                log.info("Usando perfil persistente local: %s", BROWSER_PROFILE_DIR)
                BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
                persistent_kwargs: Dict[str, Any] = dict(
                    headless=headless,
                    args=browser_args,
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                        if (IS_LINUX or IS_GITHUB_ACTIONS) else
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    timezone_id=LOCAL_TIMEZONE,
                    accept_downloads=True,
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Referer": "https://charts.youtube.com/",
                    },
                )
                if use_chrome:
                    persistent_kwargs["channel"] = "chrome"
                    log.info("Usando tu Chrome instalado (channel=chrome) en vez de Chromium descargado")
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=str(BROWSER_PROFILE_DIR),
                    **persistent_kwargs,
                )
            else:
                launch_kwargs: Dict[str, Any] = dict(headless=headless, args=browser_args)
                if use_chrome:
                    launch_kwargs["channel"] = "chrome"
                    log.info("Usando tu Chrome instalado (channel=chrome)")
                browser = await p.chromium.launch(**launch_kwargs)
                context = await browser.new_context(
                    accept_downloads=True,
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                        if (IS_LINUX or IS_GITHUB_ACTIONS) else
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    timezone_id=LOCAL_TIMEZONE,
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Referer": "https://charts.youtube.com/",
                    },
                )
            try:
                _cookies_raw = os.environ.get("YOUTUBE_COOKIES", "").strip()
                if _cookies_raw:
                    log.info("YOUTUBE_COOKIES presente (%d chars), intentando inyectar cookies", len(_cookies_raw))
                    try:
                        import json as _js
                        _parsed = _js.loads(_cookies_raw)
                        if isinstance(_parsed, list) and _parsed:
                            await context.add_cookies(_parsed)
                            log.info("Cookies JSON inyectadas: %d", len(_parsed))
                        elif isinstance(_parsed, dict) and _parsed:
                            _clist = [{"name": k, "value": str(v), "domain": ".youtube.com", "path": "/"} for k, v in _parsed.items()]
                            await context.add_cookies(_clist)
                            log.info("Cookies dict inyectadas: %d", len(_clist))
                        else:
                            raise ValueError("formato JSON no reconocido")
                    except Exception as _e:
                        try:
                            _pairs = [p.strip() for p in _cookies_raw.split(";") if "=" in p]
                            _clist2 = []
                            for _pr in _pairs:
                                _k, _v = _pr.split("=", 1)
                                _clist2.append({"name": _k.strip(), "value": _v.strip(), "domain": ".youtube.com", "path": "/"})
                            if _clist2:
                                await context.add_cookies(_clist2)
                                log.info("Cookies string cruda inyectadas: %d", len(_clist2))
                        except Exception as _e2:
                            log.warning("YOUTUBE_COOKIES no se pudo parsear, se sigue sin cookies: %s / %s", _e, _e2)
                else:
                    log.info("YOUTUBE_COOKIES vacio o no configurado: se sigue sin cookies (en CI sin cookies el captcha es mas probable)")
            except Exception as _e:
                log.warning("Inyeccion de cookies fallo (ignorado): %s", _e)
            await context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
                """
            )
            # En modo persistente ya puede haber una pagina abierta
            if keep_profile and IS_LOCAL and context.pages:
                page = context.pages[0]
            else:
                page = await context.new_page()
            # set_default_timeout es sincrono en Playwright Python
            try:
                page.set_default_timeout(60_000)
            except Exception:
                pass

            captured_json: List[Any] = []

            captured_urls: List[str] = []
            async def _on_response(resp):
                try:
                    ct = (resp.headers.get("content-type") or "").lower()
                    url = resp.url or ""
                    captured_urls.append(f"{resp.status} {url} ct={ct}")
                    # Antes solo guardaba si url tenia youtubei/charts/browse y ct json.
                    # Ahora guarda TODO lo que parezca JSON o texto, para no perder el API nuevo.
                    if "json" in ct or "text" in ct or "javascript" in ct:
                        try:
                            # Intentar json, si falla intentar texto y buscar chart
                            try:
                                data = await resp.json()
                                captured_json.append(data)
                            except Exception:
                                try:
                                    txt = await resp.text()
                                    if len(txt) > 200 and ("TopSongs" in txt or "Weekly views" in txt or "chart" in txt.lower()[:2000]):
                                        # Guarda texto crudo para parsear despues si hace falta
                                        captured_json.append({"_raw_text": txt[:20000], "_url": url})
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception:
                    pass

            page.on("response", _on_response)

            for url in get_chart_urls(chart, country):
                log.info("Navegando a %s", url)
                try:
                    try:
                        await page.goto(url, wait_until="networkidle", timeout=90_000)
                    except Exception as e:
                        log.info("goto networkidle fallo, reintento domcontentloaded: %s", e)
                        try:
                            await page.goto(url, wait_until="domcontentloaded", timeout=90_000)
                        except Exception as e2:
                            log.info("goto domcontentloaded fallo, sigo: %s", e2)
                    await page.wait_for_timeout(8000)
                    try:
                        await page.wait_for_selector("ytmc-v2-app", state="attached", timeout=30_000)
                        log.info("Polymer ytmc-v2-app adjunto, esperando chart...")
                    except Exception as e:
                        log.info("ytmc-v2-app no aparecio en 30s: %s", e)
                    for _poll in range(15):
                        try:
                            _poll_txt = await _get_page_text_with_shadow(page)
                            if "Weekly Top Songs" in _poll_txt and "Weekly views" in _poll_txt:
                                log.info("Poll chart: chart visible en shadow tras %ds", (_poll+1)*3)
                                break
                            if "Select all images" in _poll_txt or "I'm not a robot" in _poll_txt:
                                log.info("Poll chart: aparece captcha visible")
                                break
                        except Exception:
                            pass
                        await page.wait_for_timeout(3000)
                    # CAPTCHA: si Google lo muestra, hay que resolverlo a mano, si no todo dara 0
                    try:
                        await _wait_for_captcha_resolution(page, url, show_browser, max_wait=(20 if terminal_mode else 180), terminal_mode=terminal_mode)
                    except Exception as e:
                        log.info("Espera captcha fallo: %s", e)
                    # Ya se hizo poll con shadow text arriba (get_by_text NO ve shadow DOM en Polymer)
                    try:
                        _chk = await _get_page_text_with_shadow(page)
                        log.info("Check shadow post-poll: len=%d tiene_chart=%s", len(_chk), ("Weekly Top Songs" in _chk))
                    except Exception:
                        pass
                    # Log diagnostico: cuanto texto hay realmente
                    try:
                        _shadow_txt = await _get_page_text_with_shadow(page)
                        _body_len = len(_shadow_txt)
                        log.info('Diagnostico shadow: shadow_text_len=%d snippet=%s', _body_len, _shadow_txt[:500].replace(chr(10), ' | '))
                        _title = await page.evaluate("() => document.title")
                        _final_url = page.url
                        log.info("Diagnostico pagina: title=%s url_final=%s body_text_len=%d", _title, _final_url, _body_len)
                        if _body_len < 500:
                            log.warning("Body text muy corto (%d). Pagina puede venir vacia, bloqueada o con captcha. Corre con --show-browser --use-chrome para verla y resolver el captcha.", _body_len)
                    except Exception as e:
                        log.info("Diagnostico body fallo: %s", e)

                    # --- Muro de consentimiento / cookies (nuevo) ---
                    for label in [r"Accept all", r"Reject all", r"Aceptar todo", r"Rechazar todo", r"Accept", r"Aceptar"]:
                        try:
                            btn = page.get_by_role("button", name=re.compile(label, re.I))
                            if await btn.count() > 0:
                                await btn.first.click(timeout=3000)
                                log.info("Click en consentimiento: %s", label)
                                await page.wait_for_timeout(1500)
                                break
                        except Exception:
                            continue

                    # --- Scroll para cargar contenido dinamico ---
                    for _ in range(5):
                        try:
                            await page.evaluate("window.scrollBy(0, 900)")
                        except Exception:
                            pass
                        await page.wait_for_timeout(1200)
                    try:
                        await page.evaluate("window.scrollTo(0,0)")
                    except Exception:
                        pass
                    await page.wait_for_timeout(1000)

                    # 0) youtubei API - intento principal nuevo, antes de DOM
                    try:
                        rows_youtubei = await _try_youtubei_browse(page, chart, country)
                        if len(rows_youtubei) >= 10:
                            log.info("Extraccion youtubei en %s: %d filas - USANDO ESTA", url, len(rows_youtubei))
                            rows = rows_youtubei
                            # Saltar resto de extraccion para esta URL
                            # Normalizar y devolver
                            rows_norm = _normalize_rows(rows)
                            if len(rows_norm) >= 10:
                                return rows_norm
                    except Exception as e:
                        log.info("youtubei fallo en %s: %s", url, e)
                    # 1) DOM
                    rows = await _extract_via_dom(page)
                    log.info("Extraccion DOM en %s: %d filas", url, len(rows))
                    # 1b) HTML __NEXT_DATA__ / ytInitialData (nuevo: Charts 2026 usa Next.js)
                    if len(rows) < 20:
                        try:
                            _html = await page.content()
                            _rows_next = _parse_next_data(_html)
                            log.info("Extraccion __NEXT_DATA__ en %s: %d filas", url, len(_rows_next))
                            if len(_rows_next) >= 20:
                                rows = _rows_next
                            else:
                                _rows_yt = _parse_yt_initial_data(_html)
                                log.info("Extraccion ytInitialData en %s: %d filas", url, len(_rows_yt))
                                if len(_rows_yt) > len(rows):
                                    rows = _rows_yt
                        except Exception as e:
                            log.info("Parse HTML en pagina fallo: %s", e)
                    # 1d) innerText fallback - si DOM y __NEXT_DATA__ dieron 0, probar texto
                    if len(rows) < 10:
                        try:
                            rows_text = await _extract_via_inner_text(page)
                            log.info("Extraccion innerText en %s: %d filas", url, len(rows_text))
                            if len(rows_text) > len(rows):
                                rows = rows_text
                        except Exception as e:
                            log.info("innerText fallo: %s", e)
                    # 1e) Si sigue 0, guardar auto-debug AHORA, no al final
                    if len(rows) < 10:
                        await _save_auto_debug(page, url, tag="zero_rows")
                    # 1c) Log de red para debug: que APIs llamo realmente la pagina
                    try:
                        log.info("Red capturada: %d respuestas, primeras 15:", len(captured_urls))
                        for _u in captured_urls[:15]:
                            log.info("  net: %s", _u[:300])
                    except Exception:
                        pass
                    if len(rows) >= 20:
                        return save_rows_to_csv(rows, filename)

                    # 2) JSON de red
                    net_rows: List[Dict[str, Any]] = []
                    seen_vids: set = set()
                    for data in captured_json:
                        for r in _extract_rows_from_yt_json(data, seen_vids):
                            net_rows.append(r)
                    log.info("Extraccion por red: %d filas", len(net_rows))
                    if len(net_rows) >= 20:
                        return save_rows_to_csv(net_rows, filename)

                    # 3) Boton de descarga (ultimo recurso)
                    dl = await _try_download_button(page, filename)
                    if dl is not None:
                        # Valida que tenga al menos 20 lineas
                        try:
                            with open(dl, "r", encoding="utf-8", errors="ignore") as f:
                                lines = f.readlines()
                            if len(lines) >= 21:
                                log.info("CSV por boton: %d lineas", len(lines))
                                return dl
                            log.warning("CSV por boton incompleto: %d lineas", len(lines))
                        except Exception:
                            pass

                    log.warning("No se pudo extraer chart desde %s, probando siguiente URL...", url)
                except Exception as e:
                    log.warning("Error en %s: %s", url, e)
                    continue

            log.error("No se pudo descargar el chart desde ninguna URL")
            return None
        finally:
            try:
                if context is not None:
                    await context.close()
            except Exception:
                pass
            try:
                if browser is not None:
                    await browser.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# MAIN - numeracion corregida 0..5
# ---------------------------------------------------------------------------
def _main_inner(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="YouTube Charts scraper - version LOCAL PC")
    parser.add_argument("--country", default="global", help="Pais, ej. global, us, cl")
    parser.add_argument("--chart", default="TopSongs", help="Tipo de chart, ej. TopSongs, TopArtists")
    parser.add_argument("--week", default=None, help="Forzar week_id, ej. 2025-W05. Por defecto semana actual ISO.")
    parser.add_argument("--allow-fallback", action="store_true", help="Permite guardar datos SINTETICOS si falla el scraping. Sin esto, falla con codigo 2 y NO contamina la DB.")
    parser.add_argument("--no-browser", action="store_true", help="No usa Playwright, solo HTTP directo.")
    parser.add_argument("--show-browser", action="store_true", help="LOCAL: muestra el navegador para ver que pasa y resolver captcha a mano si aparece.")
    parser.add_argument("--headless", action="store_true", help="LOCAL: forzar modo sin ventana. NO recomendado: en headless Google muestra captcha, en ventana no.")
    parser.add_argument("--use-chrome", action="store_true", help="LOCAL: usa tu Google Chrome instalado en vez de Chromium descargado. Menos deteccion de bot.")
    parser.add_argument("--no-profile", action="store_true", help="LOCAL: no usa perfil persistente .browser-profile/, usa perfil temporal limpio.")
    parser.add_argument("--open-folder", action="store_true", help="LOCAL: al terminar abre la carpeta con el CSV y la DB en el explorador.")
    parser.add_argument("--force", action="store_true", help="Re-scrapear aunque la semana ya tenga datos.")
    parser.add_argument("--pause", action="store_true", help="LOCAL: al terminar espera Enter antes de cerrar. Ideal para doble clic, si no la ventana se cierra y no ves el resultado.")
    parser.add_argument("--terminal", action="store_true", help="CI / TERMINAL: no interactivo, nunca espera Enter, nunca espera captcha manual. NO significa headless: con xvfb-run -a corre HEADED.")
    args = parser.parse_args(argv)

    print("\n" + "=" * 70)
    print("YOUTUBE CHARTS - EXTRACTOR LOCAL PC (100 canciones)")
    print('Modo: PC LOCAL LINUX - terminal=' + str(args.terminal) + ' headless=' + str(args.headless) + ' DISPLAY=' + str(__import__('os').environ.get('DISPLAY', '(sin DISPLAY)')))
    print(f"Chart: {args.chart} / Pais: {args.country}")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    ensure_directories()
    setup_local_logging()
    if IS_GITHUB_ACTIONS:
        log.warning('Estas corriendo la version LOCAL en GitHub Actions. Esta version usa perfil persistente y Chrome local, en CI mejor usa la version CI.')
    else:
        log.info('Modo PC LOCAL Linux - Linux=%s, perfil persistente=%s, zona=%s, DISPLAY=%s', IS_LINUX, not args.no_profile, LOCAL_TIMEZONE, os.environ.get('DISPLAY', '(sin DISPLAY)'))

    week_id = args.week or get_week_identifier()
    # Idempotencia local: si la semana ya tiene >=50 reales, saltar (a menos que --force)
    if not getattr(args, "force", False):
        try:
            _db_check = DATABASE_DIR / f"youtube_charts_{week_id}.db"
            if _db_check.exists():
                import sqlite3 as _sq
                _conn = _sq.connect(_db_check)
                _cur = _conn.cursor()
                _cur.execute("SELECT COUNT(*) FROM chart_data WHERE week_id = ? AND is_synthetic = 0", (week_id,))
                _existing = _cur.fetchone()[0]
                _conn.close()
                if _existing >= 50:
                    log.info("Semana %s ya tiene %d registros reales. Saltando (usa --force para re-scrapear).", week_id, _existing)
                    return 0
        except Exception as e:
            log.info("Check idempotencia fallo (ignorado): %s", e)
    log.info("Semana actual: %s", week_id)

    # 0. Dependencias
    print("\n0. VERIFICANDO DEPENDENCIAS...")
    playwright_ready = False
    if not args.no_browser:
        playwright_ready = install_playwright()
        if not playwright_ready:
            log.warning("Playwright no listo, se intentara HTTP directo y luego fallback segun flags")
    else:
        log.info("Modo --no-browser: se omite Playwright")

    # 1. Descarga
    print("\n1. DESCARGANDO YOUTUBE CHARTS...")
    csv_path: Optional[Path] = None
    is_synthetic = False

    if playwright_ready:
        try:
            # CORRECCION 2026-11-18: --terminal NO es --headless.
            # --terminal = no interactivo (sin input, captcha max 20s).
            # --headless = forzar sin ventana (captcha casi seguro).
            # En CI: xvfb-run -a + --terminal => DISPLAY existe => HEADED, sin captcha.
            if args.headless:
                _effective_show_browser = False
                log.warning("Usando --headless explicito: en headless Google muestra captcha. Si falla, corre sin --headless.")
            elif args.terminal:
                _has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
                _effective_show_browser = _has_display
                if _has_display:
                    log.info("Modo TERMINAL + DISPLAY=%s (xvfb): HEADED. --terminal no es headless, asi no sale captcha.", os.environ.get("DISPLAY"))
                else:
                    log.warning("Modo TERMINAL sin DISPLAY (sin xvfb): headless forzado, captcha probable. En CI usa xvfb-run -a.")
            else:
                _effective_show_browser = True
                log.info("Modo ventana (headed) por defecto: en ventana no sale captcha, en headless si. Usa --headless solo si lo necesitas.")
            csv_path = asyncio.run(download_youtube_charts(chart=args.chart, country=args.country, show_browser=_effective_show_browser, use_chrome=args.use_chrome, keep_profile=not args.no_profile, terminal_mode=args.terminal))
        except Exception as e:
            log.error("Error en descarga Playwright: %s", e, exc_info=True)
            csv_path = None

    if csv_path is None or not Path(csv_path).exists():
        log.info("Intentando HTTP directo...")
        csv_path = download_via_http(chart=args.chart, country=args.country)

    # 2. Validacion / fallback
    print("\n2. VALIDANDO CSV...")
    if csv_path is None or not Path(csv_path).exists():
        log.warning("Descarga automatica fallo")
        if args.allow_fallback:
            log.warning("Usando datos SINTETICOS por --allow-fallback")
            csv_path = create_fallback_file(week_id, reason="descarga fallo")
            is_synthetic = True
        else:
            log.error("CRITICO: No se pudo obtener CSV. No se guardara nada falso en la DB.")
            log.error("Si es para pruebas, corre con --allow-fallback")
            return 2

    # Valida contenido
    try:
        with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        num_songs = len(lines) - 1 if len(lines) > 1 else 0
        log.info("Canciones en CSV: %d", num_songs)
        if lines:
            log.info("Headers: %s", lines[0].strip()[:200])
        if num_songs < 20:
            log.warning("CSV con pocas canciones (%d). Puede estar incompleto.", num_songs)
            if not is_synthetic and args.allow_fallback:
                log.warning("CSV incompleto, usando fallback sintetico")
                csv_path = create_fallback_file(week_id, reason=f"CSV incompleto con {num_songs} filas")
                is_synthetic = True
            elif not is_synthetic:
                log.error("CSV incompleto y --allow-fallback no activo. Abortando sin guardar.")
                return 2
    except Exception as e:
        log.error("Error leyendo CSV: %s", e)
        return 1

    # 3. SQLite
    print("\n3. GUARDANDO EN SQLITE...")
    db_path = update_sqlite_database(Path(csv_path), week_id, is_synthetic=is_synthetic)
    if not db_path:
        log.error("Error critico actualizando DB")
        return 1

    # 4. Limpieza
    print("\n4. LIMPIANDO ARCHIVOS VIEJOS...")
    cleanup_old_backups(7)
    cleanup_old_databases(52)

    # 5. Resumen
    print("\n5. RESUMEN FINAL:")
    list_available_databases()

    print("\n" + "=" * 70)
    if is_synthetic:
        print("ADVERTENCIA: SE GUARDARON DATOS SINTETICOS (is_synthetic=1)")
    else:
        print("PROCESO COMPLETADO - DATOS REALES")
    print("=" * 70)
    return 0



def main(argv: Optional[List[str]] = None) -> int:
    """Wrapper LOCAL: corre _main_inner y luego maneja --pause / --open-folder / doble clic."""
    code = _main_inner(argv)
    args_list = list(argv) if argv is not None else sys.argv[1:]
    # --open-folder solo si termino bien
    if "--open-folder" in args_list and code == 0:
        try:
            open_folder_local(ARCHIVE_DIR)
        except Exception:
            pass
    # --pause o doble clic en Windows (sin tty) -> no cerrar la ventana de golpe
    # En Linux tambien: si lo abres con doble clic desde el gestor de archivos no hay tty
    # y la ventana se cerraria sin ver el resultado. Por eso pausa si no hay tty en cualquier SO.
    _is_ci = os.environ.get("GITHUB_ACTIONS") == "true" or "--terminal" in args_list
    if _is_ci:
        should_pause = False
    else:
        try:
            _has_tty = sys.stdin.isatty()
        except Exception:
            _has_tty = False
        should_pause = "--pause" in args_list or (not _has_tty)
    if should_pause:
        try:
            input("\nPresiona Enter para cerrar...")
        except Exception:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())

