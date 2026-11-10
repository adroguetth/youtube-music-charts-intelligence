"""
Periods - Week Identification and Representation
============================================================================
Utilities to identify and represent the ISO week covered by a report.

Responsibilities
----------------
- `Period`: immutable value object with label, start and end dates.
- `previous_week`: resolve the ISO week immediately before a reference date.
- `week_from_label`: reconstruct a `Period` from a `YYYY-WXX` label.

Notes
-----
- Weeks follow ISO 8601: Monday to Sunday.
- No multi-period logic lives here yet. Monthly/quarterly/half-yearly
  periods will be introduced in a future version, and this module is the
  single place that will need to grow.
- This module contains no I/O. It is pure logic and fully testable
  without touching the filesystem or the database.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# ============================================================================
# PERIOD
# ============================================================================
@dataclass(frozen=True)
class Period:
    """
    Immutable representation of a reporting period.

    Attributes
    ----------
    label : str
        ISO week label, e.g. ``"2026-W46"``.
    start : date
        First day of the period (Monday).
    end : date
        Last day of the period (Sunday).
    """

    label: str
    start: date
    end: date

    @property
    def n_days(self) -> int:
        """Number of days covered by the period (inclusive)."""
        return (self.end - self.start).days + 1


# ============================================================================
# RESOLVERS
# ============================================================================
def previous_week(ref: date | None = None) -> Period:
    """
    Resolve the ISO week immediately before `ref` (defaults to today).

    Parameters
    ----------
    ref : date or None
        Reference date. Defaults to ``date.today()``.

    Returns
    -------
    Period
        Closed ISO week (Monday to Sunday) immediately before `ref`.
    """
    ref = ref or date.today()
    monday_this = ref - timedelta(days=ref.weekday())
    monday_prev = monday_this - timedelta(days=7)
    year, week, _ = monday_prev.isocalendar()
    return Period(
        label=f"{year}-W{week:02d}",
        start=monday_prev,
        end=monday_prev + timedelta(days=6),
    )


def week_from_label(label: str) -> Period:
    """
    Reconstruct a `Period` from a ``YYYY-WXX`` label.

    Parameters
    ----------
    label : str
        ISO week label, e.g. ``"2026-W46"``.

    Returns
    -------
    Period
        Period with the corresponding Monday and Sunday.

    Raises
    ------
    ValueError
        If `label` does not match the ``YYYY-WXX`` pattern.
    """
    year_str, week_str = label.split("-W")
    monday = date.fromisocalendar(int(year_str), int(week_str), 1)
    return Period(label=label, start=monday, end=monday + timedelta(days=6))
