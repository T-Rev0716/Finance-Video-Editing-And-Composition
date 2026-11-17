"""SEC EDGAR: company filings and reported (XBRL) financial facts. No key needed.

The SEC asks automated tools to send a User-Agent that identifies them; set SEC_CONTACT
on the Settings page ("Your Name your@email.com") to follow their fair-access policy.
"""
from __future__ import annotations

from datetime import date, datetime

from .http import FetchError, request_json
from .models import Series

# Ticker -> CIK for names that come up most in finance/AI news. Each one was checked
# against data.sec.gov/submissions. Anything else is looked up from the SEC's ticker file.
KNOWN_CIKS: dict[str, int] = {
    "AAPL": 320193, "MSFT": 789019, "NVDA": 1045810, "GOOGL": 1652044, "GOOG": 1652044,
    "AMZN": 1018724, "META": 1326801, "TSLA": 1318605, "AMD": 2488, "AVGO": 1730168,
    "ORCL": 1341439, "PLTR": 1321655, "INTC": 50863, "MU": 723125, "NFLX": 1065280,
    "JPM": 19617, "BAC": 70858, "WFC": 72971, "GS": 886982, "BRK-B": 1067983,
    "WMT": 104169, "COST": 909832, "CVX": 93410, "COIN": 1679788,
}

REVENUE_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]
CAPEX_TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]
NET_INCOME_TAGS = ["NetIncomeLoss"]


def _headers(contact: str = "") -> dict:
    agent = f"VideoPrepStudio {contact}".strip() if contact else "VideoPrepStudio/1.0 (local research tool)"
    return {"User-Agent": agent, "Accept-Encoding": "gzip, deflate"}


def lookup_cik(ticker: str, contact: str = "") -> int | None:
    ticker = ticker.strip().upper().replace(".", "-")
    if ticker in KNOWN_CIKS:
        return KNOWN_CIKS[ticker]
    try:
        table = request_json("https://www.sec.gov/files/company_tickers.json", headers=_headers(contact))
    except FetchError:
        return None
    for row in table.values():
        if str(row.get("ticker", "")).upper() == ticker:
            return int(row["cik_str"])
    return None


def fetch_company(cik: int, contact: str = "") -> dict:
    return request_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=_headers(contact))


def recent_filings(company: dict, forms=("10-K", "10-Q", "8-K"), limit: int = 4) -> list[dict]:
    """Latest filings of the given types, with a direct link to each document."""
    recent = company.get("filings", {}).get("recent", {})
    cik = int(company.get("cik", 0))
    out: list[dict] = []
    for form, filed, accession, doc, report in zip(
        recent.get("form", []), recent.get("filingDate", []), recent.get("accessionNumber", []),
        recent.get("primaryDocument", []), recent.get("reportDate", []),
    ):
        if form not in forms:
            continue
        out.append({
            "form": form, "filed": filed, "period": report,
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{doc}",
        })
        if len(out) >= limit:
            break
    return out


def annual_values(concept: dict) -> list[dict]:
    """Full-fiscal-year values from 10-K filings, oldest first, one per fiscal year end.

    A concept lists the same period many times (each later filing repeats prior years),
    so we keep the most recently filed value for each period end.
    """
    best: dict[str, dict] = {}
    for row in concept.get("units", {}).get("USD", []):
        if row.get("form") not in ("10-K", "10-K/A") or "start" not in row or "end" not in row:
            continue
        try:
            start = datetime.strptime(row["start"], "%Y-%m-%d").date()
            end = datetime.strptime(row["end"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if not 350 <= (end - start).days <= 380:
            continue
        current = best.get(row["end"])
        if current is None or row.get("filed", "") > current.get("filed", ""):
            best[row["end"]] = {"start": start, "end": end, "value": float(row["val"]),
                                "filed": row.get("filed", ""), "accn": row.get("accn", "")}
    return [best[k] for k in sorted(best)]


def fetch_annual_concept(ticker: str, tags: list[str], label: str, contact: str = "") -> Series:
    """Annual values for the first tag the company actually reports, in billions of dollars."""
    cik = lookup_cik(ticker, contact)
    if cik is None:
        raise FetchError(f"SEC EDGAR: no CIK found for ticker {ticker}")
    best_rows: list[dict] = []
    best_tag = ""
    for tag in tags:
        try:
            concept = request_json(
                f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json",
                headers=_headers(contact),
            )
        except FetchError:
            continue
        rows = annual_values(concept)
        # Companies change tags over time; prefer whichever one has the most recent year.
        if rows and (not best_rows or rows[-1]["end"] > best_rows[-1]["end"]):
            best_rows, best_tag = rows, tag
    if not best_rows:
        raise FetchError(f"SEC EDGAR: {ticker} reports none of {', '.join(tags)}")
    return Series(
        id=f"{ticker.upper()}_{label.upper().replace(' ', '_')}",
        title=f"{ticker.upper()} {label} (fiscal year)", units="usd_billions",
        dates=[r["end"] for r in best_rows], values=[r["value"] / 1e9 for r in best_rows],
        source_name=f"SEC EDGAR, {ticker.upper()} 10-K filings (us-gaap:{best_tag})",
        source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}&type=10-K",
        frequency="annual", fetched_via="sec_edgar",
    )
