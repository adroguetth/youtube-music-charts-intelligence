"""
Builders Common - Shared Visual Helpers
============================================================================
Reusable functions to apply standardized visual styles to Matplotlib
axes. This is the Python equivalent of the helpers that live inside
the notebook's SETUP_CODE, but intended for use *when building the cells*
(not inside the notebook).

Responsibilities
----------------
- `style_axes`: Applies borders, grids, and text colors to an axis object.
- `add_bar_labels`: Adds numeric labels to the end of bars in a bar chart.
- `add_currency_labels`: Adds currency-formatted labels (if needed).

Notes
-----
- These functions are called by the builders when generating the string
  code for the notebook cells. They do not execute inside the notebook
  itself; they are evaluated at generation time in the Python runtime.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

from typing import Literal

from report import theme


def style_axes(
    ax,
    grid_axis: Literal["x", "y"] = "y",
    show_labels: bool = True,
) -> None:
    """
    Apply the standardized border, grid, and tick styles to an axes object.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The axes to style.
    grid_axis : {"x", "y"}
        Which axis should display grid lines. ``"y"`` is the default for
        vertical bar charts; use ``"x"`` for horizontal bar charts.
    show_labels : bool
        Whether to show axis labels with the standard text color.
    """
    # Borders (spines)
    for spine in ax.spines.values():
        spine.set_color(theme.BORDER_COLOR)
        spine.set_linewidth(theme.BORDER_WIDTH)

    # Ticks
    ax.tick_params(colors=theme.YT_TEXT, labelsize=theme.BASE_FONT_SIZE)

    # Grid
    if grid_axis == "y":
        ax.yaxis.grid(True, color=theme.YT_GRID, linestyle=theme.GRID_STYLE, alpha=theme.GRID_ALPHA)
        ax.xaxis.grid(False)
    else:
        ax.xaxis.grid(True, color=theme.YT_GRID, linestyle=theme.GRID_STYLE, alpha=theme.GRID_ALPHA)
        ax.yaxis.grid(False)

    # Axis labels
    if show_labels:
        ax.xaxis.label.set_color(theme.YT_TEXT)
        ax.yaxis.label.set_color(theme.YT_TEXT)


def add_bar_labels(
    ax,
    fmt: str = "{:.0f}",
    suffix: str = "",
    horizontal: bool = True,
) -> None:
    """
    Add numeric labels to the end of bars in a bar chart.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The axes containing the bars.
    fmt : str
        Format string for the numeric value. Default ``"{:.0f}"`` (integer).
    suffix : str
        String to append after the number (e.g., ``"%"`` or ``"M"``).
    horizontal : bool
        If ``True``, labels are added to the right of horizontal bars.
        If ``False``, labels are added above vertical bars.
    """
    if horizontal:
        for p in ax.patches:
            width = p.get_width()
            if width == 0:
                continue
            ax.text(
                width + (width * 0.02),
                p.get_y() + p.get_height() / 2,
                f"{fmt.format(width)}{suffix}",
                ha="left",
                va="center",
                fontsize=theme.BASE_FONT_SIZE,
                color=theme.YT_TEXT,
            )
    else:
        for p in ax.patches:
            height = p.get_height()
            if height == 0:
                continue
            ax.text(
                p.get_x() + p.get_width() / 2,
                height + (height * 0.02),
                f"{fmt.format(height)}{suffix}",
                ha="center",
                va="bottom",
                fontsize=theme.BASE_FONT_SIZE,
                color=theme.YT_TEXT,
            )
