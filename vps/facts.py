"""Build the fact sheet. Every sentence here is assembled by code from fetched numbers.

A fact has a status:
  primary    - the number came straight from a primary data source
  calculated - arithmetic on primary numbers (the inputs are listed)
  verify     - it only appears in a news article; check it before saying it on camera
"""
from __future__ import annotations

import re
from datetime import timedelta

from . import fmt
from .sources.models import Series
from .transforms import monthly_payment, period_change, year_over_year, years_before

_UP = {"up": "up", "down": "down", "flat": "unchanged"}


def _fact(key: str, claim: str, value: str, as_of: str, series: Series, status: str = "primary",
          note: str = "", trend: str = "") -> dict:
    return {
        "key": key, "claim": claim, "value": value, "as_of": as_of,
        "source_name": series.source_name, "source_url": series.source_url,
        "status": status, "note": note, "series_id": series.id, "trend": trend,
    }


def _record_fact(series: Series, meta: dict) -> dict | None:
    """'Highest/lowest since X' - only when the latest value is an extreme for a year or more."""
    if len(series) < 3:
        return None
    latest, latest_date = series.latest_value, series.latest_date
    freq = meta.get("freq", "daily")
    for word, beats in (("highest", lambda v: v >= latest), ("lowest", lambda v: v <= latest)):
        previous = None
        for d, v in zip(reversed(series.dates[:-1]), reversed(series.values[:-1])):
            if beats(v):
                previous = d
                break
        if previous is None:
            since = fmt.fmt_date(series.dates[0], freq)
            years = (latest_date - series.dates[0]).days / 365.25
            if years >= 2:
                return _fact(f"{series.id}.record",
                             f"That is the {word} reading in the data fetched, which goes back to {since}.",
                             f"{word} since at least {since}", fmt.fmt_date(latest_date, freq), series,
                             status="calculated", trend=word)
        elif (latest_date - previous).days >= 365:
            when = fmt.fmt_date(previous, freq)
            return _fact(f"{series.id}.record", f"That is the {word} level since {when}.",
                         f"{word} since {when}", fmt.fmt_date(latest_date, freq), series, status="calculated", trend=word)
    return None


def level_facts(series: Series, meta: dict) -> list[dict]:
    """Facts for a series where the level itself is the story (rates, prices, counts)."""
    units, decimals, per, freq = meta.get("units", ""), meta.get("decimals", 2), meta.get("per", ""), meta.get("freq", "daily")
    noun = meta.get("noun", series.title)
    latest, latest_date = series.latest_value, series.latest_date
    value = fmt.fmt_value(latest, units, decimals, per)
    as_of = fmt.fmt_date(latest_date, freq)
    facts = [_fact(f"{series.id}.latest", f"{noun[0].upper()}{noun[1:]} was {value} as of {as_of}.", value, as_of, series)]

    target = years_before(latest_date, 1)
    year_ago = series.value_on_or_before(target)
    if year_ago is None and 0 < (series.dates[0] - target).days <= 10:
        year_ago = (series.dates[0], series.values[0])  # the source's history starts a few days short of a year
    if year_ago and (latest_date - year_ago[0]).days <= 400:
        old_date, old = year_ago
        diff = latest - old
        trend = fmt.direction(diff, 10 ** -(decimals + 1))
        old_text = fmt.fmt_value(old, units, decimals, per)
        old_when = fmt.fmt_date(old_date, freq)
        # Monthly and quarterly data: if the same period a year ago was never published,
        # say which period we compared with instead of calling it "a year earlier".
        exact = freq not in ("monthly", "quarterly") or old_date == target
        since = f"from a year earlier, when it was {old_text} ({old_when})" if exact else (
            f"from {old_when}, when it was {old_text} (the closest reading to a year earlier; "
            f"{fmt.fmt_date(target, freq)} was never published)")
        span = "in a year" if exact else f"since {old_when}"
        if trend == "flat":
            claim = (f"That is unchanged from a year earlier ({old_text} on {old_when})." if exact
                     else f"That is unchanged from {old_when} ({old_text}), the closest reading to a year earlier.")
            short = "unchanged from a year ago" if exact else f"unchanged since {old_when}"
        elif units in ("percent", "percentage_points"):
            size = fmt.fmt_change(diff, "percent", decimals)
            claim, short = f"That is {_UP[trend]} {size} {since}.", f"{_UP[trend]} {size} {span}"
        else:
            pct = fmt.fmt_pct(abs(diff / old * 100)) if old else ""
            claim, short = f"That is {_UP[trend]} {pct} {since}.", f"{_UP[trend]} {pct} {span}"
        facts.append(_fact(f"{series.id}.year", claim, short, as_of, series, status="calculated", trend=trend))

    if freq in ("daily", "weekly"):
        month_ago = series.value_on_or_before(latest_date - timedelta(days=30))
        if month_ago and (latest_date - month_ago[0]).days <= 45:
            old_date, old = month_ago
            diff = latest - old
            trend = fmt.direction(diff, 10 ** -(decimals + 1))
            if trend != "flat":
                if units in ("percent", "percentage_points"):
                    size = fmt.fmt_change(diff, "percent", decimals)
                else:
                    size = fmt.fmt_pct(abs(diff / old * 100)) if old else ""
                facts.append(_fact(
                    f"{series.id}.month",
                    f"Over the past month it is {_UP[trend]} {size} (from {fmt.fmt_value(old, units, decimals, per)} on {fmt.fmt_date(old_date, freq)}).",
                    f"{_UP[trend]} {size} in a month", as_of, series, status="calculated", trend=trend))

    record = _record_fact(series, meta)
    if record:
        facts.append(record)
    return facts


def yoy_facts(series: Series, meta: dict, window_years: int = 6) -> list[dict]:
    """Facts for an index where the story is the 12-month change (inflation-style)."""
    noun = meta.get("noun", series.title)
    yoy = year_over_year(series)
    facts: list[dict] = []
    if not len(yoy):
        return facts
    if yoy.latest_date != series.latest_date:
        month = fmt.fmt_date(series.latest_date, "monthly")
        facts.append({
            "key": f"{series.id}.yoy_missing",
            "claim": f"No 12-month change can be computed for {noun} in {month}: the same month a year earlier was never published.",
            "value": "", "as_of": month, "source_name": series.source_name, "source_url": series.source_url,
            "status": "primary", "note": "Left blank on purpose - no estimate is made. The figures below use the latest month that can be compared.",
            "series_id": series.id, "trend": "",
        })
    latest, month = yoy.latest_value, fmt.fmt_date(yoy.latest_date, "monthly")
    verb = "rose" if latest > 0 else "fell"
    value = fmt.fmt_pct(abs(latest))
    facts.append(_fact(f"{series.id}.yoy", f"{noun[0].upper()}{noun[1:]} {verb} {value} over the 12 months ending {month}.",
                       value, month, series, status="calculated", trend="up" if latest > 0 else "down"))
    if len(yoy) >= 2:
        prev, prev_month = yoy.values[-2], fmt.fmt_date(yoy.dates[-2], "monthly")
        trend = fmt.direction(latest - prev, 0.05)
        word = {"up": "faster than", "down": "slower than", "flat": "the same pace as"}[trend]
        facts.append(_fact(f"{series.id}.yoy_prev", f"That is {word} the {fmt.fmt_pct(prev)} pace in {prev_month}.",
                           fmt.fmt_pct(prev), prev_month, series, status="calculated", trend=trend))
    window = yoy.since(years_before(yoy.latest_date, window_years))
    if len(window) > 12:
        peak = max(window.values)
        peak_date = window.dates[window.values.index(peak)]
        if peak_date != yoy.latest_date:
            facts.append(_fact(f"{series.id}.yoy_peak",
                               f"The peak in the last {window_years} years was {fmt.fmt_pct(peak)} in {fmt.fmt_date(peak_date, 'monthly')}.",
                               fmt.fmt_pct(peak), fmt.fmt_date(peak_date, "monthly"), series, status="calculated"))
    return facts


def change_facts(series: Series, meta: dict) -> list[dict]:
    """Facts for a level where the story is the change each period (monthly payroll jobs)."""
    change = period_change(series)
    if not len(change):
        return []
    scale = 1000 if meta.get("units") == "thousands" else 1
    latest, month = change.latest_value * scale, fmt.fmt_date(change.latest_date, meta.get("freq", "monthly"))
    verb = "added" if latest >= 0 else "lost"
    value = f"{abs(latest):,.0f}"
    facts = [_fact(f"{series.id}.change", f"The economy {verb} {value} jobs in {month}.", value, month, series,
                   status="calculated", trend="up" if latest >= 0 else "down")]
    if len(change) >= 3:
        avg = sum(change.values[-3:]) / 3 * scale
        facts.append(_fact(f"{series.id}.avg3", f"The average over the last three months is {avg:+,.0f} jobs a month.",
                           f"{avg:+,.0f}", month, series, status="calculated"))
    return facts


def mortgage_payment_fact(rate_series: Series, price_series: Series) -> dict | None:
    """Worked example: monthly payment on the median-priced home, today's rate vs a year ago."""
    year_ago = rate_series.value_on_or_before(years_before(rate_series.latest_date, 1))
    if not year_ago:
        return None
    price = price_series.latest_value
    loan = price * 0.8
    now_rate, old_rate = rate_series.latest_value, year_ago[1]
    now_pay, old_pay = monthly_payment(loan, now_rate), monthly_payment(loan, old_rate)
    diff = now_pay - old_pay
    trend = fmt.direction(diff, 0.5)
    compare = f"about ${abs(diff):,.0f} a month {'more' if diff > 0 else 'less'} than" if trend != "flat" else "about the same as"
    claim = (
        f"Worked example: a 30-year loan for 80% of the median home price (${price:,.0f} in "
        f"{fmt.fmt_date(price_series.latest_date, 'quarterly')}, so a ${loan:,.0f} loan) costs about ${now_pay:,.0f} a month "
        f"in principal and interest at {now_rate:.2f}%. That is {compare} at the rate a year ago ({old_rate:.2f}%)."
    )
    return {
        "key": "WALLET.mortgage_payment", "claim": claim, "value": f"${now_pay:,.0f} a month",
        "as_of": fmt.fmt_date(rate_series.latest_date, "weekly"),
        "source_name": f"Calculated from {rate_series.source_name} and {price_series.source_name}",
        "source_url": rate_series.source_url, "status": "calculated",
        "note": "Illustration only: excludes taxes, insurance and fees. Inputs: " + price_series.source_url,
        "series_id": rate_series.id, "trend": trend,
    }


def edgar_facts(series: Series, ticker: str, label: str) -> list[dict]:
    """Facts from annual 10-K figures."""
    if not len(series):
        return []
    end = fmt.fmt_date(series.latest_date, "annual")
    value = fmt.fmt_value(series.latest_value, "usd_billions")
    facts = [_fact(f"{series.id}.latest", f"{ticker} reported {label} of {value} for its {end}.", value, end, series)]
    if len(series) >= 2 and series.values[-2]:
        pct = (series.latest_value / series.values[-2] - 1) * 100
        trend = fmt.direction(pct, 0.05)
        facts.append(_fact(f"{series.id}.year",
                           f"That is {_UP[trend]} {fmt.fmt_pct(abs(pct))} from {fmt.fmt_value(series.values[-2], 'usd_billions')} the fiscal year before.",
                           f"{_UP[trend]} {fmt.fmt_pct(abs(pct))} in a year", end, series, status="calculated", trend=trend))
    return facts


def filing_facts(ticker: str, company_name: str, filings: list[dict]) -> list[dict]:
    return [{
        "key": f"{ticker}.filing.{i}", "claim": f"{company_name} filed a Form {f['form']} with the SEC on {f['filed']}"
        + (f" (period ending {f['period']})." if f.get("period") else "."),
        "value": f["form"], "as_of": f["filed"], "source_name": "SEC EDGAR", "source_url": f["url"],
        "status": "primary", "note": "Read the filing itself for the numbers.", "series_id": "", "trend": "",
    } for i, f in enumerate(filings, 1)]


_NUMBER = re.compile(r"\d")


def news_facts(headlines: list[dict]) -> list[dict]:
    """Headlines from the report. News-only claims are always flagged 'verify'."""
    facts = []
    for i, h in enumerate(headlines, 1):
        has_number = bool(_NUMBER.search(h["title"]))
        facts.append({
            "key": f"NEWS.{i}", "claim": f"Reported: “{h['title']}”", "value": "", "as_of": "",
            "source_name": h.get("source") or "news article", "source_url": h.get("url", ""), "status": "verify",
            "note": ("Contains a number that comes only from a news article. Verify it against a primary source before saying it on camera."
                     if has_number else "News report, not a primary source. Verify before repeating it as fact."),
            "series_id": "", "trend": "",
        })
    return facts


def number_facts(facts: list[dict]) -> list[dict]:
    """Assign F1, F2, ... in display order."""
    for i, fact in enumerate(facts, 1):
        fact["id"] = f"F{i}"
    return facts


_LABEL_SUFFIX = {
    "year": "change in a year", "month": "change in a month", "record": "record", "yoy": "12-month change",
    "yoy_prev": "12-month change, month before", "yoy_peak": "recent peak", "change": "latest month",
    "avg3": "3-month average", "since_start": "change over the chart",
}


def fact_label(fact: dict) -> str:
    """A short name for a fact, for cards, thumbnails and change reports (e.g. '10-year Treasury yield')."""
    from . import catalog
    key = fact.get("key", "")
    if key == "WALLET.mortgage_payment":
        return "Example monthly mortgage payment"
    if key.startswith("NEWS."):
        return "News headline"
    title = catalog.SERIES.get(fact.get("series_id", ""), {}).get("title") or fact.get("series_id") or fact.get("source_name", "")
    suffix = _LABEL_SUFFIX.get(key.rsplit(".", 1)[-1])
    return f"{title} ({suffix})" if suffix else title
