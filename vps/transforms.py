"""Arithmetic on fetched series. Every output number is computed from real observations."""
from __future__ import annotations

from datetime import date

from .sources.models import Series


def _derived(series: Series, dates: list[date], values: list[float], title: str, units: str) -> Series:
    return Series(series.id, title, units, dates, values, series.source_name, series.source_url,
                  series.frequency, series.fetched_via, list(series.notes))


def year_over_year(series: Series) -> Series:
    """12-month % change for a monthly series. A month is skipped when the same month a
    year earlier was never published - we do not interpolate."""
    by_date = dict(zip(series.dates, series.values))
    dates, values = [], []
    for d, v in zip(series.dates, series.values):
        try:
            prior = by_date.get(d.replace(year=d.year - 1))
        except ValueError:  # Feb 29
            prior = None
        if prior:
            dates.append(d)
            values.append((v / prior - 1) * 100)
    return _derived(series, dates, values, series.title, "percent")


def period_change(series: Series) -> Series:
    """Change from the previous observation (e.g. jobs added this month).

    If an observation is missing (a month that was never published), the change across
    that gap is skipped rather than passed off as a one-period change."""
    gaps = sorted((b - a).days for a, b in zip(series.dates, series.dates[1:]))
    typical = gaps[len(gaps) // 2] if gaps else 0
    dates, values = [], []
    for i in range(1, len(series)):
        if typical and (series.dates[i] - series.dates[i - 1]).days > typical * 1.5:
            continue
        dates.append(series.dates[i])
        values.append(series.values[i] - series.values[i - 1])
    return _derived(series, dates, values, series.title, series.units)


def rebase_to_100(series: Series) -> Series:
    """Rebase so the first observation equals 100."""
    if not series.values or series.values[0] == 0:
        return _derived(series, [], [], series.title, "index")
    base = series.values[0]
    return _derived(series, list(series.dates), [v / base * 100 for v in series.values], series.title, "index")


def years_before(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


def monthly_payment(principal: float, annual_rate_percent: float, years: int = 30) -> float:
    """Principal-and-interest payment on a fixed-rate loan (standard amortization formula)."""
    monthly_rate = annual_rate_percent / 100 / 12
    n = years * 12
    if monthly_rate == 0:
        return principal / n
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** -n)


def recession_spans(flag_series: Series) -> list[tuple[date, date]]:
    """Turn a monthly 0/1 recession flag into (start, end) spans."""
    spans, start, last = [], None, None
    for d, v in zip(flag_series.dates, flag_series.values):
        if v >= 0.5 and start is None:
            start = d
        if v < 0.5 and start is not None:
            spans.append((start, last or d))
            start = None
        last = d
    if start is not None and last is not None:
        spans.append((start, last))
    return spans
