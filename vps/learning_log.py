"""Post-publish learning log: what was made, how long it took, and how it did.

Observations are plain counts and medians over the user's own logged episodes. There is
no predicted or synthetic score of any kind, and anything based on fewer than eight
episodes is labelled TENTATIVE.
"""
from __future__ import annotations

from statistics import median

from . import config, projects, store

FILE = "learning_log.json"
MIN_SAMPLE = 8
NUMERIC = ("views_48h", "views_7d", "ctr_pct", "avg_view_duration_sec")
TEXT = ("retention_notes", "audience_comments_notes")
MINUTES = ("prep_minutes", "recording_minutes", "editing_minutes")


def _index_path():
    return config.user_data_dir() / FILE


def hook_structure(hook: str) -> str:
    """A transparent label for how a hook opens. Rules, not a model."""
    first = " ".join(hook.split()[:14])
    if "?" in hook.split(".")[0]:
        return "question"
    if any(ch.isdigit() for ch in first):
        return "leads with a number"
    return "statement"


def defaults(project: dict) -> dict:
    """What the form starts with, taken from the project itself."""
    cards = project.get("recording_cards") or []
    hook_card = next((c for c in cards if c["id"] == "hook"), None)
    hook = hook_card["text"] if hook_card else "\n".join(b["text"] for b in project["outline"]["hook"]["bullets"])
    renders = project.get("thumbnail_renders") or []
    last = renders[-1] if renders else {}
    return {
        "project_id": project["id"], "topic": project["topic"], "created": project.get("created", ""),
        "hook_text": hook, "final_title": (project.get("titles") or [""])[0],
        "thumbnail_layout": last.get("layout", ""), "thumbnail_preset": last.get("preset", ""),
        "topic_family": (project.get("plan") or {}).get("primary", "") or "other",
        "open_lane": bool((project.get("theme") or {}).get("open_lane")),
        "published_date": "", **{k: None for k in MINUTES + NUMERIC}, **{k: "" for k in TEXT},
    }


def _number(value, allow_float: bool):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{value}' is not a number.") from None
    if number < 0:
        raise ValueError("Numbers cannot be negative.")
    return number if allow_float else int(round(number))


def load(project_id: str) -> dict:
    project = projects.load(project_id)
    saved = store.read_json(projects.project_dir(project_id) / FILE, {})
    return {**defaults(project), **saved}


def save(project_id: str, values: dict) -> dict:
    """Store the record in the project and in the cross-project index."""
    record = load(project_id)
    for key in ("hook_text", "final_title", "thumbnail_layout", "thumbnail_preset", "topic_family", "published_date") + TEXT:
        if key in values:
            record[key] = str(values[key] or "").strip()
    if "open_lane" in values:
        record["open_lane"] = bool(values["open_lane"])
    for key in MINUTES + NUMERIC:
        if key in values:
            record[key] = _number(values[key], allow_float=key == "ctr_pct")
    if record["ctr_pct"] is not None and record["ctr_pct"] > 100:
        raise ValueError("Click-through rate is a percentage, so it cannot be above 100.")
    minutes = [record[k] for k in MINUTES if record[k] is not None]
    record["total_minutes"] = sum(minutes) if minutes else None
    record["hook_structure"] = hook_structure(record["hook_text"])
    record["updated"] = store.now_iso()
    store.write_json(projects.project_dir(project_id) / FILE, record)
    index = [r for r in read_index() if r["project_id"] != project_id] + [record]
    store.write_json(_index_path(), index)
    return record


def read_index() -> list[dict]:
    return store.read_json(_index_path(), [])


def _label(n: int) -> str:
    return f"TENTATIVE — small sample size ({n} episode{'' if n == 1 else 's'})" if n < MIN_SAMPLE else f"Based on {n} episodes"


def _observation(title: str, text: str, n: int) -> dict:
    return {"title": title, "text": text, "n": n, "tentative": n < MIN_SAMPLE, "label": _label(n)}


def _best_group(records: list[dict], group_key: str, metric: str) -> tuple[str, float, int, int] | None:
    """(group, its median, episodes in that group, episodes with the metric)."""
    groups: dict[str, list[float]] = {}
    for record in records:
        if record.get(metric) is not None and record.get(group_key):
            groups.setdefault(str(record[group_key]), []).append(record[metric])
    if not groups:
        return None
    best = max(groups, key=lambda g: median(groups[g]))
    return best, median(groups[best]), len(groups[best]), sum(len(v) for v in groups.values())


def summarize(records: list[dict] | None = None) -> dict:
    """The comparison table plus a few plain observations, each with its sample size."""
    records = read_index() if records is None else records
    records = sorted(records, key=lambda r: r.get("published_date") or r.get("created") or "", reverse=True)
    observations = []
    timed = [r["total_minutes"] for r in records if r.get("total_minutes") is not None]
    if timed:
        observations.append(_observation("Median build time", f"{median(timed):.0f} minutes from prep to finished edit.", len(timed)))
    for title, group_key, metric, unit, noun in (
        ("Hook structure with the longest average view", "hook_structure", "avg_view_duration_sec", "seconds average view duration", "hook"),
        ("Thumbnail layout with the highest click-through", "thumbnail_layout", "ctr_pct", "% median click-through rate", "layout"),
        ("Topic family with the most 7-day views", "topic_family", "views_7d", "median views after 7 days", "topic family"),
    ):
        found = _best_group(records, group_key, metric)
        if found:
            group, value, in_group, total = found
            shown = f"{value:,.1f}" if metric == "ctr_pct" else f"{value:,.0f}"
            observations.append(_observation(
                title, f"'{group}': {shown} {unit} across {in_group} episode{'' if in_group == 1 else 's'} with that {noun}.", total))
    lanes = {flag: [r["views_7d"] for r in records if r.get("views_7d") is not None and bool(r.get("open_lane")) is flag]
             for flag in (True, False)}
    if lanes[True] and lanes[False]:
        observations.append(_observation(
            "Open-lane topics vs crowded topics",
            f"Open lane: {median(lanes[True]):,.0f} median 7-day views ({len(lanes[True])}). "
            f"Crowded: {median(lanes[False]):,.0f} ({len(lanes[False])}).", len(lanes[True]) + len(lanes[False])))
    return {
        "episodes": records, "count": len(records), "observations": observations, "min_sample": MIN_SAMPLE,
        "note": ("These are counts and medians of what you logged. They describe your past episodes; "
                 "they do not predict the next one, and there is no viral score."),
    }
