"""Decide which data tells the story for a topic. Keyword rules only - no AI, no numbers."""
from __future__ import annotations

import re

from . import catalog

COMPANY_NAMES = {
    "nvidia": "NVDA", "microsoft": "MSFT", "apple": "AAPL", "amazon": "AMZN", "alphabet": "GOOGL",
    "google": "GOOGL", "meta": "META", "facebook": "META", "tesla": "TSLA", "broadcom": "AVGO",
    "oracle": "ORCL", "palantir": "PLTR", "intel": "INTC", "micron": "MU", "netflix": "NFLX",
    "jpmorgan": "JPM", "bank of america": "BAC", "wells fargo": "WFC", "goldman sachs": "GS",
    "walmart": "WMT", "costco": "COST", "chevron": "CVX", "coinbase": "COIN", "amd": "AMD",
}
MAX_CHARTS = 6
MIN_CHARTS = 3


def _count(keyword: str, text: str) -> int:
    return len(re.findall(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text))


def score_categories(topic: str, context: str = "") -> list[tuple[str, int]]:
    """Category scores, best first. The topic itself counts 3x what the headlines do."""
    topic_l, context_l = topic.lower(), context.lower()
    scores: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for name, cat in catalog.CATEGORIES.items():
        score = sum(3 * _count(k, topic_l) + min(_count(k, context_l), 3) for k in cat["keywords"])
        if score:
            scores[name] = score
        positions = [m.start() for k in cat["keywords"]
                     for m in re.finditer(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", topic_l)]
        if positions:
            first_seen[name] = min(positions)
    if first_seen:
        # Whatever the topic names first is what the video is about, however often the
        # headlines mention something else.
        scores[min(first_seen, key=first_seen.get)] += 1000
    return sorted(scores.items(), key=lambda pair: -pair[1])


def find_tickers(topic: str, context: str = "", report_tickers: list[str] | None = None) -> list[str]:
    """Companies named in the topic or its headlines (max 3), for SEC filing lookups."""
    text = f"{topic} {context}"
    lower = text.lower()
    found: list[str] = []
    for name, ticker in COMPANY_NAMES.items():
        if _count(name, lower) and ticker not in found:
            found.append(ticker)
    known = set(COMPANY_NAMES.values()) | {t.upper() for t in (report_tickers or [])}
    for symbol in re.findall(r"(?<![A-Za-z$])\$?([A-Z]{2,5})(?![A-Za-z])", text):
        if symbol in known and symbol not in found:
            found.append(symbol)
    return found[:3]


def plan_topic(topic: str, theme: dict | None = None, report_tickers: list[str] | None = None,
               extra_series: list[str] | None = None) -> dict:
    """Pick categories, an ordered chart list (3-6) and the releases to watch."""
    theme = theme or {}
    context = " ".join([h.get("title", "") for h in theme.get("headlines", [])] + theme.get("search_trends", []))
    ranked = score_categories(topic, context)
    names = [name for name, _ in ranked[:3]]
    tickers = list(dict.fromkeys(find_tickers(topic, context, report_tickers) + [t for t in theme.get("tickers", [])][:3]))[:3]

    charts: list[str] = []

    def add(chart_id: str) -> None:
        if chart_id not in charts and len(charts) < MAX_CHARTS:
            charts.append(chart_id)

    if names:
        primary = catalog.CATEGORIES[names[0]]["charts"]
        for chart_id in primary[: 4 if len(names) > 1 else MAX_CHARTS]:
            add(chart_id)
        for other in names[1:]:
            for chart_id in [c for c in catalog.CATEGORIES[other]["charts"] if c not in charts][:2]:
                add(chart_id)
    if tickers and "ticker_revenue" not in charts:
        if len(charts) >= MAX_CHARTS:
            charts.pop()
        add("ticker_revenue")
    if not tickers and "ticker_revenue" in charts:
        charts.remove("ticker_revenue")
    backups = [c for name in names for c in catalog.CATEGORIES[name]["charts"]] + catalog.DEFAULT_CHARTS
    backups = [c for c in dict.fromkeys(backups) if c not in charts and c != "ticker_revenue"]
    while len(charts) < MIN_CHARTS and backups:
        add(backups.pop(0))

    releases: list[str] = []
    for name in names or ["fed"]:
        for release in catalog.CATEGORIES[name]["releases"]:
            if release not in releases:
                releases.append(release)

    primary_name = names[0] if names else ""
    return {
        "categories": names,
        "primary": primary_name,
        "label": catalog.CATEGORIES[primary_name]["label"] if primary_name else "",
        "plural": catalog.CATEGORIES[primary_name]["plural"] if primary_name else False,
        "lead_series": catalog.CATEGORIES[primary_name]["lead_series"] if primary_name else "",
        "charts": charts,
        "backup_charts": backups,
        "releases": releases[:5],
        "tickers": tickers,
        "extra_series": [s.strip().upper() for s in (extra_series or []) if s.strip()][:4],
    }
