"""The Generate button: topic in, full recording package out."""
from __future__ import annotations

import traceback
from datetime import date, datetime
from typing import Callable

from . import builder, clips, compliance, config, llm, package, projects, topics, wording


def _headlines(theme: dict, facts: list[dict]) -> list[dict]:
    news = {f["key"]: f["id"] for f in facts if f["key"].startswith("NEWS.")}
    return [{"n": i, "title": h["title"], "source": h.get("source") or "news article", "url": h.get("url", ""),
             "fact_id": news.get(f"NEWS.{i}", "")} for i, h in enumerate(theme.get("headlines", []), 1)]


def _competitor_titles(theme: dict, report: dict | None) -> list[dict]:
    seen, out = set(), []
    for video in (report or {}).get("competitor_outliers", []) + theme.get("competitor_videos", []):
        if video["title"] not in seen:
            seen.add(video["title"])
            out.append(video)
    return out


def generate(project_id: str, topic: str, theme: dict | None = None, report: dict | None = None,
             extra_series: list[str] | None = None, progress: Callable[[str], None] = lambda _m: None,
             settings: dict | None = None, today: date | None = None) -> dict:
    """Run the whole pipeline and save the project. Returns the saved project."""
    settings = settings or config.load_settings()
    theme = theme or {"theme": topic, "headlines": [], "search_trends": [], "competitor_videos": [], "tickers": []}
    folder = projects.project_dir(project_id)
    (folder / "charts").mkdir(parents=True, exist_ok=True)
    (folder / "data").mkdir(parents=True, exist_ok=True)

    project = {
        "id": project_id, "topic": topic, "created": datetime.now().isoformat(timespec="seconds"),
        "status": "generating", "report_file": (report or {}).get("file", ""), "theme": theme,
    }
    projects.save(project)

    try:
        progress("Choosing the data that tells this story")
        plan = topics.plan_topic(topic, theme, (report or {}).get("tickers", []), extra_series)
        ctx = builder.DataContext(settings, today)
        data = builder.gather(plan, theme, ctx, folder / "charts", progress)
        if not data["charts"]:
            raise RuntimeError(
                "No chart data could be fetched, so there is nothing to build on. "
                "Check your internet connection. Details: " + " | ".join(data["warnings"][:3]))
        for series_id, series in ctx.raw.items():
            (folder / "data" / f"{series_id}.csv").write_text(series.to_csv(), encoding="utf-8")

        headlines = _headlines(theme, data["facts"])
        competitor = _competitor_titles(theme, report)
        brief = {
            "topic": topic, "label": plan["label"], "plural": plan["plural"], "primary": plan["primary"],
            "lead_series": plan["lead_series"], "facts": data["facts"], "charts": data["charts"],
            "wallet": data["wallet"], "watch": data["watch"], "headlines": headlines,
            "channel": settings.get("CHANNEL_NAME", ""), "competitor_titles": [v["title"] for v in competitor],
        }

        warnings = list(data["warnings"])
        if settings.get("ANTHROPIC_API_KEY"):
            progress("Writing the outline, titles and B-roll prompts (LLM, wording only)")
            try:
                words = llm.llm_wording(brief, settings)
            except llm.LLMUnavailable as exc:
                warnings.append(f"LLM wording unavailable: {exc} Used the built-in templates.")
                words = wording.template_wording(brief)
        else:
            progress("Writing the outline, titles and B-roll prompts (built-in templates)")
            words = wording.template_wording(brief)

        progress("Building the shot list, description and compliance checklist")
        built = package.assemble(topic, words, data, headlines, brief, settings)
        project.update({
            "status": "ready", "plan": plan, "charts": data["charts"], "facts": data["facts"],
            "wallet": data["wallet"], "filings": data["filings"], "watch": data["watch"], "warnings": warnings,
            "headlines": headlines, "competitor_outliers": competitor,
            "llm_used": words.get("source", "templates") != "templates", "manual_checks": {}, **built,
        })
        project["compliance"] = compliance.run_checks(project, settings.get("DISCLAIMER", ""))
        projects.save(project)
        projects.write_exports(project)
        progress("Done")
    except Exception as exc:
        project.update({"status": "error", "error": str(exc), "error_detail": traceback.format_exc()})
        projects.save(project)
        raise
    return project


def add_transcript(project_id: str, filename: str, text: str, settings: dict | None = None) -> dict:
    """Upload a recorded video's transcript and build the clip plan."""
    settings = settings or config.load_settings()
    project = projects.load(project_id)
    suffix = ".srt" if filename.lower().endswith(".srt") else ".txt"
    (projects.project_dir(project_id) / f"transcript{suffix}").write_text(text, encoding="utf-8")
    picker = (lambda segments: llm.llm_clip_plan(segments, settings)) if settings.get("ANTHROPIC_API_KEY") else None
    project["clips"] = clips.plan_clips(filename, text, picker)
    project["clips"]["file"] = filename
    project["compliance"] = compliance.run_checks(project, settings.get("DISCLAIMER", ""))
    projects.save(project)
    projects.write_exports(project)
    return project


def set_manual_checks(project_id: str, checks: dict, settings: dict | None = None) -> dict:
    settings = settings or config.load_settings()
    project = projects.load(project_id)
    project["manual_checks"] = {k: bool(v) for k, v in checks.items()}
    project["compliance"] = compliance.run_checks(project, settings.get("DISCLAIMER", ""))
    projects.save(project)
    projects.write_exports(project)
    return project
