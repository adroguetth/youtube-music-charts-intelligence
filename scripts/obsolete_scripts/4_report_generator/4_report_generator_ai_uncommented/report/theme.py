"""
Theme - Centralized Visual Configuration
============================================================================
Single source of truth for colors, fonts, and global visual settings.
Any change to the report's aesthetic should start here.

This module contains no logic and no side effects. It only declares
constants. The values are consumed by `report.setup` (which injects
them into the notebook's SETUP_CODE) and by `report.builders.common`
(for helpers that need to know border widths, etc.).

Notes
-----
- All colors are hex strings.
- Font sizes are in points (pt). Figure sizes are in inches.
- Keep this file free of dependencies to avoid import cycles.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

# ============================================================================
# COLORS
# ============================================================================
YT_RED: str = "#FC4B4B"          # Soft Red for main data
YT_DARK_GREY: str = "#282828"    # Dark Grey for comparisons
YT_TEXT: str = "#000000"         # Black for axis labels and text
YT_GRAY: str = "#606060"         # Medium Grey for secondary text
YT_GRID: str = "#E5E5E5"         # Light Grey for grid lines
YT_BG: str = "#FFFFFF"           # Pure White background
BORDER_COLOR: str = "#A0A0A0"    # Subtle grey for chart borders

# Categorical palette for multi-series charts (e.g., Temporal Analysis)
CATEGORICAL_PALETTE: list[str] = [
    "#FC4B4B",  # Soft Red
    "#282828",  # Dark Grey
    "#4A90E2",  # Steel Blue
    "#F5A623",  # Burnt Orange
    "#50E3C2",  # Aquamarine
]

# ============================================================================
# TYPOGRAPHY & SIZES
# ============================================================================
FONT_FAMILY: list[str] = ["Arial", "Helvetica", "DejaVu Sans"]
BASE_FONT_SIZE: int = 11
TITLE_FONT_SIZE: int = 18
FIGURE_DPI: int = 110
FIGURE_SIZE: tuple[int, int] = (12, 6)
BAR_HEIGHT: float = 0.65

# ============================================================================
# BORDERS & GRIDS
# ============================================================================
BORDER_WIDTH: float = 0.8
GRID_ALPHA: float = 0.7
GRID_STYLE: str = "--"
