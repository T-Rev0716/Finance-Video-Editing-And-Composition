"""'What to watch next': upcoming release dates. Dates are fetched or left blank - never guessed."""
from __future__ import annotations

import json
from datetime import date, datetime

from . import catalog, config, fmt
from .sources import fred
from .sources.http import FetchError


def next_fomc(today: date) -> dict | None:
    path = config.ROOT / "data" / "fomc_meetings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for meeting in data.get("meetings", []):
        end = datetime.strptime(meeting["end"], "%Y-%m-%d").date()
        if end >= today:
            return {"date": end.isoformat(), "date_text": fmt.fmt_date(end), "source_url": data.get("source_url", "")}
    return None


def build_watch_list(release_keys: list[str], fred_key: str = "", today: date | None = None) -> list[dict]:
    today = today or date.today()
    items = []
    for key in release_keys:
        release = catalog.RELEASES[key]
        item = {"key": key, "name": release["name"], "why": release["why"], "date": "", "date_text": "",
                "source_url": release["schedule_url"], "status": ""}
        if key == "fomc":
            meeting = next_fomc(today)
            if meeting:
                item.update(date=meeting["date"], date_text=meeting["date_text"], source_url=meeting["source_url"],
                            status="From the bundled Fed calendar - verify on the Fed's site")
            else:
                item["status"] = "No date on file - check the Fed's calendar"
        elif release["release_id"] and fred_key:
            try:
                found = fred.fetch_next_release_date(release["release_id"], fred_key, today)
            except FetchError as exc:
                found, item["status"] = None, f"Date not fetched ({exc}) - check the schedule"
            if found:
                item.update(date=found.isoformat(), date_text=fmt.fmt_date(found),
                            status="From FRED's release calendar")
            elif not item["status"]:
                item["status"] = "No upcoming date listed yet - check the schedule"
        elif release["release_id"]:
            item["status"] = "Date left blank: add a FRED API key in Settings to fetch it, or check the schedule"
        else:
            item["status"] = "No single date - check the schedule link"
        items.append(item)
    items.sort(key=lambda i: (i["date"] == "", i["date"]))
    return items
