"""Turn fetched numbers into the exact text shown on screen. Formatting only - no data."""
from __future__ import annotations

from datetime import date

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def fmt_value(value: float, units: str, decimals: int = 2, per: str = "") -> str:
    """Format a value with its unit, e.g. 7.11 -> '7.11%', 393300 -> '$393,300'."""
    if units == "percent":
        text = f"{value:.{decimals}f}%"
    elif units == "percentage_points":
        text = f"{value:.{decimals}f} percentage points"
    elif units == "usd":
        text = f"${value:,.{decimals}f}"
    elif units == "usd_trillions":
        text = f"${value:,.2f} trillion"
    elif units == "usd_billions":
        text = f"${value / 1000:,.2f} trillion" if abs(value) >= 1000 else f"${value:,.1f} billion"
    elif units == "usd_millions":
        text = f"${value / 1e6:,.2f} trillion" if abs(value) >= 1e6 else f"${value / 1000:,.1f} billion"
    elif units == "thousands":
        text = f"{value / 1000:,.1f} million" if abs(value) >= 1000 else f"{value * 1000:,.0f}"
    elif units == "count":
        text = f"{value:,.0f}"
    else:  # index and anything unknown
        text = f"{value:,.{decimals}f}"
    return f"{text} {per}".strip()


def fmt_change(diff: float, units: str, decimals: int = 2) -> str:
    """Size of a change, always positive; the caller says 'up' or 'down'."""
    return fmt_value(abs(diff), "percentage_points" if units == "percent" else units, decimals)


def fmt_pct(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}%"


def fmt_date(d: date, frequency: str = "daily") -> str:
    if frequency == "monthly":
        return f"{MONTHS[d.month - 1]} {d.year}"
    if frequency == "quarterly":
        return f"Q{(d.month - 1) // 3 + 1} {d.year}"
    if frequency == "annual":
        return f"fiscal year ending {MONTHS[d.month - 1][:3]} {d.year}"
    return f"{MONTHS[d.month - 1][:3]} {d.day}, {d.year}"


def direction(diff: float, tolerance: float = 1e-9) -> str:
    if diff > tolerance:
        return "up"
    if diff < -tolerance:
        return "down"
    return "flat"
