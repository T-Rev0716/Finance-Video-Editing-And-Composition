"""'What changed since I recorded?' - freeze the facts, re-fetch later, and diff.

Financial numbers update between recording and the final edit. Freezing saves exactly
what the presenter recorded against. Checking re-fetches the same data into a staging
area (nothing is overwritten), lists every fact that changed, and names each card,
chart, graphic and description line that uses it. The user then chooses, fact by fact:
keep the as-recorded value with a date note, or accept the new value and flag the
affected cards for a retake. Card wording is never rewritten, and the package as it
stood is saved under versions/ first.
"""
from __future__ import annotations

import copy
import re
import shutil
from datetime import date, datetime
from pathlib import Path

from . import builder, compliance, config, projects, recording_cards, reports, store
from .facts import fact_label
from .sources import http

FROZEN_FILE = "frozen_facts.json"
CHANGES_FILE = "fact_changes.json"
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


class FactDiffError(ValueError):
    """Shown to the user."""


def _folder(project_id: str) -> Path:
    return projects.project_dir(project_id)


def frozen(project_id: str) -> dict | None:
    return store.read_json(_folder(project_id) / FROZEN_FILE, None)


def freeze(project_id: str, reason: str = "manual") -> dict:
    """Save the facts exactly as they are now, with the last observation of every data file."""
    project = projects.load(project_id)
    series = {}
    for path in sorted((_folder(project_id) / "data").glob("*.csv")):
        rows = path.read_text(encoding="utf-8").strip().splitlines()
        if len(rows) > 1:
            last_date, _, last_value = rows[-1].partition(",")
            series[path.stem] = {"observations": len(rows) - 1, "last_date": last_date, "last_value": last_value}
    snapshot = {
        "frozen_at": store.now_iso(), "reason": reason, "facts": copy.deepcopy(project.get("facts", [])),
        "series": series,
        "charts": [{"n": c["n"], "id": c["id"], "data_through": c.get("data_through", "")} for c in project.get("charts", [])],
        "headlines": [h["title"] for h in project.get("headlines", [])],
    }
    store.write_json(_folder(project_id) / FROZEN_FILE, snapshot)
    project["fact_freeze"] = {"frozen_at": snapshot["frozen_at"], "reason": reason, "facts": len(snapshot["facts"])}
    projects.save(project)
    return snapshot


def ensure_frozen(project_id: str, reason: str) -> dict:
    """Freeze only if there is no snapshot yet (called when a card is first marked recorded)."""
    return frozen(project_id) or freeze(project_id, reason)


# ---------------------------------------------------------------- the diff itself (pure)
def _first_number(text: str) -> tuple[float, int] | None:
    match = _NUMBER.search(text or "")
    if not match:
        return None
    raw = match.group(0).replace(",", "")
    return float(raw), len(raw.partition(".")[2])


def _delta(frozen_value: str, live_value: str) -> tuple[float | None, str]:
    """Numeric difference when both values lead with a number in the same unit."""
    a, b = _first_number(frozen_value), _first_number(live_value)
    if a is None or b is None:
        return None, ""
    shape = lambda text: _NUMBER.sub("#", text, count=1)  # noqa: E731 - "7.11%" and "7.25%" share the shape "#%"
    if shape(frozen_value) != shape(live_value):
        return None, ""
    diff = round(b[0] - a[0], max(a[1], b[1]) + 2)
    decimals = max(a[1], b[1])
    unit = " percentage points" if "%" in frozen_value else ""
    prefix = "$" if frozen_value.strip().startswith("$") else ""
    sign = "+" if diff > 0 else "-" if diff < 0 else ""
    return diff, f"{sign}{prefix}{abs(diff):,.{decimals}f}{unit}"


def compute_diff(frozen_facts: list[dict], live_facts: list[dict]) -> dict:
    """Compare by each fact's stable key. News headlines are compared separately by title."""
    live = {f["key"]: f for f in live_facts}
    changes, unavailable = [], []
    for old in frozen_facts:
        if old["key"].startswith("NEWS."):
            continue
        new = live.get(old["key"])
        if new is None:
            unavailable.append({"fact_id": old["id"], "key": old["key"], "label": fact_label(old),
                                "frozen_value": old.get("value", ""), "note": "Could not be re-fetched; left as recorded."})
            continue
        if old.get("value", "") == new.get("value", "") and old.get("as_of", "") == new.get("as_of", ""):
            continue
        delta, delta_text = _delta(old.get("value", ""), new.get("value", ""))
        changes.append({
            "fact_id": old["id"], "key": old["key"], "label": fact_label(old),
            "frozen_value": old.get("value", ""), "live_value": new.get("value", ""),
            "frozen_as_of": old.get("as_of", ""), "live_as_of": new.get("as_of", ""),
            "frozen_claim": old.get("claim", ""), "live_claim": new.get("claim", ""),
            "delta": delta, "delta_text": delta_text,
            "kind": "revised" if old.get("as_of", "") == new.get("as_of", "") else "new_data",
            "source_url": old.get("source_url", ""), "decision": None,
        })
    return {"changes": changes, "unavailable": unavailable}


def find_affected(project: dict, cards: list[dict], change: dict) -> dict:
    """Everything that uses this fact: cards, charts, graphics, thumbnails, description lines."""
    fact_id = change["fact_id"]
    tag = "{" + fact_id + "}"
    card_hits = [{"id": c["id"], "title": c["title"]} for c in cards if fact_id in c.get("fact_ids", []) or tag in c.get("text", "")]
    chart_hits = [{"n": c["n"], "title": c["title"]} for c in project.get("charts", []) if fact_id in c.get("fact_ids", [])]
    chart_numbers = {c["n"] for c in chart_hits}
    graphic_hits = [{"n": g["n"], "title": g["title"], "type": g["type"]} for g in project.get("graphics", [])
                    if fact_id in g.get("fact_ids", []) or g.get("chart_n") in chart_numbers]
    thumb_hits = [{"n": t["n"], "headline": t.get("headline", "")} for t in project.get("thumbnail_renders", [])
                  if fact_id in t.get("fact_ids", []) or t.get("chart_n") in chart_numbers]
    value = change["frozen_value"]
    lines = []
    for number, line in enumerate(project.get("description", "").splitlines(), 1):
        if (change["source_url"] and change["source_url"] in line) or (value and any(ch.isdigit() for ch in value) and value in line):
            lines.append({"line": number, "text": line})
    return {"cards": card_hits, "charts": chart_hits, "graphics": graphic_hits, "thumbnails": thumb_hits,
            "description_lines": lines}


# ---------------------------------------------------------------- refresh into staging and diff
def check_changes(project_id: str, settings: dict | None = None, today: date | None = None) -> dict:
    """Re-fetch everything into staging/ (the project itself is untouched) and diff against the snapshot."""
    snapshot = frozen(project_id)
    if snapshot is None:
        raise FactDiffError("Freeze the facts first, so there is something to compare against.")
    settings = settings or config.load_settings()
    project = projects.load(project_id)
    staging = _folder(project_id) / "staging"
    shutil.rmtree(staging, ignore_errors=True)
    (staging / "charts").mkdir(parents=True)

    theme = project.get("theme") or {"headlines": []}
    latest = reports.latest_report()
    if latest:  # pick up new headlines for the same theme, if today's report still has it
        theme = next((t for t in latest["themes"] if t["theme"] == theme.get("theme")), theme)

    ctx = builder.DataContext(settings, today)
    with http.fresh():
        data = builder.gather(project["plan"], theme, ctx, staging / "charts")
    (staging / "data").mkdir(exist_ok=True)
    for series_id, series in ctx.raw.items():
        (staging / "data" / f"{series_id}.csv").write_text(series.to_csv(), encoding="utf-8")
    store.write_json(staging / "live.json", {"facts": data["facts"], "charts": data["charts"], "fetched_at": store.now_iso()})

    cards = recording_cards.load(project_id, project)["cards"]
    result = compute_diff(snapshot["facts"], data["facts"])
    for change in result["changes"]:
        change["affected"] = find_affected(project, cards, change)
    known = set(snapshot.get("headlines", []))
    report = {
        "checked_at": store.now_iso(), "frozen_at": snapshot["frozen_at"], **result,
        "new_headlines": [h for h in theme.get("headlines", []) if h["title"] not in known],
        "warnings": data["warnings"],
        "summary": (f"{len(result['changes'])} fact(s) changed since {snapshot['frozen_at'].replace('T', ' ')}."
                    if result["changes"] else "Nothing changed since you froze the facts."),
    }
    store.write_json(_folder(project_id) / CHANGES_FILE, report)
    return report


def last_report(project_id: str) -> dict | None:
    return store.read_json(_folder(project_id) / CHANGES_FILE, None)


# ---------------------------------------------------------------- applying the user's choices
def _save_version(project_id: str, chart_files: list[str]) -> str:
    """Copy the package as it stands into versions/<time>/ before anything is changed."""
    folder = _folder(project_id)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = store.unique_path(folder / "versions", stamp)
    (target / "charts").mkdir(parents=True)
    for name in ("project.json", recording_cards.FILE, FROZEN_FILE, "youtube_description.txt"):
        if (folder / name).exists():
            shutil.copyfile(folder / name, target / name)
    for name in chart_files:
        if (folder / "charts" / name).exists():
            shutil.copyfile(folder / "charts" / name, target / "charts" / name)
    return target.name


def resolve(project_id: str, decisions: dict[str, str], settings: dict | None = None) -> dict:
    """decisions: {fact key: 'keep_frozen' | 'accept_new'}."""
    settings = settings or config.load_settings()
    report = last_report(project_id)
    if report is None:
        raise FactDiffError("Run 'check for changes' first.")
    pending = {c["key"]: c for c in report["changes"]}
    for key, choice in decisions.items():
        if key not in pending:
            raise FactDiffError(f"{key} is not in the latest change report. Check for changes again.")
        if choice not in ("keep_frozen", "accept_new"):
            raise FactDiffError("Choose 'keep_frozen' or 'accept_new' for each fact.")

    folder = _folder(project_id)
    project = projects.load(project_id)
    live = store.read_json(folder / "staging" / "live.json", {"facts": [], "charts": []})
    live_facts = {f["key"]: f for f in live["facts"]}
    live_charts = {c["id"]: c for c in live["charts"]}
    accepted = [pending[k] for k, v in decisions.items() if v == "accept_new"]
    stale_charts = {c["n"] for change in accepted for c in change["affected"]["charts"]}
    chart_files = [name for c in project.get("charts", []) if c["n"] in stale_charts
                   for name in list(c["files"].values()) + [c.get("spec_file", "")] if name]
    version = _save_version(project_id, chart_files)

    snapshot = frozen(project_id)
    notes = project.get("as_recorded_notes", [])
    for key, choice in decisions.items():
        change = pending[key]
        if choice == "keep_frozen":
            note = (f"As recorded: {change['label']} was {change['frozen_value']} (as of {change['frozen_as_of']}). "
                    f"It has since updated to {change['live_value']} ({change['live_as_of']}).")
            for card in change["affected"]["cards"]:
                recording_cards.add_flag(project_id, card["id"], "date_note", note)
            line = f"{change['label']}: {change['frozen_value']} as of {change['frozen_as_of']} (updated since recording)."
            if line not in notes:
                notes.append(line)
        else:
            new = live_facts[key]
            for fact in project["facts"]:
                if fact["key"] == key:
                    fact.update({k: new.get(k, fact.get(k)) for k in ("claim", "value", "as_of", "trend", "note")})
            for fact in snapshot["facts"]:  # the accepted value becomes the new baseline
                if fact["key"] == key:
                    fact.update({k: new.get(k, fact.get(k)) for k in ("claim", "value", "as_of", "trend", "note")})
            retake = (f"{change['label']} changed from {change['frozen_value']} ({change['frozen_as_of']}) to "
                      f"{change['live_value']} ({change['live_as_of']}). Re-record this card; your wording was not changed.")
            for card in change["affected"]["cards"]:
                recording_cards.add_flag(project_id, card["id"], "retake", retake, status="needs_another_take")
        change["decision"] = choice
        change["decided_at"] = store.now_iso()

    # add_flag saved project.json (cards mirror); reload before editing the rest
    cards_now = projects.load(project_id).get("recording_cards", project.get("recording_cards"))
    if cards_now is not None:
        project["recording_cards"] = cards_now

    for chart in project.get("charts", []):  # swap in the refreshed chart files
        fresh = live_charts.get(chart["id"])
        if chart["n"] in stale_charts and fresh:
            for size, name in fresh["files"].items():
                shutil.copyfile(folder / "staging" / "charts" / name, folder / "charts" / chart["files"][size])
            if fresh.get("spec_file") and chart.get("spec_file"):
                shutil.copyfile(folder / "staging" / "charts" / fresh["spec_file"], folder / "charts" / chart["spec_file"])
            chart["data_through"] = fresh["data_through"]
            chart["refreshed_at"] = store.now_iso()
    for change in accepted:
        for series_file in (folder / "staging" / "data").glob("*.csv"):
            shutil.copyfile(series_file, folder / "data" / series_file.name)
        for group, key in (("graphics", "graphics"), ("thumbnails", "thumbnail_renders")):
            numbers = {item["n"] for item in change["affected"][group]}
            for item in project.get(key, []):
                if item["n"] in numbers:
                    item["stale"] = True

    if notes:
        project["as_recorded_notes"] = notes
        marker = "AS-RECORDED NOTE"
        body = project["description"].split(f"\n{marker}\n")[0].rstrip("\n")
        project["description"] = f"{body}\n\n{marker}\nFigures are as of the recording date.\n" + "\n".join(f"- {n}" for n in notes) + "\n"

    store.write_json(folder / FROZEN_FILE, snapshot)
    report["last_version"] = version
    store.write_json(folder / CHANGES_FILE, report)
    project["compliance"] = compliance.run_checks(project, settings.get("DISCLAIMER", ""))
    projects.save(project)
    projects.write_exports(project)
    return report
