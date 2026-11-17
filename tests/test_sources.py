"""Data-fetch functions: parsing, fallbacks and failure handling (no real network)."""
from __future__ import annotations

import json
from datetime import date

import pytest
import requests

from vps.sources import bls, edgar, fred, http, treasury
from vps.sources.http import FetchError


# ---------- FRED ----------
def test_parse_fredgraph_csv_skips_missing_values():
    text = "observation_date,DGS10\n2026-11-10,5.10\n2026-11-11,.\n2026-11-12,\n2026-11-13,5.15\n"
    dates, values = fred.parse_fredgraph_csv(text)
    assert dates == [date(2026, 11, 10), date(2026, 11, 13)]
    assert values == [5.10, 5.15]


def test_parse_fredgraph_csv_rejects_html_error_page():
    with pytest.raises(FetchError):
        fred.parse_fredgraph_csv("<!DOCTYPE html><html>Not found</html>")


def test_parse_observations_json_skips_dots_and_reports_api_errors():
    payload = {"observations": [{"date": "2026-01-01", "value": "3.5"}, {"date": "2026-02-01", "value": "."}]}
    assert fred.parse_observations_json(payload) == ([date(2026, 1, 1)], [3.5])
    with pytest.raises(FetchError, match="Bad Request"):
        fred.parse_observations_json({"error_code": 400, "error_message": "Bad Request. api_key invalid"})


def test_fetch_series_without_key_uses_public_csv(net):
    net.overrides["DGS10"] = "observation_date,DGS10\n2026-11-12,5.10\n2026-11-13,5.15\n"
    series = fred.fetch_series("dgs10", title="10-year Treasury yield", units="percent", source_org="Federal Reserve Board")
    assert series.fetched_via == "fred_csv"
    assert (series.latest_date, series.latest_value) == (date(2026, 11, 13), 5.15)
    assert series.source_url == "https://fred.stlouisfed.org/series/DGS10"
    assert "Federal Reserve Board" in series.source_name
    assert all("api.stlouisfed.org" not in url for url, _ in net.calls)


def test_fetch_series_with_key_uses_api_and_reads_metadata(net):
    net.overrides["series/observations"] = json.dumps({"observations": [{"date": "2026-10-01", "value": "4.1"}, {"date": "2026-11-01", "value": "4.2"}]})
    net.overrides["/fred/series"] = json.dumps({"seriess": [{"title": "Unemployment Rate", "units": "Percent", "frequency": "Monthly"}]})
    series = fred.fetch_series("UNRATE", api_key="k" * 32)
    assert series.fetched_via == "fred_api"
    assert series.title == "Unemployment Rate" and series.frequency == "monthly"
    assert series.latest_value == 4.2


def test_fetch_series_falls_back_to_csv_when_api_rejects_key(net):
    net.overrides["series/observations"] = json.dumps({"error_code": 400, "error_message": "Bad Request. api_key invalid"})
    net.overrides["fredgraph.csv"] = "observation_date,DGS10\n2026-11-13,5.15\n2026-11-14,5.16\n"
    series = fred.fetch_series("DGS10", api_key="bad")
    assert series.fetched_via == "fred_csv" and series.latest_value == 5.16
    assert any("FRED API failed" in note for note in series.notes)


def test_fetch_series_with_no_observations_raises(net):
    net.overrides["fredgraph.csv"] = "observation_date,EMPTY\n"
    with pytest.raises(FetchError, match="no observations"):
        fred.fetch_series("EMPTY")


def test_next_release_date_picks_the_nearest_future_date(net):
    net.overrides["release/dates"] = json.dumps({"release_dates": [
        {"date": "2027-01-13"}, {"date": "2026-12-10"}, {"date": "2026-11-12"}, {"date": "bad"}]})
    assert fred.fetch_next_release_date(10, "k" * 32, today=date(2026, 11, 17)) == date(2026, 12, 10)
    assert fred.fetch_next_release_date(10, "", today=date(2026, 11, 17)) is None  # no key, no date - never guessed


# ---------- BLS ----------
def test_parse_bls_response_sorts_and_skips_unpublished_months():
    payload = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"seriesID": "CUUR0000SA0", "data": [
        {"year": "2026", "period": "M10", "value": "337.511"},
        {"year": "2026", "period": "M09", "value": "336.9"},
        {"year": "2025", "period": "M10", "value": "-"},
        {"year": "2025", "period": "M13", "value": "330.0"},
    ]}]}}
    dates, values = bls.parse_bls_response(payload)["CUUR0000SA0"]
    assert dates == [date(2026, 9, 1), date(2026, 10, 1)]
    assert values == [336.9, 337.511]


def test_bls_rate_limit_message_becomes_a_fetch_error():
    with pytest.raises(FetchError, match="daily threshold"):
        bls.parse_bls_response({"status": "REQUEST_NOT_PROCESSED", "message": ["daily threshold reached"], "Results": {}})


# ---------- Treasury ----------
def test_treasury_debt_is_converted_to_trillions(net):
    net.overrides["debt_to_penny"] = json.dumps({"data": [
        {"record_date": "2026-11-13", "tot_pub_debt_out_amt": "40616678827092.07"},
        {"record_date": "2026-11-12", "tot_pub_debt_out_amt": "40608506856903.25"},
        {"record_date": "2026-11-11", "tot_pub_debt_out_amt": "null"},
    ]})
    series = treasury.fetch_total_public_debt(date(2026, 11, 1))
    assert series.dates == [date(2026, 11, 12), date(2026, 11, 13)]
    assert round(series.latest_value, 3) == 40.617
    assert series.units == "usd_trillions" and "Treasury" in series.source_name


def test_treasury_error_payload_raises(net):
    net.overrides["debt_to_penny"] = json.dumps({"error": "Invalid Query Param", "message": "bad filter"})
    with pytest.raises(FetchError, match="bad filter"):
        treasury.fetch_total_public_debt(date(2026, 11, 1))


# ---------- SEC EDGAR ----------
def test_annual_values_keeps_full_years_and_latest_restatement():
    concept = {"units": {"USD": [
        {"start": "2024-07-01", "end": "2025-06-30", "val": 60e9, "form": "10-K", "filed": "2025-07-30"},
        {"start": "2024-07-01", "end": "2025-06-30", "val": 64.6e9, "form": "10-K", "filed": "2026-07-29"},  # restated
        {"start": "2025-07-01", "end": "2026-06-30", "val": 115.9e9, "form": "10-K", "filed": "2026-07-29"},
        {"start": "2026-04-01", "end": "2026-06-30", "val": 30e9, "form": "10-K", "filed": "2026-07-29"},  # one quarter
        {"start": "2025-07-01", "end": "2026-03-31", "val": 80e9, "form": "10-Q", "filed": "2026-04-25"},  # year to date
    ]}}
    rows = edgar.annual_values(concept)
    assert [(r["end"].isoformat(), r["value"]) for r in rows] == [("2025-06-30", 64.6e9), ("2026-06-30", 115.9e9)]


def test_recent_filings_builds_document_links():
    company = {"cik": "1045810", "filings": {"recent": {
        "form": ["4", "8-K", "10-Q"], "filingDate": ["2026-11-14", "2026-11-12", "2026-08-27"],
        "accessionNumber": ["0001-26-1", "0001045810-26-000082", "0001045810-26-000070"],
        "primaryDocument": ["x.xml", "nvda-20261111.htm", "nvda-20260727.htm"], "reportDate": ["", "2026-11-11", "2026-07-27"]}}}
    filings = edgar.recent_filings(company)
    assert [f["form"] for f in filings] == ["8-K", "10-Q"]
    assert filings[0]["url"] == "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000082/nvda-20261111.htm"


def test_lookup_cik_known_and_unknown(net):
    assert edgar.lookup_cik("nvda") == 1045810
    net.fail_hosts.add("www.sec.gov")
    assert edgar.lookup_cik("ZZZZ") is None  # unknown ticker and SEC unreachable: None, not a guess


# ---------- HTTP layer ----------
class _Response:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


def test_http_caches_successful_responses(monkeypatch):
    calls = []
    monkeypatch.setattr(http._session, "request", lambda *a, **k: calls.append(1) or _Response(200, "hello"))
    assert http.request_text("https://example.test/x") == "hello"
    assert http.request_text("https://example.test/x") == "hello"
    assert len(calls) == 1


def test_http_does_not_retry_a_404(monkeypatch):
    calls = []
    monkeypatch.setattr(http._session, "request", lambda *a, **k: calls.append(1) or _Response(404))
    with pytest.raises(FetchError, match="HTTP 404"):
        http.request_text("https://example.test/missing")
    assert len(calls) == 1


def test_http_retries_server_errors_then_gives_up(monkeypatch):
    calls = []
    monkeypatch.setattr(http._session, "request", lambda *a, **k: calls.append(1) or _Response(503))
    monkeypatch.setattr(http.time, "sleep", lambda _s: None)
    with pytest.raises(FetchError, match="HTTP 503"):
        http.request_text("https://example.test/flaky")
    assert len(calls) == 3


def test_http_proxy_block_is_reported_without_retrying(monkeypatch):
    calls = []

    def blocked(*_a, **_k):
        calls.append(1)
        raise requests.exceptions.ProxyError("403 Forbidden")

    monkeypatch.setattr(http._session, "request", blocked)
    with pytest.raises(FetchError, match="blocked by a proxy"):
        http.request_text("https://example.test/x")
    assert len(calls) == 1
