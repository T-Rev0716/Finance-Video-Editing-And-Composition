"""Turn guarded wording + fetched data into the finished package: outline, shot list,
titles, thumbnails and the YouTube description."""
from __future__ import annotations

import re

from . import compliance, wording
from .numbers import REMOVED
from .voice import BROLL_SAFETY_SUFFIX, ILLUSTRATIVE_LABEL

SECTION_TITLES = {
    "hook": "Hook (0-15 s)",
    "what_happened": "Here's what happened (explain it like I'm 12)",
    "why": "Why it happened",
    "what_it_means": "What it means for you",
    "watch_next": "What to watch next",
    "closing": "Closing line + subscribe",
}
ANGLE_LABELS = {"mortgage": "Mortgage", "job": "Job", "groceries": "Groceries", "retirement": "401(k)"}
_MARKER = re.compile(r"\[(CHART|HEADLINE|B-ROLL) (\d+)\]")


def _clean_lines(items: list[str], limit_check, fallback: list[str], count: int) -> list[str]:
    """Keep model lines that pass every rule; top up from the template list."""
    out: list[str] = []
    for line in list(items) + list(fallback):
        line = " ".join(line.split())
        if not line or line in out or REMOVED in line:
            continue
        if not limit_check(line) or not compliance.is_clean(line):
            continue
        out.append(line)
        if len(out) == count:
            break
    return out


def build_outline(words: dict, data: dict) -> dict:
    watch_bullets = []
    for item in data["watch"]:
        when = item["date_text"] or "date not fetched"
        watch_bullets.append({"text": f"{item['name']}: {when}. {item['why']}", "facts": [],
                              "source_url": item["source_url"], "status": item["status"]})
    takeaway = words.get("watch_takeaway")
    return {
        "hook": {"title": SECTION_TITLES["hook"], "bullets": words["hook"]},
        "what_happened": {"title": SECTION_TITLES["what_happened"], "bullets": words["what_happened"]},
        "why": words["causes"],
        "what_it_means": words["wallet"],
        "watch_next": {"title": SECTION_TITLES["watch_next"], "bullets": watch_bullets,
                       "takeaway": takeaway if takeaway and takeaway.get("text") else None},
        "closing": {"title": SECTION_TITLES["closing"], "line": words["closing_line"], "cta": words["cta"],
                    "facts": words.get("closing_facts", [])},
    }


def build_broll(words: dict) -> list[dict]:
    """Number the B-roll ideas, append the safety suffix and block anything not allowed."""
    out = []
    for n, item in enumerate(words.get("broll", []), 1):
        problems = compliance.check_broll_prompt(item["prompt"] + " " + item.get("idea", ""))
        prompt = item["prompt"].rstrip(". ") + ". " + BROLL_SAFETY_SUFFIX
        out.append({
            "n": n, "section": item.get("section", ""), "idea": item.get("idea", ""),
            "prompt": "" if problems else prompt, "blocked": bool(problems),
            "blocked_reason": "; ".join(problems), "label": ILLUSTRATIVE_LABEL,
        })
    return out


def _markers(bullets: list[dict]) -> list[tuple[str, int]]:
    found = []
    for bullet in bullets:
        for kind, number in _MARKER.findall(bullet["text"]):
            if (kind, int(number)) not in found:
                found.append((kind, int(number)))
    return found


def build_shot_list(outline: dict, data: dict, broll: list[dict], headlines: list[dict]) -> list[dict]:
    """One row per scene, in running order."""
    charts = {c["n"]: c for c in data["charts"]}
    heads = {h["n"]: h for h in headlines}
    brolls = {b["n"]: b for b in broll}
    used_broll: set[int] = set()
    shots: list[dict] = []

    def add(section: str, shot_type: str, what: str, **extra) -> None:
        shots.append({"n": len(shots) + 1, "section": section, "type": shot_type, "what": what, **extra})

    def chart_shot(section: str, number: int) -> None:
        chart = charts.get(number)
        if chart:
            add(section, f"CHART {number}", chart["title"], file=chart["files"]["1920x1080"],
                vertical_file=chart["files"]["1080x1920"],
                note=f"Real data through {chart['data_through']}. Source is printed on the chart.")

    def headline_shot(section: str, number: int) -> None:
        head = heads.get(number)
        if head:
            add(section, "HEADLINE SCREENSHOT", f"“{head['title']}” ({head['source']})", url=head["url"],
                note="Screenshot the real page with the outlet's name visible. Do not edit the headline.")

    def broll_shot(section: str, number: int) -> None:
        item = brolls.get(number)
        if item and number not in used_broll:
            used_broll.add(number)
            add(section, "B-ROLL (AI)", item["idea"] or "Illustrative B-roll", prompt=item["prompt"],
                label=item["label"], blocked=item["blocked"],
                note=(f"BLOCKED: {item['blocked_reason']}. Rewrite as a generic scene." if item["blocked"]
                      else "Paste the prompt into Higgsfield. Add an on-screen \"Illustrative\" label in the edit."))

    def section_shots(section_key: str, title: str, bullets: list[dict], talking: str) -> None:
        add(title, "TALKING HEAD", talking)
        for kind, number in _markers(bullets):
            {"CHART": chart_shot, "HEADLINE": headline_shot, "B-ROLL": broll_shot}[kind](title, number)
        for item in broll:  # B-roll the writer assigned to this section but did not mark inline
            if item["section"] == section_key and item["n"] not in used_broll:
                broll_shot(title, item["n"])

    section_shots("hook", SECTION_TITLES["hook"], outline["hook"]["bullets"], "To camera, high energy: the surprising fact or question.")
    section_shots("what_happened", SECTION_TITLES["what_happened"], outline["what_happened"]["bullets"], "To camera: the plain-English version.")
    for i, cause in enumerate(outline["why"], 1):
        title = f"{SECTION_TITLES['why']} - cause {i}"
        add(title, "TALKING HEAD", f"Set up cause {i}: {cause['cause']}")
        chart_shot(title, cause["chart"])
        for kind, number in _markers(cause["bullets"]):
            if kind == "CHART" and number == cause["chart"]:
                continue
            {"CHART": chart_shot, "HEADLINE": headline_shot, "B-ROLL": broll_shot}[kind](title, number)
        if i == 1:
            for item in broll:
                if item["section"] == "why" and item["n"] not in used_broll:
                    broll_shot(title, item["n"])
    wallet_bullets = [b for bullets in outline["what_it_means"].values() for b in bullets]
    section_shots("what_it_means", SECTION_TITLES["what_it_means"], wallet_bullets,
                  "To camera: mortgage, job, groceries, 401(k). One beat each.")
    add(SECTION_TITLES["watch_next"], "TALKING HEAD", "To camera: the dates and data releases to watch.",
        note="Optional: put the dates on screen as a text card.")
    for item in broll:  # anything left over still gets a slot so no prompt is lost
        if item["n"] not in used_broll:
            broll_shot(SECTION_TITLES["watch_next"], item["n"])
    add(SECTION_TITLES["closing"], "TALKING HEAD", "To camera: closing line, disclaimer, subscribe.")
    return shots


def cited_fact_ids(outline: dict) -> list[str]:
    ids: list[str] = []

    def take(bullets: list[dict]) -> None:
        for bullet in bullets:
            for fact_id in bullet.get("facts", []):
                if fact_id not in ids:
                    ids.append(fact_id)

    take(outline["hook"]["bullets"])
    take(outline["what_happened"]["bullets"])
    for cause in outline["why"]:
        take(cause["bullets"])
    for bullets in outline["what_it_means"].values():
        take(bullets)
    for fact_id in outline["closing"].get("facts", []):
        if fact_id not in ids:
            ids.append(fact_id)
    return ids


def build_description(topic: str, summary: str, data: dict, cited: list[str], shots: list[dict],
                      headlines: list[dict], disclaimer: str, channel: str = "") -> str:
    """Ready-to-paste YouTube description: summary, sources, AI disclosure, disclaimer."""
    lines = [summary.strip(), ""]
    lines += ["CHAPTERS (replace the times after editing)",
              "0:00 The hook", "0:00 What happened", "0:00 Why it happened",
              "0:00 What it means for you", "0:00 What to watch next", ""]

    sources: dict[str, str] = {}
    for chart in data["charts"]:
        for series in chart["series"]:
            sources.setdefault(series["source_url"], f"{series['title']} - {series['source_name']}")
    for fact in data["facts"]:
        if fact["id"] in cited and fact["status"] != "verify" and fact.get("source_url"):
            sources.setdefault(fact["source_url"], fact["source_name"])
    lines.append("SOURCES AND DATA")
    lines += [f"- {label}: {url}" for url, label in sources.items()]
    lines.append("All charts in this video are drawn from the public data linked above.")
    lines.append("")

    news = [h for h in headlines if h.get("url")]
    if news:
        lines.append("NEWS COVERAGE REFERENCED")
        lines += [f"- {h['title']} ({h['source']}): {h['url']}" for h in news]
        lines.append("")

    if any(s["type"] == "B-ROLL (AI)" for s in shots):
        lines += ["AI DISCLOSURE",
                  "Some B-roll in this video is AI-generated and illustrative only. It does not show real people or "
                  "real events. All charts use real data.", ""]

    lines += ["DISCLAIMER", disclaimer.strip(), ""]
    if channel:
        lines.append(f"{channel} - plain-English money news.")
    return "\n".join(lines).rstrip() + "\n"


def assemble(topic: str, words: dict, data: dict, headlines: list[dict], brief: dict, settings: dict) -> dict:
    """Everything after the wording step. Pure code."""
    lead = wording.lead_facts(brief)
    titles = _clean_lines(words.get("titles", []), lambda t: len(t) <= wording.TITLE_LIMIT,
                          wording.template_titles(brief, lead), 8)
    thumbnails = _clean_lines(words.get("thumbnails", []), lambda t: len(t.split()) <= wording.THUMB_WORD_LIMIT,
                              wording.template_thumbnails(brief, lead), 3)
    outline = build_outline(words, data)
    broll = build_broll(words)
    shots = build_shot_list(outline, data, broll, headlines)
    cited = cited_fact_ids(outline)
    description = build_description(topic, words.get("description_summary", ""), data, cited, shots, headlines,
                                    settings.get("DISCLAIMER", ""), settings.get("CHANNEL_NAME", ""))
    return {"outline": outline, "broll": broll, "shots": shots, "titles": titles, "thumbnails": thumbnails,
            "description": description, "cited_fact_ids": cited,
            "removed_numbers": words.get("removed_numbers", []), "wording_source": words.get("source", "templates")}
