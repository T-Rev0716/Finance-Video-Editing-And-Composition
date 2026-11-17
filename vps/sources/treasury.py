"""U.S. Treasury Fiscal Data API (no key needed)."""
from __future__ import annotations

from datetime import date, datetime

from .http import FetchError, request_json
from .models import Series

BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
DEBT_PAGE = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"
RATES_PAGE = "https://fiscaldata.treasury.gov/datasets/average-interest-rates-treasury-securities/"


def parse_rows(payload: dict, date_field: str, value_field: str) -> tuple[list[date], list[float]]:
    if "data" not in payload:
        raise FetchError("api.fiscaldata.treasury.gov: " + str(payload.get("message", "no data in response")))
    rows: list[tuple[date, float]] = []
    for row in payload["data"]:
        try:
            rows.append((datetime.strptime(row[date_field], "%Y-%m-%d").date(), float(row[value_field])))
        except (ValueError, KeyError, TypeError):
            continue  # Treasury uses the string "null" for gaps
    rows.sort()
    return [d for d, _ in rows], [v for _, v in rows]


def fetch_total_public_debt(start: date) -> Series:
    """Total public debt outstanding, daily, in trillions of dollars."""
    payload = request_json(
        f"{BASE}/v2/accounting/od/debt_to_penny",
        params={
            "fields": "record_date,tot_pub_debt_out_amt",
            "filter": f"record_date:gte:{start.isoformat()}",
            "sort": "record_date",
            "page[size]": 10000,
        },
    )
    dates, values = parse_rows(payload, "record_date", "tot_pub_debt_out_amt")
    if not values:
        raise FetchError("Treasury debt_to_penny returned no rows")
    return Series(
        id="TREASURY_DEBT", title="U.S. national debt (total public debt outstanding)",
        units="usd_trillions", dates=dates, values=[v / 1e12 for v in values],
        source_name="U.S. Treasury, Fiscal Data (Debt to the Penny)", source_url=DEBT_PAGE,
        frequency="daily", fetched_via="treasury_api",
    )


def fetch_avg_interest_rate(start: date, security: str = "Total Marketable") -> Series:
    """Average interest rate the Treasury pays on its marketable debt, monthly."""
    payload = request_json(
        f"{BASE}/v2/accounting/od/avg_interest_rates",
        params={
            "fields": "record_date,security_desc,avg_interest_rate_amt",
            "filter": f"record_date:gte:{start.isoformat()},security_desc:eq:{security}",
            "sort": "record_date",
            "page[size]": 10000,
        },
    )
    dates, values = parse_rows(payload, "record_date", "avg_interest_rate_amt")
    if not values:
        raise FetchError("Treasury avg_interest_rates returned no rows")
    return Series(
        id="TREASURY_AVG_RATE", title="Average interest rate on U.S. marketable debt",
        units="percent", dates=dates, values=values,
        source_name="U.S. Treasury, Fiscal Data (Average Interest Rates)", source_url=RATES_PAGE,
        frequency="monthly", fetched_via="treasury_api",
    )
