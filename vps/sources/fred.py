"""FRED (Federal Reserve Bank of St. Louis).

With an API key we use the official API (which also gives series metadata and upcoming
release dates). Without one we fall back to FRED's public CSV download - same numbers.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime

from .http import FetchError, request_json, request_text
from .models import Series

API_BASE = "https://api.stlouisfed.org/fred"
CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def series_page(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/series/{series_id}"


def parse_fredgraph_csv(text: str) -> tuple[list[date], list[float]]:
    """Parse FRED's CSV download. Missing observations (blank or '.') are skipped."""
    dates: list[date] = []
    values: list[float] = []
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header or len(header) < 2 or "date" not in header[0].lower():
        raise FetchError("fred.stlouisfed.org: unexpected CSV format")
    for row in reader:
        if len(row) < 2:
            continue
        raw = row[1].strip()
        if raw in ("", "."):
            continue
        try:
            dates.append(datetime.strptime(row[0].strip(), "%Y-%m-%d").date())
            values.append(float(raw))
        except ValueError:
            continue
    return dates, values


def parse_observations_json(payload: dict) -> tuple[list[date], list[float]]:
    """Parse the API's series/observations response."""
    if "observations" not in payload:
        raise FetchError("api.stlouisfed.org: " + str(payload.get("error_message", "no observations in response")))
    dates: list[date] = []
    values: list[float] = []
    for obs in payload["observations"]:
        raw = str(obs.get("value", "")).strip()
        if raw in ("", "."):
            continue
        try:
            dates.append(datetime.strptime(obs["date"], "%Y-%m-%d").date())
            values.append(float(raw))
        except (ValueError, KeyError):
            continue
    return dates, values


def fetch_series(
    series_id: str,
    *,
    title: str = "",
    units: str = "",
    source_org: str = "",
    frequency: str = "",
    start: date | None = None,
    api_key: str = "",
) -> Series:
    """Fetch one series. Tries the API when a key is set, then the keyless CSV."""
    series_id = series_id.strip().upper()
    notes: list[str] = []
    dates: list[date] = []
    values: list[float] = []
    via = ""

    if api_key:
        try:
            params = {"series_id": series_id, "api_key": api_key, "file_type": "json"}
            if start:
                params["observation_start"] = start.isoformat()
            dates, values = parse_observations_json(request_json(f"{API_BASE}/series/observations", params=params))
            via = "fred_api"
            if not title:
                meta = request_json(
                    f"{API_BASE}/series", params={"series_id": series_id, "api_key": api_key, "file_type": "json"}
                ).get("seriess", [{}])[0]
                title = meta.get("title", "")
                units = units or meta.get("units", "")
                frequency = frequency or meta.get("frequency", "").lower()
        except FetchError as exc:
            notes.append(f"FRED API failed ({exc}); used the public CSV download instead.")

    if not via:
        params = {"id": series_id}
        if start:
            params["cosd"] = start.isoformat()
        dates, values = parse_fredgraph_csv(request_text(CSV_URL, params=params))
        via = "fred_csv"

    if not values:
        raise FetchError(f"FRED series {series_id} returned no observations")

    credit = f"FRED ({source_org})" if source_org else "FRED, Federal Reserve Bank of St. Louis"
    return Series(
        id=series_id, title=title or series_id, units=units, dates=dates, values=values,
        source_name=credit, source_url=series_page(series_id), frequency=frequency,
        fetched_via=via, notes=notes,
    )


def fetch_next_release_date(release_id: int, api_key: str, today: date | None = None) -> date | None:
    """Next scheduled date for a FRED release (needs an API key). None if unknown."""
    if not api_key:
        return None
    today = today or date.today()
    payload = request_json(
        f"{API_BASE}/release/dates",
        params={
            "release_id": release_id, "api_key": api_key, "file_type": "json",
            "include_release_dates_with_no_data": "true", "sort_order": "desc", "limit": 60,
        },
    )
    upcoming = []
    for item in payload.get("release_dates", []):
        try:
            d = datetime.strptime(item["date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        if d >= today:
            upcoming.append(d)
    return min(upcoming) if upcoming else None
