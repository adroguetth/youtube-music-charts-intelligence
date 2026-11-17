"""
YouTube Charts Data Scraper (GitHub Actions Edition - Strict Mode)
============================================================================
Automated scraper for downloading YouTube Charts weekly data and storing it in
SQLite. Fallback mode DISABLED. Fails hard if download fails.

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
    """Check and install Playwright dependencies if needed."""
    print("🔧 Checking Playwright installation...")
    try:
        subprocess.run([sys.executable, "-c", "import playwright"], check=True, capture_output=True)
        print("   ✅ Playwright is installed")
        try:
            subprocess.run(["playwright", "install", "--dry-run"], check=True, capture_output=True)
            print("   ✅ Playwright browsers are installed")
            return True
        except Exception:
            print("   ⚠️  Browsers not installed, installing...")
            result = subprocess.run(["playwright", "install", "chromium"], capture_output=True, text=True)
            if result.returncode == 0:
                print("   ✅ Chromium browser installed")
                return True
            print(f"   ❌ Error installing browser: {result.stderr}")
            return False
    except ImportError:
        print("   ❌ Playwright is not installed")
        print("   📦 Installing Playwright...")
        result = subprocess.run([sys.executable, "-m", "pip", "install", "playwright", "pandas"], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"   ❌ Error installing Playwright: {result.stderr}")
            return False
        print("   ✅ Playwright installed")
        result = subprocess.run(["playwright", "install", "chromium"], capture_output=True, text=True)
        if result.returncode == 0:
            print("   ✅ Chromium browser installed")
            return True
        print(f"   ❌ Error installing browser: {result.stderr}")
        return False

# ============================================================================
# WEEK IDENTIFIER
# ============================================================================
def get_week_identifier(date: datetime = None) -> str:
    if date is None:
        date = datetime.now()
    year, week_num, _ = date.isocalendar()
    return f"{year}-W{week_num:02d}"

# ============================================================================
# YOUTUBE CHARTS DOWNLOADER (STRICT MODE)
# ============================================================================
async def download_youtube_charts() -> Path | None:
    """
    Download YouTube Charts data using Playwright.
    Returns the Path if successful, None if it fails.
    """
    print("🎵 YouTube Charts - Downloading complete CSV (100 songs)")
    print("=" * 70)

    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

        async with async_playwright() as p:
            print("1. 🚀 Starting browser (Headless, Strict)...")
            
            # Argumentos para GitHub Actions (Linux)
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                    "--window-size=1920,1080",
                    "--disable-extensions",
                    "--single-process",  # Ayuda en contenedores
                    "--no-zygote",
                ],
            )

            context = await browser.new_context(
                accept_downloads=True,
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Referer": "https://charts.youtube.com/",
                    "DNT": "1",
                },
            )

            # Script anti-detección
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)

            page = await context.new_page()
            page.set_default_timeout(120_000)

            print("2. 🌐 Navigating to YouTube Charts...")
            url = "https://charts.youtube.com/charts/TopSongs/global/weekly"
            
            # Usar domcontentloaded para no colgarse esperando networkidle
            await page.goto(url, wait_until="domcontentloaded", timeout=120_000)

            print("3. ⏳ Waiting for page to settle (simulating human)...")
            await page.wait_for_timeout(5_000)
            
            # Simular movimiento de ratón para despertar posibles componentes
            await page.mouse.move(100, 100)
            await page.wait_for_timeout(1_000)
            await page.mouse.move(500, 500)
            await page.wait_for_timeout(2_000)

            print("4. 📜 Scrolling to load dynamic content...")
            for i in range(3):
                await page.evaluate("window.scrollBy(0, 800)")
                await page.wait_for_timeout(1_500)

            print("5. 🔍 SEARCHING FOR DOWNLOAD BUTTON (Strict Mode)...")
            
            # Estrategia: Esperar explícitamente con reintentos
            max_retries = 3
            button_found = False
            
            for attempt in range(1, max_retries + 1):
                print(f"   🔎 Intento {attempt}/{max_retries} buscando el botón...")
                try:
                    # Esperar a que el selector exista en el DOM
                    # Usamos state="attached" para no fallar si está oculto temporalmente
                    await page.wait_for_selector("#download-button", state="attached", timeout=20_000)
                    
                    # Verificar que sea visible (o forzar scroll)
                    button = await page.query_selector("#download-button")
                    if button:
                        is_visible = await button.is_visible()
                        print(f"   ✅ Botón encontrado en DOM. Visible: {is_visible}")
                        
                        if not is_visible:
                            print("   🔍 Haciendo scroll hacia el botón...")
                            await button.scroll_into_view_if_needed()
                            await page.wait_for_timeout(2_000)
                            is_visible = await button.is_visible()
                            print(f"   👁️ Visible después de scroll: {is_visible}")
                        
                        if is_visible:
                            button_found = True
                            break
                    else:
                        print("   ⚠️ Selector apareció pero query_selector retornó None.")
                        
                except PlaywrightTimeoutError:
                    print(f"   ⚠️ Botón no encontrado en intento {attempt}.")
                
                if attempt < max_retries:
                    print("   🔄 Recargando página para reintentar...")
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(5_000)
                    # Mover ratón de nuevo después de recargar
                    await page.mouse.move(200, 200)

            if not button_found:
                print("   ❌ El botón no apareció tras todos los intentos.")
                await page.screenshot(path=str(ARCHIVE_DIR / "error_no_button.png"))
                await browser.close()
                return None

            # Si llegamos aquí, el botón existe y es visible
            print("   ⬇️  Triggering download...")
            filename = ARCHIVE_DIR / "latest_chart.csv"

            try:
                # IMPORTANTE: expect_download va en PAGE, no en CONTEXT
                async with page.expect_download(timeout=60_000) as dl_info:
                    # Clic por JavaScript para evitar problemas de intercepción
                    await page.evaluate("document.querySelector('#download-button').click()")
                    # Pequeña espera para que el navegador procese
                    await page.wait_for_timeout(3_000)

                download = await dl_info.value
                await download.save_as(filename)
                
                # Verificar que el archivo existe y no está vacío
                if filename.exists() and filename.stat().st_size > 0:
                    print(f"   💾 File downloaded: {filename.stat().st_size} bytes")
                    await browser.close()
                    return filename
                else:
                    print("   ❌ Archivo descargado está vacío o no existe.")
                    await browser.close()
                    return None

            except PlaywrightTimeoutError:
                print("   ❌ Timeout esperando el evento de descarga.")
                await page.screenshot(path=str(ARCHIVE_DIR / "error_download_timeout.png"))
                await browser.close()
                return None
            except Exception as e:
                print(f"   ❌ Error durante el clic/descarga: {e}")
                await page.screenshot(path=str(ARCHIVE_DIR / "error_click_exception.png"))
                await browser.close()
                return None

    except Exception as e:
        print(f"⚠️  Error crítico en el proceso: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============================================================================
# BACKUP & CLEANUP (sin cambios)
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
# SQLITE DATABASE UPDATE (sin cambios)
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
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chart_data'")
        
        if cursor.fetchone():
            cursor.execute("DELETE FROM chart_data WHERE week_id = ?", (week_id,))
            try:
                cursor.execute(f"INSERT INTO chart_data SELECT * FROM {temp_table_name}")
                cursor.execute(f"DROP TABLE {temp_table_name}")
            except sqlite3.OperationalError as e:
                if "columns" in str(e).lower():
                    print("   ⚠️  Schema mismatch, recreating table...")
                    cursor.execute("DROP TABLE IF EXISTS chart_data")
                    cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO chart_data")
                else:
                    raise
        else:
            cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO chart_data")

        cursor.execute("SELECT COUNT(*) FROM chart_data")
        total_records = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        print("   ✅ Database updated successfully!")
        print(f"      📊 Total records: {total_records:,}")
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
            conn.close()
            size_kb = db.stat().st_size / 1024
            week_id = db.stem.replace("youtube_charts_", "")
            total_records += count
            print(f"   • {week_id}: {count:,} records, {size_kb:.1f} KB")
        except Exception:
            size_kb = db.stat().st_size / 1024
            print(f"   • {db.stem}: Error reading, {size_kb:.1f} KB")
    print(f"\n   📊 TOTAL: {total_records:,} records in {len(dbs)} databases")

# ============================================================================
# MAIN (STRICT MODE)
# ============================================================================
def main() -> int:
    print("\n" + "=" * 70)
    print("🎵 YOUTUBE CHARTS - STRICT EXTRACTOR (No Fallback)")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    print("\n0. 🔧 CHECKING DEPENDENCIES...")
    if not install_playwright():
        print("❌ CRITICAL: Playwright not ready. Aborting.")
        return 1

    week_id = get_week_identifier()
    print(f"\n📆 Current week: {week_id}")

    print("\n1. 📥 DOWNLOADING YOUTUBE CHARTS (Strict)...")
    csv_path = asyncio.run(download_youtube_charts())

    # STRICT MODE: Si no hay CSV, abortar.
    if not csv_path or not csv_path.exists():
        print("\n❌ CRITICAL ERROR: Automatic download failed.")
        print("🛑 Fallback mode disabled. Aborting execution to prevent data pollution.")
        return 1

    print(f"\n   📄 File obtained: {csv_path.name}")
    try:
        with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            num_songs = len(lines) - 1 if len(lines) > 1 else 0
            print(f"   📈 Songs in CSV: {num_songs}")
    except Exception as e:
        print(f"   ⚠️  Error reading CSV: {e}")
        return 1

    print("\n2. 🗃️  STORING IN SQLITE DATABASE...")
    db_path = update_sqlite_database(csv_path, week_id)
    if not db_path:
        print("❌ Critical error updating database")
        return 1

    print("\n3. 🧹 CLEANING OLD FILES...")
    cleanup_old_backups(7)
    cleanup_old_databases(52)

    print("\n4. 📊 FINAL SUMMARY:")
    list_available_databases()

    print("\n" + "=" * 70)
    print("✅ PROCESS COMPLETED SUCCESSFULLY")
    print("=" * 70)
    return 0

if __name__ == "__main__":
    sys.exit(main())
