"""
Renderer - Quarto Compilation Engine
============================================================================
Executes the Quarto CLI to render the .qmd templates into final reports
(HTML and PDF).

This module acts as the bridge between the Python environment (which has
the data and AI insights) and the Quarto engine (which handles the visual
layout and rendering).

Features
--------
- Passes parameters dynamically to the Quarto document using `-P`.
- Supports both HTML and PDF rendering in a single call.
- Handles paths correctly to ensure outputs are saved in the `reports/` folder.
- Captures Quarto's console output and logs it for debugging.

Dependencies
------------
- Internal: `..config` (paths, logger).
- External: subprocess, pathlib (stdlib).

Requirements
------------
- Python 3.7+
- Quarto CLI installed and accessible in the system PATH.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import subprocess
import json
from pathlib import Path

from ..config import TEMPLATES_DIR, OUTPUT_DIR, logger


def render_report(
    week_str: str, 
    ai_data: dict, 
    language: str = "en", 
    formats: list = ["html", "pdf"]
) -> list[Path]:
    """
    Renders the Quarto report for a specific language.

    Parameters
    ----------
    week_str : str
        The week identifier (e.g., '2026-W45').
    ai_data : dict
        Dictionary with AI-generated texts (intro, trend, top_songs, countries).
    language : str
        'en' for English or 'es' for Spanish.
    formats : list
        List of output formats to generate (e.g., ['html', 'pdf']).

    Returns
    -------
    list of Path
        List of paths to the generated files.
    """
    
    # 1. Locate the template
    qmd_file = TEMPLATES_DIR / f"report_{language}.qmd"
    if not qmd_file.exists():
        raise FileNotFoundError(f"❌ Template not found: {qmd_file}")

    generated_files = []

    # 2. Loop through requested formats
    for fmt in formats:
        logger.info(f"🎨 Rendering {language.upper()} report as {fmt.upper()}...")
        
        output_filename = f"report_{week_str}_{language}.{fmt}"
        output_path = OUTPUT_DIR / output_filename

        # 3. Build the Quarto command
        # We pass the AI data as a JSON string to avoid quote escaping issues
        cmd = [
            "quarto", "render", str(qmd_file),
            "--to", fmt,
            "--output", output_filename,
            "--output-dir", str(OUTPUT_DIR),
            "-P", f"week_str:{week_str}",
            "-P", f"ai_intro:{ai_data.get('intro', '')}",
            "-P", f"ai_trend:{ai_data.get('trend', '')}",
            "-P", f"ai_top_songs:{ai_data.get('top_songs', '')}",
            "-P", f"ai_countries:{ai_data.get('countries', '')}"
        ]

        # 4. Execute Quarto
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Quarto sometimes prints warnings to stderr even on success
            if result.stderr and "WARNING" not in result.stderr:
                logger.debug(f"Quarto stderr: {result.stderr}")

            if output_path.exists():
                logger.info(f"   ✅ Generated: {output_path.name}")
                generated_files.append(output_path)
            else:
                logger.warning(f"   ⚠️ Quarto finished but output not found: {output_path.name}")

        except subprocess.CalledProcessError as e:
            logger.error(f"   ❌ Quarto rendering failed for {fmt.upper()}")
            logger.error(f"   Error output: {e.stderr}")
            raise e
        except FileNotFoundError:
            logger.error("   ❌ Quarto CLI not found. Is Quarto installed and in the PATH?")
            raise

    return generated_files
