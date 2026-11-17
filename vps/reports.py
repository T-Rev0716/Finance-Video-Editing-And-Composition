"""Read the daily JSON reports from reports/ and smooth over small format differences."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from . import config

_DATE_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _first(d: dict, *keys, default=None):
    for key in keys:
        if isinstance(d, dict) and d.get(key) not in (None, ""):
            return d[key]
    return default


def parse_views(value) -> int | None:
    """'1.2M', '340K', '12,345' or 12345 -> int. None when unknown."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower().replace(",", "").replace("views", "").strip()
    match = re.fullmatch(r"([\d.]+)\s*([kmb]?)", text)
    if not match:
        return None
    try:
        number = float(match.group(1))
    except ValueError:
        return None
    return int(number * {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[match.group(2)])


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _headline(item) -> dict | None:
    if isinstance(item, str):
        return {"title": item.strip(), "url": "", "source": ""} if item.strip() else None
    if not isinstance(item, dict):
        return None
    title = _first(item, "title", "headline", "text", "name", default="")
    url = _first(item, "link", "url", "href", default="")
    if not title:
        return None
    return {"title": str(title).strip(), "url": str(url).strip(),
            "source": str(_first(item, "source", "publisher", "outlet", default="") or _domain(str(url)))}


def _video(item) -> dict | None:
    if isinstance(item, str):
        return {"title": item.strip(), "channel": "", "views": None, "url": ""} if item.strip() else None
    if not isinstance(item, dict):
        return None
    title = _first(item, "title", "name", default="")
    if not title:
        return None
    url = _first(item, "url", "link", "href", default="")
    video_id = _first(item, "video_id", "videoId", "id")
    if not url and video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"
    return {
        "title": str(title).strip(),
        "channel": str(_first(item, "channel", "channel_title", "channelTitle", "author", default="")),
        "views": parse_views(_first(item, "views", "view_count", "viewCount")),
        "url": str(url),
        "multiplier": _first(item, "multiplier", "outlier_score", "ratio", "outlier"),
    }


def _strings(items) -> list[str]:
    out = []
    for item in items or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            value = _first(item, "phrase", "term", "query", "keyword", "ticker", "symbol", "name", "text")
            if value:
                out.append(str(value))
    return out


def normalize_report(raw: dict, file_name: str = "") -> dict:
    themes = []
    for item in raw.get("themes") or []:
        if not isinstance(item, dict):
            continue
        name = _first(item, "theme", "name", "title", "topic", default="")
        if not name:
            continue
        themes.append({
            "theme": str(name),
            "score": _first(item, "score", "rank_score", "total_score", default=0) or 0,
            "headlines": [h for h in map(_headline, item.get("headlines") or []) if h],
            "search_trends": _strings(_first(item, "search_trends", "trends", "searches", default=[])),
            "competitor_videos": [v for v in map(_video, _first(item, "competitor_videos", "videos", default=[]) or []) if v],
            "open_lane": bool(_first(item, "open_lane", "openLane", default=False)),
            "tickers": [t.upper() for t in _strings(item.get("tickers"))],
        })
    try:
        themes.sort(key=lambda t: float(t["score"]), reverse=True)
    except (TypeError, ValueError):
        pass
    date_match = _DATE_IN_NAME.search(file_name)
    return {
        "file": file_name,
        "date": str(_first(raw, "date", "report_date", "generated_at", default="") or (date_match.group(1) if date_match else "")),
        "themes": themes,
        "tickers": [t.upper() for t in _strings(raw.get("tickers"))],
        "emerging": _strings(raw.get("emerging")),
        "competitor_outliers": [v for v in map(_video, raw.get("competitor_outliers") or []) if v],
        "note": str(raw.get("_note", "")),
    }


def list_report_files() -> list[Path]:
    """Newest first: by the date in the file name when there is one, else by modified time."""
    folder = config.reports_dir()
    if not folder.exists():
        return []

    def sort_key(path: Path):
        match = _DATE_IN_NAME.search(path.name)
        return (match.group(1) if match else "", path.stat().st_mtime)

    return sorted(folder.glob("*.json"), key=sort_key, reverse=True)


def load_report(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: expected a JSON object at the top level")
    return normalize_report(raw, path.name)


def latest_report() -> dict | None:
    for path in list_report_files():
        try:
            return load_report(path)
        except (ValueError, OSError):
            continue  # skip a broken file and try the next newest
    return None


class RadarImportError(ValueError):
    """Shown to the user."""


def import_latest_radar(source_dir: str) -> dict:
    """Copy the newest report from the topic-radar folder into reports/."""
    import shutil
    source = Path((source_dir or "").strip().strip('"')).expanduser()
    if not source.is_dir():
        raise RadarImportError(f"The topic radar folder was not found: {source}. Set it in Settings.")

    def sort_key(path: Path):
        match = _DATE_IN_NAME.search(path.name)
        return (match.group(1) if match else "", path.stat().st_mtime)

    candidates = sorted(source.glob("*.json"), key=sort_key, reverse=True)
    if not candidates:
        raise RadarImportError(f"No .json reports in {source}.")
    newest = candidates[0]
    try:
        report = load_report(newest)
    except (ValueError, OSError) as exc:
        raise RadarImportError(f"{newest.name} could not be read as a report: {exc}") from None
    folder = config.reports_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / newest.name
    if target.exists() and target.read_bytes() == newest.read_bytes():
        status = "already_current"
    else:
        shutil.copyfile(newest, target)
        status = "imported"
    return {"status": status, "file": newest.name, "themes": len(report["themes"]), "date": report["date"], "source": str(source)}
