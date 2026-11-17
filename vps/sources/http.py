"""One place for outbound HTTP: retries, a short on-disk cache, clear errors."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import requests

from .. import config


class FetchError(Exception):
    """A data source could not be reached or returned something unusable."""


def cache_ttl() -> float:
    """Seconds a saved response stays fresh. Data here changes at most daily, so one hour
    keeps re-runs fast. Set VPS_CACHE_TTL (seconds) to work offline from the last fetch."""
    try:
        return float(os.environ.get("VPS_CACHE_TTL", 3600))
    except ValueError:
        return 3600.0


_session = requests.Session()


def _cache_file(method: str, url: str, params, body) -> Path:
    # The key is hashed, so API keys in query strings never appear in file names.
    raw = json.dumps([method, url, params, body], sort_keys=True, default=str)
    return config.cache_dir() / (hashlib.sha256(raw.encode()).hexdigest()[:32] + ".txt")


def request_text(
    url: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
    headers: dict | None = None,
    timeout: float = 30,
    retries: int = 3,
    use_cache: bool = True,
) -> str:
    """GET (or POST when json_body is given) and return the body as text."""
    method = "POST" if json_body is not None else "GET"
    cache_file = _cache_file(method, url, params, json_body)
    if use_cache and cache_file.exists() and time.time() - cache_file.stat().st_mtime < cache_ttl():
        return cache_file.read_text(encoding="utf-8")

    last_error = "unknown error"
    for attempt in range(retries):
        try:
            response = _session.request(
                method, url, params=params, json=json_body, headers=headers, timeout=timeout
            )
        except requests.exceptions.ProxyError:
            # A proxy or firewall refused the connection; asking again will not change that.
            last_error = "blocked by a proxy or firewall on this network"
            break
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}"
        else:
            if response.status_code == 200:
                if use_cache:
                    cache_file.write_text(response.text, encoding="utf-8")
                return response.text
            last_error = f"HTTP {response.status_code}"
            if response.status_code in (400, 401, 403, 404):
                break  # asking again will not change the answer
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    host = url.split("/")[2] if "//" in url else url
    raise FetchError(f"{host}: {last_error}")


def request_json(url: str, **kwargs) -> dict:
    text = request_text(url, **kwargs)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise FetchError(f"{url.split('/')[2]}: response was not JSON") from exc
