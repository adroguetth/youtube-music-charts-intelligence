"""
YouTube Charts Data Scraper
============================================================================
Automated scraper for downloading YouTube Charts weekly data and storing it in
SQLite. Handles dependency installation (Playwright), browser automation with
anti-detection measures, CSV download, SQLite persistence with versioning by
week, backup management, and cleanup of old files.

This module is the entry point of the scraper. It orchestrates the full
pipeline: dependency check → download → database update → cleanup → summary.

Features
--------
- Downloads complete CSV files (100 songs) from YouTube Charts.
- Stores historical data in SQLite with versioning by week.
- Automatic backup system before database updates.
- Handles Playwright browser automation with anti-detection measures.
- Strict failure: If download fails, it stops (NO fallback data).

Dependencies
------------
- Internal: none (self-contained script).
- External: playwright, pandas, sqlite3 (stdlib), asyncio, shutil, subprocess.
- Downstream: none (this is the entry point).

Requirements
------------
- Python 3.7+
- Playwright with Chromium browser (auto-installed if missing).
- Pandas (auto-installed if missing).

Notes
-----
- Directory structure is created automatically on import:
  `data/`, `charts_archive/1_download-chart/databases/`, and
  `charts_archive/1_download-chart/backup/`.
- Week identifiers follow ISO format `YYYY-WXX` (e.g., `2025-W05`).
- Backups are retained for 7 days; databases are retained for 52 weeks.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence 
Email: adroguett.consultor@gmail.com
"""

import asyncio
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================================
# CONSTANTS AND DIRECTORIES
# ============================================================================
OUTPUT_DIR = Path("data")
ARCHIVE_DIR = Path("charts_archive/1_download-chart")
DATABASE_DIR = ARCHIVE_DIR / "databases"
BACKUP_DIR = ARCHIVE_DIR / "backup"

for dir_path in [OUTPUT_DIR, ARCHIVE_DIR, DATABASE_DIR, BACKUP_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)


# ============================================================================
# DEPENDENCY MANAGEMENT
# ============================================================================
def install_playwright() -> bool:
    """
    Check and install Playwright dependencies if needed.
    """
    print("🔧 Checking Playwright installation...")

    try:
        subprocess.run(
            [sys.executable, "-c", "import playwright"],
            check=True,
            capture_output=True,
        )
        print("   ✅ Playwright is installed")

        try:
            subprocess.run(
                ["playwright", "install", "--dry-run"],
                check=True,
                capture_output=True,
            )
            print("   ✅ Playwright browsers are installed")
            return True
        except Exception:
            print("   ⚠️  Browsers not installed, installing...")
            result = subprocess.run(
                ["playwright", "install", "chromium"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print("   ✅ Chromium browser installed")
                return True
            print(f"   ❌ Error installing browser: {result.stderr}")
            return False

    except ImportError:
        print("   ❌ Playwright is not installed")
        print("   📦 Installing Playwright...")

        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright", "pandas"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"   ❌ Error installing Playwright: {result.stderr}")
            return False

        print("   ✅ Playwright installed")
        result = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("   ✅ Chromium browser installed")
            return True
        print(f"   ❌ Error installing browser: {result.stderr}")
        return False


# ============================================================================
# WEEK IDENTIFIER
# ============================================================================
def get_week_identifier(date: datetime = None) -> str:
    """
    Generate ISO week identifier string.
    """
    if date is None:
        date = datetime.now()
    year, week_num, _ = date.isocalendar()
    return f"{year}-W{week_num:02d}"


# ============================================================================
# YOUTUBE CHARTS DOWNLOADER
# ============================================================================
async def download_youtube_charts() -> Path | None:
    """
    Download YouTube Charts data using Playwright browser automation.
    Simulates realistic human interaction to bypass anti-bot measures.
    """
    print("🎵 YouTube Charts - Downloading complete CSV (100 songs)")
    print("=" * 70)

    try:
        from playwright.async_api import async_playwright

        print("1. 🚀 Starting browser...")

        async with async_playwright() as p:
            # Argumentos optimizados para GitHub Actions (Linux) y evasión
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--window-size=1920,1080",
                    "--start-maximized",
                    "--mute-audio",
                    "--no-zygote"
                ],
            )

            context = await browser.new_context(
                accept_downloads=True,
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                permissions=["clipboard-read", "clipboard-write", "geolocation"],
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/webp,*/*;q=0.8"
                    ),
                    "Referer": "https://charts.youtube.com/",
                    "DNT": "1",
                    "Upgrade-Insecure-Requests": "1"
                },
            )

            # Script de evasión profunda (Simula un navegador real)
            await context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        { name: 'Chrome PDF Plugin' },
                        { name: 'Chrome PDF Viewer' },
                        { name: 'Native Client' }
                    ]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                window.chrome = { runtime: {} };
                """
            )

            page = await context.new_page()
            page.set_default_timeout(90_000)

            print("2. 🌐 Navigating to YouTube Charts...")
            url = "https://charts.youtube.com/charts/TopSongs/global/weekly"
            
            await page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            
            print("3. ⏳ Waiting for page to fully load...")
            try:
                await page.wait_for_selector("#download-button", state="attached", timeout=30_000)
                print("   ✅ Botón detectado en el DOM")
            except Exception:
                print("   ⚠️ El botón no apareció a tiempo, continuando de todas formas...")
            
            await page.wait_for_timeout(5000) 

            print("4. 📜 Scrolling to load dynamic content...")
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 800)")
                await page.wait_for_timeout(1500)

            print("5. 🔍 SEARCHING FOR DOWNLOAD BUTTON...")
            filename = ARCHIVE_DIR / "latest_chart.csv"

            print("   🎯 Triggering download from Context level...")
            try:
                # A nivel de context es más seguro para descargas dinámicas
                async with context.expect_download(timeout=60_000) as dl_info:
                    # Técnica avanzada: Disparar evento 'click' nativo del navegador
                    await page.evaluate("""
                        const btn = document.querySelector('#download-button');
                        if (btn) {
                            // Simular hover
                            const mouseoverEvent = new Event('mouseover', { bubbles: true });
                            btn.dispatchEvent(mouseoverEvent);
                            
                            // Clic sintético (evade validación isTrusted)
                            const clickEvent = new MouseEvent('click', {
                                view: window,
                                bubbles: true,
                                cancelable: true
                            });
                            btn.dispatchEvent(clickEvent);
                        }
                    """)
                    
                    # Damos tiempo a que el navegador procese el Blob/Descarga
                    await page.wait_for_timeout(3000)

                # Si llegamos aquí, Playwright capturó la descarga
                download = await dl_info.value
                await download.save_as(filename)
                
                print(f"   💾 ¡Descarga exitosa! Tamaño: {filename.stat().st_size} bytes")
                await browser.close()
                return filename

            except Exception as e:
                print(f"   ❌ Error al descargar: {e}")
                # Tomar captura de pantalla para depurar en GitHub Actions
                error_img = ARCHIVE_DIR / "error_github_actions.png"
                await page.screenshot(path=error_img)
                print(f"   📸 Captura guardada en {error_img}")
                raise e # Relanzamos el error para que main() lo detenga

    except Exception as e:
        print(f"⚠️  Error crítico en el proceso: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# BACKUP MANAGEMENT
# ============================================================================
def create_backup_before_update(week_id: str) -> None:
    db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"

    if not db_path.exists():
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = BACKUP_DIR / f"backup_{week_id}_{timestamp}.db"

    try:
        shutil.copy2(db_path, backup_filename)
        print(f"   ✅ Backup created: {backup_filename.name}")
    except Exception as e:
        print(f"   ⚠️  Error creating backup: {e}")


def cleanup_old_backups(days: int = 7) -> None:
    print(f"   🧹 Cleaning backups older than {days} days...")

    cutoff_date = datetime.now() - timedelta(days=days)
    deleted_count = 0

    for backup in BACKUP_DIR.glob("backup_*.db"):
        if backup.stat().st_mtime < cutoff_date.timestamp():
            try:
                backup.unlink()
                deleted_count += 1
            except Exception as e:
                print(f"   ⚠️  Error deleting {backup.name}: {e}")

    if deleted_count > 0:
        print(f"   ✅ Deleted {deleted_count} old backup(s)")
    else:
        print("   ℹ️  No old backups to delete")


def cleanup_old_databases(weeks: int = 52) -> None:
    print(f"   🧹 Cleaning databases older than {weeks} weeks...")

    current_date = datetime.now()
    cutoff_date = current_date - timedelta(weeks=weeks)
    deleted_count = 0

    for db in DATABASE_DIR.glob("youtube_charts_*.db"):
        try:
            week_id = db.stem.replace("youtube_charts_", "")
            year, week = map(int, week_id.split("-W"))
            db_date = datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w")

            if db_date < cutoff_date:
                db.unlink()
                deleted_count += 1
                print(f"      ✅ Deleted: {db.name}")
        except Exception as e:
            print(f"   ⚠️  Error processing {db.name}: {e}")

    if deleted_count > 0:
        print(f"   ✅ Deleted {deleted_count} old database(s)")
    else:
        print("   ℹ️  No old databases to delete")


# ============================================================================
# SQLITE DATABASE UPDATE
# ============================================================================
def update_sqlite_database(csv_path: Path, week_id: str) -> Path | None:
    print("   📊 Processing chart data...")

    try:
        import sqlite3
        import pandas as pd

        try:
            df = pd.read_csv(csv_path, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="latin-1")

        print(f"   📈 Songs loaded: {len(df)}")

        if len(df) > 0:
            print(f"   📋 Columns: {', '.join(df.columns.tolist())}")
            print("   🎵 Sample songs:")
            for i in range(min(5, len(df))):
                row = df.iloc[i]
                track = str(row.get("Track Name", "N/A"))[:30]
                artist = str(row.get("Artist Names", "N/A"))[:30]
                print(f"      {i + 1}. {track}... - {artist}...")

        current_time = datetime.now()
        df["download_date"] = current_time.strftime("%Y-%m-%d")
        df["download_time"] = current_time.strftime("%H:%M:%S")
        df["week_id"] = week_id
        df["timestamp"] = current_time.strftime("%Y%m%d_%H%M%S")

        db_path = DATABASE_DIR / f"youtube_charts_{week_id}.db"

        if db_path.exists():
            print("   💾 Creating backup before update...")
            create_backup_before_update(week_id)

        conn = sqlite3.connect(db_path)
        temp_table_name = f"temp_{current_time.strftime('%Y%m%d_%H%M%S')}"
        df.to_sql(temp_table_name, conn, if_exists="replace", index=False)

        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='chart_data'"
        )

        if cursor.fetchone():
            cursor.execute("DELETE FROM chart_data WHERE week_id = ?", (week_id,))
            deleted_rows = cursor.rowcount
            if deleted_rows > 0:
                print(f"   🗑️  Deleted {deleted_rows} old records for {week_id}")

            try:
                cursor.execute(
                    f"INSERT INTO chart_data SELECT * FROM {temp_table_name}"
                )
                cursor.execute(f"DROP TABLE {temp_table_name}")
            except sqlite3.OperationalError as e:
                if "columns" in str(e).lower():
                    print("   ⚠️  Schema mismatch detected, recreating table...")
                    cursor.execute("DROP TABLE IF EXISTS chart_data")
                    cursor.execute(
                        f"ALTER TABLE {temp_table_name} RENAME TO chart_data"
                    )
                else:
                    raise
        else:
            cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO chart_data")

        indices = [
            ("idx_date", "chart_data(download_date)"),
            ("idx_week", "chart_data(week_id)"),
            ("idx_rank", "chart_data(Rank)"),
            ("idx_artist", "chart_data(Artist Names)"),
        ]
        for idx_name, idx_columns in indices:
            try:
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_columns}"
                )
            except Exception:
                pass

        cursor.execute("SELECT COUNT(*) FROM chart_data")
        total_records = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT download_date) FROM chart_data")
        unique_dates = cursor.fetchone()[0]

        conn.commit()
        conn.close()

        print("   ✅ Database updated successfully!")
        print(f"      📊 Total records: {total_records:,}")
        print(f"      📅 Unique dates: {unique_dates}")
        print(f"      💾 Location: {db_path}")

        return db_path

    except Exception as e:
        print(f"⚠️  SQLite error: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# DATABASE INVENTORY
# ============================================================================
def list_available_databases() -> None:
    import sqlite3

    dbs = sorted(DATABASE_DIR.glob("youtube_charts_*.db"))

    if not dbs:
        print("   ℹ️  No databases available yet")
        return

    print(f"\n📦 Available databases ({len(dbs)}):")
    total_records = 0

    for db in dbs:
        try:
            conn = sqlite3.connect(db)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM chart_data")
            count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT MIN(download_date), MAX(download_date) FROM chart_data"
            )
            min_date, max_date = cursor.fetchone()
            conn.close()

            size_kb = db.stat().st_size / 1024
            week_id = db.stem.replace("youtube_charts_", "")
            total_records += count

            print(f"   • {week_id}: {count:,} records, {size_kb:.1f} KB")
            if min_date and max_date:
                print(f"     📅 {min_date} to {max_date}")

        except Exception:
            size_kb = db.stat().st_size / 1024
            week_id = db.stem.replace("youtube_charts_", "")
            print(f"   • {week_id}: Error reading, {size_kb:.1f} KB")

    print(f"\n   📊 TOTAL: {total_records:,} records in {len(dbs)} databases")


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    """
    Entry point of the scraper.
    """
    print("\n" + "=" * 70)
    print("🎵 YOUTUBE CHARTS - COMPLETE EXTRACTOR (100 songs)")
    print("   COMPLETE CSV DOWNLOAD + SQLITE STORAGE")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    print("\n0. 🔧 CHECKING DEPENDENCIES...")
    playwright_ready = install_playwright()

    if not playwright_ready:
        print("❌ CRITICAL ERROR: Playwright is not ready. Aborting.")
        return 1

    week_id = get_week_identifier()
    print(f"\n📆 Current week: {week_id}")
    print("💻 Running locally / cloud")

    print("\n1. 📥 DOWNLOADING YOUTUBE CHARTS (Complete CSV)...")
    print("   ⏱️  This may take 1-2 minutes...")

    csv_path = asyncio.run(download_youtube_charts())

    # CONTROL ESTRICTO: Si no se descargó, el script muere aquí.
    if not csv_path or not os.path.exists(csv_path):
        print("\n❌ CRITICAL ERROR: Automatic download failed.")
        print("🛑 Fallback mode disabled. Aborting execution to prevent data pollution.")
        return 1

    print(f"\n   📄 File obtained: {csv_path.name}")
    try:
        with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            num_songs = len(lines) - 1 if len(lines) > 1 else 0
            print(f"   📈 Songs in CSV: {num_songs}")

            if len(lines) > 1:
                print(f"   📋 Headers: {lines[0].strip()}")
                if len(lines) > 2:
                    print(f"   🎵 First song: {lines[1][:100]}...")
    except Exception as e:
        print(f"   ⚠️  Error reading CSV: {e}")

    print("\n3. 🗃️  STORING IN SQLITE DATABASE...")
    db_path = update_sqlite_database(csv_path, week_id)

    if not db_path:
        print("❌ Critical error updating database")
        return 1

    print("\n4. 🧹 CLEANING OLD FILES...")
    cleanup_old_backups(7)
    cleanup_old_databases(52)

    print("\n5. 📊 FINAL SUMMARY:")
    list_available_databases()

    print("\n" + "=" * 70)
    print("✅ PROCESS COMPLETED SUCCESSFULLY")
    print("🎉 CSV with 100 songs stored in SQLite")
    print("=" * 70)

    return 0


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    sys.exit(main())
