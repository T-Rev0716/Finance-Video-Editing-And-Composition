"""Write the package as readable files, so a project folder is useful without the app."""
from __future__ import annotations

from .package import ANGLE_LABELS, SECTION_TITLES

STATUS_LABEL = {"primary": "PRIMARY SOURCE", "calculated": "CALCULATED FROM PRIMARY DATA", "verify": "VERIFY (news only)"}


def fact_sheet_md(project: dict) -> str:
    lines = [f"# Fact sheet: {project['topic']}", "",
             "Every number below was fetched from the linked source or calculated from fetched numbers. "
             "Anything marked VERIFY appears only in a news article: check it before you say it.", ""]
    group = None
    for fact in project["facts"]:
        if fact.get("group") != group:
            group = fact.get("group")
            lines += [f"## {group}", ""]
        lines.append(f"- **{fact['id']}** [{STATUS_LABEL.get(fact['status'], fact['status'])}] {fact['claim']}")
        source = f"  - Source: {fact['source_name']}"
        if fact.get("source_url"):
            source += f" - {fact['source_url']}"
        lines.append(source)
        if fact.get("note"):
            lines.append(f"  - Note: {fact['note']}")
    if project.get("warnings"):
        lines += ["", "## Data notes", ""] + [f"- {w}" for w in project["warnings"]]
    return "\n".join(lines) + "\n"


def _bullets(bullets: list[dict]) -> list[str]:
    out = []
    for bullet in bullets:
        refs = f" ({', '.join(bullet['facts'])})" if bullet.get("facts") else ""
        out.append(f"- {bullet['text']}{refs}")
    return out


def outline_md(project: dict) -> str:
    outline = project["outline"]
    lines = [f"# Outline: {project['topic']}", "",
             "Talking points only. Codes like (F3) point to the fact sheet. [CHART n] marks where a visual goes.", ""]
    lines += [f"## {outline['hook']['title']}", ""] + _bullets(outline["hook"]["bullets"]) + [""]
    lines += [f"## {outline['what_happened']['title']}", ""] + _bullets(outline["what_happened"]["bullets"]) + [""]
    lines += [f"## {SECTION_TITLES['why']}", ""]
    for i, cause in enumerate(outline["why"], 1):
        lines += [f"### Cause {i}: {cause['cause']} [CHART {cause['chart']}]", ""] + _bullets(cause["bullets"]) + [""]
    lines += [f"## {SECTION_TITLES['what_it_means']}", ""]
    for angle, bullets in outline["what_it_means"].items():
        lines += [f"### {ANGLE_LABELS.get(angle, angle)}", ""] + _bullets(bullets) + [""]
    lines += [f"## {outline['watch_next']['title']}", ""]
    for item in outline["watch_next"]["bullets"]:
        lines.append(f"- {item['text']} [{item['status']}] {item['source_url']}")
    if outline["watch_next"].get("takeaway"):
        lines.append(f"- {outline['watch_next']['takeaway']['text']}")
    lines += ["", f"## {outline['closing']['title']}", "", f"- {outline['closing']['line']}", f"- {outline['closing']['cta']}"]
    return "\n".join(lines) + "\n"


def shot_list_md(project: dict) -> str:
    lines = [f"# Shot list: {project['topic']}", ""]
    section = None
    for shot in project["shots"]:
        if shot["section"] != section:
            section = shot["section"]
            lines += ["", f"## {section}", ""]
        lines.append(f"{shot['n']}. **{shot['type']}** - {shot['what']}")
        if shot.get("file"):
            lines.append(f"   - File: charts/{shot['file']} (vertical: charts/{shot['vertical_file']})")
        if shot.get("url"):
            lines.append(f"   - Link: {shot['url']}")
        if shot.get("prompt"):
            lines.append(f"   - Label on screen: {shot['label']}")
            lines.append(f"   - Higgsfield prompt: {shot['prompt']}")
        if shot.get("note"):
            lines.append(f"   - {shot['note']}")
    return "\n".join(lines) + "\n"


def titles_md(project: dict) -> str:
    lines = [f"# Titles and thumbnails: {project['topic']}", "", "## Title options (60 characters or fewer)", ""]
    lines += [f"{i}. {title} ({len(title)} chars)" for i, title in enumerate(project["titles"], 1)]
    lines += ["", "## Thumbnail text (4 words or fewer)", ""] + [f"- {t}" for t in project["thumbnails"]]
    outliers = project.get("competitor_outliers", [])
    if outliers:
        lines += ["", "## Competitor outlier titles (from the report, for comparison)", ""]
        for video in outliers:
            views = f"{video['views']:,} views" if video.get("views") is not None else "views not in report"
            lines.append(f"- {video['title']} - {video.get('channel') or 'unknown channel'} ({views}) {video.get('url', '')}")
    return "\n".join(lines) + "\n"


def compliance_md(project: dict) -> str:
    mark = {"pass": "PASS", "fail": "FAIL", "warn": "REVIEW", "manual": "TO DO"}
    lines = [f"# Compliance checklist: {project['topic']}", "",
             "Education and commentary only. Not personal investment advice.", "", "## Automatic checks", ""]
    for item in project["compliance"]["automatic"]:
        lines.append(f"- [{mark[item['status']]}] {item['label']}: {item['detail']}")
    lines += ["", "## Confirm before you publish", ""]
    for item in project["compliance"]["manual"]:
        lines.append(f"- [{'x' if item.get('checked') else ' '}] {item['label']}")
    return "\n".join(lines) + "\n"


def clips_md(project: dict) -> str:
    plan = project.get("clips") or {}
    lines = [f"# Clip plan: {project['topic']}", ""]
    if plan.get("message"):
        lines += [plan["message"], ""]
    for clip in plan.get("clips", []):
        approx = " (estimated)" if clip.get("estimated_times") else ""
        lines += [f"## Clip {clip['n']}: {clip['start']} to {clip['end']}{approx} - {clip['duration_seconds']} s", "",
                  f"- Caption hook: {clip['caption']}", f"- Opens with: {clip['opens_with']}"]
        if clip.get("why"):
            lines.append(f"- Why this works: {clip['why']}")
        lines += [f"- Note: {note}" for note in clip.get("notes", [])]
        lines += ["", f"> {clip['text']}", ""]
    return "\n".join(lines) + "\n"
