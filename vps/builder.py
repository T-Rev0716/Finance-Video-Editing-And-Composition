"""Fetch the data for a topic, render its charts and build the fact sheet.

Nothing in this module uses an LLM. If a source fails, that chart or fact is skipped
and the reason is recorded - a number is never filled in.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Callable

from . import catalog, charts, facts, fmt, transforms, watch
from .sources import bls, edgar, fred, treasury
from .sources.http import FetchError
from .sources.models import Series

HISTORY_START = date(2000, 1, 1)  # long enough to say "highest since ..."


class DataContext:
    """One generation run: settings, a series cache and the warnings collected along the way."""

    def __init__(self, settings: dict, today: date | None = None):
        self.settings = settings
        self.today = today or date.today()
        self.cache: dict[str, Series] = {}
        self.warnings: list[str] = []
        self.raw: dict[str, Series] = {}  # everything fetched, saved as CSV for provenance

    def fred(self, series_id: str) -> Series:
        if series_id not in self.cache:
            meta = catalog.SERIES.get(series_id, {})
            self.cache[series_id] = fred.fetch_series(
                series_id, title=meta.get("title", ""), units=meta.get("units", ""),
                source_org=meta.get("org", ""), frequency=meta.get("freq", ""),
                start=HISTORY_START, api_key=self.settings.get("FRED_API_KEY", ""),
            )
            self.raw[series_id] = self.cache[series_id]
            for note in self.cache[series_id].notes:
                if note not in self.warnings:
                    self.warnings.append(note)
        return self.cache[series_id]


def _meta(series_id: str, series: Series) -> dict:
    meta = dict(catalog.SERIES.get(series_id, {}))
    meta.setdefault("noun", series.title)
    meta.setdefault("units", series.units or "index")
    meta.setdefault("freq", series.frequency or "daily")
    meta.setdefault("decimals", 2)
    return meta


def _recessions(ctx: DataContext, start: date) -> list[tuple[date, date]]:
    try:
        spans = transforms.recession_spans(ctx.fred("USREC"))
    except FetchError:
        return []
    return [(max(a, start), b) for a, b in spans if b >= start]


def build_chart(chart_id: str, spec: dict, ctx: DataContext, tickers: list[str]) -> tuple[dict, list[dict]]:
    """Returns (chart ready to render, facts). Raises FetchError/ValueError if unusable."""
    kind = spec["kind"]
    start = transforms.years_before(ctx.today, spec.get("years", 5))
    chart = {"id": chart_id, "kind": kind, "title": spec["title"], "teaches": spec.get("teaches", ""),
             "target": spec.get("target"), "target_label": spec.get("target_label"),
             "zero_line": spec.get("zero_line", False), "series": [], "units": "index", "decimals": 2}
    chart_facts: list[dict] = []

    if kind in ("lines", "bars"):
        for sid in spec["series"]:
            full = ctx.fred(sid)
            meta = _meta(sid, full)
            chart["series"].append(full.since(start))
            chart_facts += facts.level_facts(full, meta)
            chart["units"], chart["decimals"] = meta["units"], meta["decimals"]
        if kind == "lines" and spec.get("years", 5) >= 10:
            chart["recessions"] = _recessions(ctx, start)
    elif kind == "yoy":
        for sid in spec["series"]:
            full = ctx.fred(sid)
            chart["series"].append(transforms.year_over_year(full).since(start))
            chart_facts += facts.yoy_facts(full, _meta(sid, full), spec.get("years", 6))
        chart["units"], chart["decimals"] = "percent", 1
    elif kind == "bars_change":
        sid = spec["series"][0]
        full = ctx.fred(sid)
        meta = _meta(sid, full)
        chart["series"].append(transforms.period_change(full).since(start))
        chart_facts += facts.change_facts(full, meta)
        chart["units"], chart["decimals"] = meta["units"], 0
    elif kind == "indexed":
        windows = [ctx.fred(sid).since(start) for sid in spec["series"]]
        common = max(w.dates[0] for w in windows)
        for sid, window in zip(spec["series"], windows):
            window = window.since(common)
            rebased = transforms.rebase_to_100(window)
            chart["series"].append(rebased)
            meta = _meta(sid, window)
            chart_facts += facts.level_facts(ctx.fred(sid), meta)[:1]
            pct = rebased.latest_value - 100
            chart_facts.append({
                "key": f"{sid}.since_start",
                "claim": f"Since {fmt.fmt_date(window.dates[0])}, {meta['noun']} is {'up' if pct >= 0 else 'down'} {fmt.fmt_pct(abs(pct))}.",
                "value": f"{'up' if pct >= 0 else 'down'} {fmt.fmt_pct(abs(pct))}", "as_of": fmt.fmt_date(window.latest_date),
                "source_name": window.source_name, "source_url": window.source_url, "status": "calculated",
                "note": "", "series_id": sid, "trend": "up" if pct >= 0 else "down",
            })
        chart["units"], chart["decimals"] = "index", 0
    elif kind == "treasury":
        if spec["dataset"] == "debt":
            series = treasury.fetch_total_public_debt(start)
            meta = {"noun": "the U.S. national debt", "units": "usd_trillions", "freq": "daily", "decimals": 2}
        else:
            series = treasury.fetch_avg_interest_rate(start)
            meta = {"noun": "the average interest rate on U.S. marketable debt", "units": "percent", "freq": "monthly", "decimals": 2}
        ctx.raw[series.id] = series
        chart["series"].append(series)
        chart_facts += facts.level_facts(series, meta)
        chart["units"], chart["decimals"] = meta["units"], meta["decimals"]
    elif kind == "edgar":
        names = spec.get("tickers") or tickers
        if not names:
            raise ValueError("no company tickers for this chart")
        tags, label = (edgar.CAPEX_TAGS, "capital spending") if spec["concept"] == "capex" else (edgar.REVENUE_TAGS, "revenue")
        for ticker in names[:3]:
            try:
                series = edgar.fetch_annual_concept(ticker, tags, label, ctx.settings.get("SEC_CONTACT", ""))
            except FetchError as exc:
                ctx.warnings.append(str(exc))
                continue
            ctx.raw[series.id] = series
            chart_facts += facts.edgar_facts(series, ticker.upper(), label)
            recent = series.since(transforms.years_before(ctx.today, 8))
            recent.title = f"{ticker.upper()} {label}"
            chart["series"].append(recent)
        if not chart["series"]:
            raise FetchError("SEC EDGAR returned no usable annual figures")
        if not spec.get("tickers"):
            chart["title"] = f"{', '.join(n.upper() for n in names[:3])}: annual {label} from SEC filings"
        chart["units"], chart["decimals"] = "usd_billions", 1
    else:
        raise ValueError(f"unknown chart kind {kind}")

    chart["series"] = [s for s in chart["series"] if len(s) >= 2]
    if not chart["series"]:
        raise ValueError("not enough observations in the chart window")
    return chart, chart_facts


def _extra_series_chart(series_id: str, ctx: DataContext) -> tuple[dict, list[dict]]:
    """A chart for a FRED series the user typed in."""
    full = ctx.fred(series_id)
    meta = _meta(series_id, full)
    chart = {"id": f"custom_{series_id.lower()}", "kind": "lines", "title": full.title, "teaches": "",
             "series": [full.since(transforms.years_before(ctx.today, 10))], "units": meta["units"],
             "decimals": meta["decimals"], "recessions": _recessions(ctx, transforms.years_before(ctx.today, 10))}
    return chart, facts.level_facts(full, meta)


def _bls_cross_check(ctx: DataContext, all_facts: list[dict]) -> None:
    """Confirm BLS-produced numbers against the BLS API itself, where we can reach it."""
    wanted = {sid: catalog.SERIES[sid]["bls_id"] for sid in ctx.cache if catalog.SERIES.get(sid, {}).get("bls_id")}
    if not wanted:
        return
    try:
        result = bls.fetch_series(sorted(set(wanted.values())), ctx.today.year - 1, ctx.today.year,
                                  ctx.settings.get("BLS_API_KEY", ""))
    except FetchError as exc:
        ctx.warnings.append(f"BLS cross-check skipped ({exc}). The FRED copy of the BLS data was used.")
        return
    for sid, bls_id in wanted.items():
        direct, mirror = result.get(bls_id), ctx.cache[sid]
        if not direct:
            continue
        same_month = dict(zip(direct.dates, direct.values)).get(mirror.latest_date)
        if same_month is None:
            continue
        matches = abs(same_month - mirror.latest_value) < 0.005 * max(1.0, abs(mirror.latest_value))
        for fact in all_facts:
            if fact.get("series_id") == sid and fact["key"].endswith((".latest", ".yoy")):
                fact["note"] = (fact.get("note", "") + " " + (
                    f"Cross-checked against the BLS API ({bls.series_page(bls_id)}): matches."
                    if matches else
                    f"WARNING: the BLS API shows {same_month} for the same month ({bls.series_page(bls_id)}). Check before using."
                )).strip()


def gather(plan: dict, theme: dict, ctx: DataContext, charts_dir: Path,
           progress: Callable[[str], None] = lambda _msg: None) -> dict:
    """Fetch everything, draw the charts and number the facts."""
    theme_name = ctx.settings.get("CHART_THEME", "dark")
    chart_entries: list[dict] = []
    all_facts: list[dict] = []
    seen_keys: set[str] = set()

    def add_facts(new: list[dict], group: str) -> list[dict]:
        kept = []
        for fact in new:
            if fact["key"] in seen_keys:
                kept.append(next(f for f in all_facts if f["key"] == fact["key"]))
                continue
            seen_keys.add(fact["key"])
            fact["group"] = group
            all_facts.append(fact)
            kept.append(fact)
        return kept

    candidates = list(plan["charts"])
    backups = list(plan.get("backup_charts", []))
    jobs: list[tuple[str, Callable]] = [(cid, None) for cid in candidates]
    for sid in plan.get("extra_series", []):
        jobs.append((f"custom:{sid}", None))

    index = 0
    while index < len(jobs):
        chart_id = jobs[index][0]
        index += 1
        number = len(chart_entries) + 1
        try:
            if chart_id.startswith("custom:"):
                progress(f"Fetching FRED series {chart_id[7:]}")
                chart, new_facts = _extra_series_chart(chart_id[7:], ctx)
            else:
                progress(f"Fetching data for chart {number}: {catalog.CHARTS[chart_id]['title']}")
                chart, new_facts = build_chart(chart_id, catalog.CHARTS[chart_id], ctx, plan.get("tickers", []))
            files = charts.render_chart(chart, charts_dir, number, theme_name)
            spec_name = f"chart_{number:02d}_{chart['id']}.json"
            (charts_dir / spec_name).write_text(json.dumps(charts.chart_to_spec(chart)), encoding="utf-8")
        except (FetchError, ValueError) as exc:
            ctx.warnings.append(f"Chart skipped ({chart_id}): {exc}")
            if backups and len(chart_entries) + (len(jobs) - index) < 3:
                jobs.append((backups.pop(0), None))  # keep the package at three charts if we can
            continue
        kept = add_facts(new_facts, f"Chart {number}: {chart['title']}")
        last = max(s.dates[-1] for s in chart["series"])
        chart_entries.append({
            "n": number, "id": chart["id"], "title": chart["title"], "teaches": chart.get("teaches", ""),
            "kind": chart["kind"], "files": files, "spec_file": spec_name, "theme": theme_name,
            "series_ids": [s.id for s in chart["series"]],
            "series": [{"title": s.title, "source_name": s.source_name, "source_url": s.source_url} for s in chart["series"]],
            "data_through": fmt.fmt_date(last, chart["series"][0].frequency or "daily"),
            "fact_keys": [f["key"] for f in kept],
        })

    # --- the four "what it means for you" angles always get a real number
    progress("Fetching wallet numbers (mortgage, jobs, groceries, 401k)")
    wallet: dict[str, list[str]] = {}
    for angle, cfg in catalog.WALLET.items():
        keys: list[str] = []
        try:
            series = ctx.fred(cfg["series"])
            meta = _meta(cfg["series"], series)
            new = facts.yoy_facts(series, meta) if meta["units"] == "index" and angle == "groceries" else facts.level_facts(series, meta)
            keys += [f["key"] for f in add_facts(new, "Your wallet")]
            if angle == "mortgage":
                example = facts.mortgage_payment_fact(series, ctx.fred("MSPUS"))
                if example:
                    keys += [f["key"] for f in add_facts([example], "Your wallet")]
        except FetchError as exc:
            ctx.warnings.append(f"Wallet number skipped ({cfg['label']}): {exc}")
        wallet[angle] = keys

    # --- company filings from SEC EDGAR
    filings_out = []
    for ticker in plan.get("tickers", []):
        progress(f"Fetching SEC filings for {ticker}")
        contact = ctx.settings.get("SEC_CONTACT", "")
        try:
            cik = edgar.lookup_cik(ticker, contact)
            if cik is None:
                raise FetchError(f"SEC EDGAR: no CIK found for {ticker}")
            company = edgar.fetch_company(cik, contact)
            filings = edgar.recent_filings(company)
            add_facts(facts.filing_facts(ticker, company.get("name", ticker), filings), "Company filings (SEC EDGAR)")
            filings_out.append({"ticker": ticker, "name": company.get("name", ticker), "filings": filings})
            for tags, label in ((edgar.REVENUE_TAGS, "revenue"), (edgar.NET_INCOME_TAGS, "net income")):
                series = edgar.fetch_annual_concept(ticker, tags, label, contact)
                ctx.raw[series.id] = series
                add_facts(facts.edgar_facts(series, ticker, label), "Company filings (SEC EDGAR)")
        except FetchError as exc:
            ctx.warnings.append(f"SEC data skipped for {ticker}: {exc}")

    progress("Cross-checking BLS numbers")
    _bls_cross_check(ctx, all_facts)

    add_facts(facts.news_facts(theme.get("headlines", [])), "News coverage (verify before use)")
    facts.number_facts(all_facts)
    by_key = {f["key"]: f["id"] for f in all_facts}
    for entry in chart_entries:
        entry["fact_ids"] = [by_key[k] for k in entry.pop("fact_keys") if k in by_key]

    progress("Looking up release dates")
    watch_list = watch.build_watch_list(plan["releases"], ctx.settings.get("FRED_API_KEY", ""), ctx.today)

    return {
        "charts": chart_entries,
        "facts": all_facts,
        "wallet": {angle: [by_key[k] for k in keys if k in by_key] for angle, keys in wallet.items()},
        "filings": filings_out,
        "watch": watch_list,
        "warnings": ctx.warnings,
    }
