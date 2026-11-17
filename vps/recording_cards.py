"""Recording cards: one large card per outline section, editable in the presenter's own words.

Rewriting a card never loses its numbers: the sourced facts are pinned to the card
separately from the wording, and every edit is checked by the number guard and the
compliance scan. Edits autosave with an undo/redo history.
"""
from __future__ import annotations

import copy
import re

from . import compliance, projects, store
from .numbers import MARKER, unknown_placeholders, unverified_numbers
from .package import ANGLE_LABELS, SECTION_TITLES

FILE = "recording_cards.json"
STATUSES = ("unrecorded", "recorded", "needs_another_take")
MAX_HISTORY = 50
EDITABLE = ("text", "pronunciation", "fact_ids", "title")


def _lines(bullets: list[dict]) -> str:
    return "\n".join(f"- {b['text']}" for b in bullets)


def _ids(bullets: list[dict]) -> list[str]:
    out: list[str] = []
    for bullet in bullets:
        for fact_id in bullet.get("facts", []):
            if fact_id not in out:
                out.append(fact_id)
    return out


def build_cards(project: dict) -> list[dict]:
    """One card per outline section, in running order, with the section's facts pinned."""
    outline = project["outline"]
    cards: list[dict] = []

    def add(card_id: str, group: str, title: str, bullets: list[dict], extra_facts: list[str] | None = None) -> None:
        fact_ids = _ids(bullets)
        for fact_id in extra_facts or []:
            if fact_id not in fact_ids:
                fact_ids.append(fact_id)
        text = _lines(bullets)
        cards.append({"id": card_id, "group": group, "title": title, "text": text, "original_text": text,
                      "fact_ids": fact_ids, "pronunciation": "", "visuals": [], "status": "unrecorded", "flags": []})

    add("hook", SECTION_TITLES["hook"], SECTION_TITLES["hook"], outline["hook"]["bullets"])
    add("what_happened", SECTION_TITLES["what_happened"], SECTION_TITLES["what_happened"], outline["what_happened"]["bullets"])
    for i, cause in enumerate(outline["why"], 1):
        add(f"why_{i}", f"{SECTION_TITLES['why']} - cause {i}", f"Why it happened {i}: {cause['cause']}",
            [{"text": f"{cause['cause']} [CHART {cause['chart']}]", "facts": []}] + cause["bullets"])
    for angle, bullets in outline["what_it_means"].items():
        add(f"means_{angle}", SECTION_TITLES["what_it_means"], f"What it means for you: {ANGLE_LABELS.get(angle, angle)}", bullets)
    watch = [{"text": b["text"], "facts": []} for b in outline["watch_next"]["bullets"]]
    if outline["watch_next"].get("takeaway"):
        watch.append(outline["watch_next"]["takeaway"])
    add("watch_next", SECTION_TITLES["watch_next"], SECTION_TITLES["watch_next"], watch)
    closing = outline["closing"]
    add("closing", SECTION_TITLES["closing"], SECTION_TITLES["closing"],
        [{"text": closing["line"], "facts": closing.get("facts", [])}, {"text": closing["cta"], "facts": []}])

    # Attach each planned visual to the card that mentions it, else the first card of its section.
    for shot in project.get("shots", []):
        ref = shot.get("ref")
        if not ref:
            continue
        group = [c for c in cards if c["group"] == shot["section"]]
        if not group:
            continue
        tag = f"[{ref['kind']} {ref['n']}]"
        target = next((c for c in group if tag in c["text"]), group[0])
        entry = {"shot_n": shot["n"], "kind": ref["kind"], "n": ref["n"]}
        if entry not in target["visuals"]:
            target["visuals"].append(entry)
    return cards


# ---------------------------------------------------------------- checks
def _allowed_extras(project: dict) -> list[dict]:
    """Dates of upcoming releases count as verified text (they were fetched or bundled, with a source)."""
    return [{"status": "primary", "claim": item.get("date_text", ""), "value": "", "as_of": ""}
            for item in project.get("watch", []) if item.get("date_text")]


def check_text(text: str, project: dict) -> dict:
    """Live checks on hand-edited wording. Warnings only - the text is never rewritten."""
    facts = project.get("facts", [])
    by_id = {f["id"]: f for f in facts}
    # A quoted real headline is not the presenter's claim; it already carries a "verify" flag.
    scan = text
    for headline in project.get("headlines", []):
        scan = scan.replace(headline["title"], " ")
    flags = compliance.scan_text(MARKER.sub(" ", text))
    result = {
        "unverified_numbers": unverified_numbers(scan, facts + _allowed_extras(project)),
        "unknown_facts": unknown_placeholders(text, by_id),
        "advice": [hit for hits in flags.values() for hit in hits],
    }
    result["ok"] = not any(result.values())
    return result


def card_warnings(card: dict, project: dict) -> dict:
    return check_text(card["text"], project)


# ---------------------------------------------------------------- storage
def _path(project_id: str):
    return projects.project_dir(project_id) / FILE


def load(project_id: str, project: dict | None = None) -> dict:
    """The saved cards, or a fresh set built from the outline the first time."""
    state = store.read_json(_path(project_id), None)
    if state and state.get("cards"):
        return state
    project = project or projects.load(project_id)
    state = {"version": 1, "cards": build_cards(project), "undo": [], "redo": [], "cues": [], "total_seconds": 0,
             "updated": store.now_iso()}
    _save(project_id, state)
    return state


def _save(project_id: str, state: dict) -> None:
    state["updated"] = store.now_iso()
    store.write_json(_path(project_id), state)
    # project.json carries the current cards too, so an exported project is self-contained.
    try:
        project = projects.load(project_id)
    except FileNotFoundError:
        return
    project["recording_cards"] = state["cards"]
    projects.save(project)


def _checkpoint(state: dict, label: str) -> None:
    state["undo"].append({"label": label, "cards": copy.deepcopy(state["cards"])})
    del state["undo"][:-MAX_HISTORY]
    state["redo"] = []


def _card(state: dict, card_id: str) -> dict:
    for card in state["cards"]:
        if card["id"] == card_id:
            return card
    raise KeyError(card_id)


# ---------------------------------------------------------------- edits
def update_card(project_id: str, card_id: str, changes: dict, checkpoint: bool = True) -> dict:
    """Autosave an edit. checkpoint=False folds it into the previous undo step (same typing burst)."""
    state = load(project_id)
    card = _card(state, card_id)
    changes = {k: v for k, v in changes.items() if k in EDITABLE}
    if "fact_ids" in changes:
        known = {f["id"] for f in projects.load(project_id).get("facts", [])}
        changes["fact_ids"] = [f for f in dict.fromkeys(changes["fact_ids"]) if f in known]
    if all(card.get(k) == v for k, v in changes.items()):
        return state
    if checkpoint or not state["undo"]:
        _checkpoint(state, f"Edit {card['title'][:40]}")
    card.update(changes)
    _save(project_id, state)
    return state


def set_status(project_id: str, card_id: str, status: str) -> dict:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    state = load(project_id)
    card = _card(state, card_id)
    if card["status"] != status:
        _checkpoint(state, f"Mark {status.replace('_', ' ')}")
        card["status"] = status
        if status == "recorded":
            card["flags"] = [f for f in card.get("flags", []) if f.get("kind") != "retake"]
        _save(project_id, state)
    return state


def reorder(project_id: str, order: list[str]) -> dict:
    state = load(project_id)
    by_id = {c["id"]: c for c in state["cards"]}
    if sorted(order) != sorted(by_id):
        raise ValueError("the new order must list every card exactly once")
    if [c["id"] for c in state["cards"]] != order:
        _checkpoint(state, "Reorder cards")
        state["cards"] = [by_id[i] for i in order]
        _save(project_id, state)
    return state


def move(project_id: str, card_id: str, delta: int) -> dict:
    state = load(project_id)
    order = [c["id"] for c in state["cards"]]
    index = order.index(card_id)
    target = max(0, min(len(order) - 1, index + delta))
    order.insert(target, order.pop(index))
    return reorder(project_id, order)


def reset_card(project_id: str, card_id: str) -> dict:
    """Put the generated wording back (undoable)."""
    state = load(project_id)
    return update_card(project_id, card_id, {"text": _card(state, card_id)["original_text"]})


def undo(project_id: str) -> dict:
    state = load(project_id)
    if state["undo"]:
        step = state["undo"].pop()
        state["redo"].append({"label": step["label"], "cards": copy.deepcopy(state["cards"])})
        state["cards"] = step["cards"]
        _save(project_id, state)
    return state


def redo(project_id: str) -> dict:
    state = load(project_id)
    if state["redo"]:
        step = state["redo"].pop()
        state["undo"].append({"label": step["label"], "cards": copy.deepcopy(state["cards"])})
        state["cards"] = step["cards"]
        _save(project_id, state)
    return state


def add_flag(project_id: str, card_id: str, kind: str, text: str, status: str | None = None) -> None:
    """Attach a note to a card without touching its wording (used by the fact-change checker)."""
    state = load(project_id)
    card = _card(state, card_id)
    _checkpoint(state, "Fact change")
    card.setdefault("flags", []).append({"kind": kind, "text": text, "at": store.now_iso()})
    if status:
        card["status"] = status
    _save(project_id, state)


def set_cues(project_id: str, cues: list[dict], total_seconds: float) -> dict:
    """Save the timestamps logged in recording view."""
    state = load(project_id)
    ids = {c["id"] for c in state["cards"]}
    clean = []
    for cue in cues:
        if cue.get("card_id") in ids:
            clean.append({"card_id": cue["card_id"], "start": round(max(0.0, float(cue.get("start", 0))), 2),
                          "flagged": bool(cue.get("flagged"))})
    clean.sort(key=lambda c: c["start"])
    state["cues"] = clean
    state["total_seconds"] = round(max(float(total_seconds or 0), clean[-1]["start"] if clean else 0), 2)
    _save(project_id, state)
    return state


# ---------------------------------------------------------------- what the browser gets
_FACT_REF = re.compile(r"\{(F\d+)\}")


def view(state: dict, project: dict) -> dict:
    """Cards plus everything needed to draw them: pinned fact details, visuals, live warnings."""
    facts = {f["id"]: f for f in project.get("facts", [])}
    charts = {c["n"]: c for c in project.get("charts", [])}
    headlines = {h["n"]: h for h in project.get("headlines", [])}
    broll = {b["n"]: b for b in project.get("broll", [])}
    slots = (project.get("asset_board") or {}).get("slots", {})
    cards = []
    for card in state["cards"]:
        pinned = []
        for fact_id in list(dict.fromkeys(card["fact_ids"] + _FACT_REF.findall(card["text"]))):
            fact = facts.get(fact_id)
            if fact:
                pinned.append({k: fact.get(k, "") for k in ("id", "value", "claim", "as_of", "source_name", "source_url", "status")})
        visuals = []
        for v in card.get("visuals", []):
            slot = slots.get(str(v["shot_n"]), {})
            item = {"kind": v["kind"], "n": v["n"], "shot_n": v["shot_n"], "file": slot.get("file", ""), "media": slot.get("media", "")}
            if v["kind"] == "CHART" and v["n"] in charts:
                item.update(title=charts[v["n"]]["title"], file=f"charts/{charts[v['n']]['files']['1920x1080']}", media="image")
            elif v["kind"] == "HEADLINE" and v["n"] in headlines:
                item.update(title=headlines[v["n"]]["title"], url=headlines[v["n"]]["url"])
            elif v["kind"] == "B-ROLL" and v["n"] in broll:
                item.update(title=broll[v["n"]]["idea"], prompt=broll[v["n"]]["prompt"], blocked=broll[v["n"]]["blocked"])
            visuals.append(item)
        cards.append({**card, "pinned": pinned, "visuals": visuals, "warnings": card_warnings(card, project),
                      "edited": card["text"] != card["original_text"]})
    counts = {status: sum(1 for c in cards if c["status"] == status) for status in STATUSES}
    return {"cards": cards, "can_undo": bool(state["undo"]), "can_redo": bool(state["redo"]),
            "undo_label": state["undo"][-1]["label"] if state["undo"] else "",
            "redo_label": state["redo"][-1]["label"] if state["redo"] else "",
            "cues": state.get("cues", []), "total_seconds": state.get("total_seconds", 0),
            "counts": counts, "updated": state.get("updated", "")}
