"""Shared test setup. Tests never touch the network: every outbound request goes through
vps.sources.http, and the `net` fixture replaces it with canned responses."""
from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vps.sources import http  # noqa: E402

TODAY = date(2026, 11, 17)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Each test gets its own projects/, reports/, cache and .env, and no real network."""
    for name in ("projects", "reports", "cache"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("VPS_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("VPS_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("VPS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("VPS_ENV_FILE", str(tmp_path / ".env"))
    monkeypatch.delenv("VPS_CACHE_TTL", raising=False)

    def no_network(*_args, **_kwargs):
        raise AssertionError("a test tried to use the real network")

    monkeypatch.setattr(http._session, "request", no_network)
    return tmp_path


def synthetic_csv(series_id: str, start: date = date(2000, 1, 3), step_days: int = 1,
                  base: float = 4.0, drift: float = 0.0002, monthly: bool = False) -> str:
    """Made-up but deterministic observations in FRED's CSV format. Test data only."""
    lines = [f"observation_date,{series_id}"]
    d, i = start, 0
    while d <= TODAY:
        value = base * (1 + drift * i) + 0.3 * math.sin(i / 37.0)
        lines.append(f"{d.isoformat()},{value:.3f}")
        i += 1
        if monthly:
            d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
        else:
            d += timedelta(days=step_days)
    return "\n".join(lines) + "\n"


MONTHLY = {"CPIAUCNS", "CPILFENS", "UNRATE", "PAYEMS", "CUSR0000SAF11", "USREC", "CES0500000003", "CUSR0000SEHA", "JTSJOL", "UMCSENT"}
QUARTERLY_AS_MONTHLY = {"MSPUS", "A191RL1Q225SBEA"}
BASES = {"MSPUS": 400000.0, "SP500": 5000.0, "PAYEMS": 150000.0, "CPIAUCNS": 250.0, "CPILFENS": 250.0,
         "CUSR0000SAF11": 250.0, "USREC": 0.0, "NASDAQCOM": 15000.0}


class FakeNet:
    """Stands in for http.request_text. Records every call."""

    def __init__(self):
        self.calls: list[tuple[str, dict | None]] = []
        self.fail_hosts: set[str] = set()
        self.overrides: dict[str, str] = {}

    def __call__(self, url, *, params=None, json_body=None, headers=None, **_kwargs):
        self.calls.append((url, params))
        host = url.split("/")[2]
        if host in self.fail_hosts:
            raise http.FetchError(f"{host}: blocked in this test")
        for needle, body in self.overrides.items():
            if needle in url or needle in json.dumps(params or {}):
                return body
        if "fredgraph.csv" in url:
            sid = params["id"]
            monthly = sid in MONTHLY or sid in QUARTERLY_AS_MONTHLY
            if sid == "USREC":
                return "observation_date,USREC\n" + "\n".join(
                    f"{y}-{m:02d}-01,{1 if (y, m) in ((2008, 6), (2008, 7), (2008, 8)) else 0}"
                    for y in range(2000, 2027) for m in range(1, 13)) + "\n"
            return synthetic_csv(sid, start=date(2000, 1, 1) if monthly else date(2000, 1, 3),
                                 step_days=1, base=BASES.get(sid, 4.0), monthly=monthly)
        if "api.bls.gov" in url:
            return json.dumps({"status": "REQUEST_NOT_PROCESSED", "message": ["daily threshold reached"], "Results": {}})
        raise http.FetchError(f"{host}: no canned response for {url}")


@pytest.fixture
def net(monkeypatch):
    fake = FakeNet()
    monkeypatch.setattr(http, "request_text", fake)
    # The source modules imported the functions by name, so patch those references too.
    from vps.sources import bls, edgar, fred, treasury

    def fake_json(url, **kwargs):
        return json.loads(fake(url, **kwargs))

    monkeypatch.setattr(fred, "request_text", fake)
    for module in (fred, bls, edgar, treasury):
        monkeypatch.setattr(module, "request_json", fake_json)
    return fake


SAMPLE_REPORT = {
    "date": "2026-11-16",
    "themes": [
        {"theme": "Mortgage rates climb as Treasury yields rise", "score": 90, "open_lane": True,
         "headlines": [{"title": "Mortgage rates hit 7.2%, highest this year", "link": "https://news.example/a"},
                       {"title": "Bond selloff deepens", "url": "https://news.example/b", "source": "Example Wire"}],
         "search_trends": ["mortgage rates today"],
         "competitor_videos": [{"title": "Mortgage Rates Are EXPLODING", "channel": "Rival", "views": "1.2M", "video_id": "abc123"}]},
        {"theme": "Low score theme", "score": 10, "headlines": ["Just a string headline"]},
    ],
    "tickers": ["NVDA", {"ticker": "msft"}],
    "emerging": ["term premium"],
    "competitor_outliers": [{"title": "Why Your Mortgage Just Got Worse", "channel": "Rival", "views": 2500000, "url": "https://youtu.be/x"}],
}


@pytest.fixture
def report_file(isolated):
    path = isolated / "reports" / "2026-11-16.json"
    path.write_text(json.dumps(SAMPLE_REPORT), encoding="utf-8")
    return path
