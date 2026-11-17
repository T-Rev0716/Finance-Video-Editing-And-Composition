"""U.S. Bureau of Labor Statistics public API (v2). Works without a key (small daily limit)."""
from __future__ import annotations

from datetime import date

from .http import FetchError, request_json
from .models import Series

API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def series_page(series_id: str) -> str:
    return f"https://data.bls.gov/timeseries/{series_id}"


def parse_bls_response(payload: dict) -> dict[str, tuple[list[date], list[float]]]:
    """Return {series_id: (dates, values)} sorted oldest-first. Monthly periods only."""
    if payload.get("status") != "REQUEST_SUCCEEDED":
        message = "; ".join(payload.get("message", [])) or str(payload.get("status"))
        raise FetchError(f"api.bls.gov: {message}")
    out: dict[str, tuple[list[date], list[float]]] = {}
    for item in payload.get("Results", {}).get("series", []):
        rows: list[tuple[date, float]] = []
        for obs in item.get("data", []):
            period = obs.get("period", "")
            if not (period.startswith("M") and period[1:].isdigit()) or period == "M13":
                continue
            try:
                rows.append((date(int(obs["year"]), int(period[1:]), 1), float(obs["value"])))
            except (ValueError, KeyError):
                continue  # BLS uses "-" when a month was not published
        rows.sort()
        out[item.get("seriesID", "")] = ([d for d, _ in rows], [v for _, v in rows])
    return out


def fetch_series(series_ids: list[str], start_year: int, end_year: int, api_key: str = "") -> dict[str, Series]:
    body: dict = {"seriesid": series_ids, "startyear": str(start_year), "endyear": str(end_year)}
    if api_key:
        body["registrationkey"] = api_key
    parsed = parse_bls_response(request_json(API_URL, json_body=body))
    result: dict[str, Series] = {}
    for sid, (dates, values) in parsed.items():
        if values:
            result[sid] = Series(
                id=sid, title=sid, units="", dates=dates, values=values,
                source_name="U.S. Bureau of Labor Statistics", source_url=series_page(sid),
                frequency="monthly", fetched_via="bls_api",
            )
    return result
