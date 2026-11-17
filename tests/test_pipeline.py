"""End to end: topic in, project folder out. Network and LLM are faked."""
from __future__ import annotations

import io
import json
import re
import zipfile

import pytest
from PIL import Image

from tests.conftest import TODAY
from vps import config, llm, pipeline, projects, reports
from vps.numbers import REMOVED


def run(net, report=True, settings=None, topic=None, theme_index=0):
    rep = reports.latest_report() if report else None
    theme = rep["themes"][theme_index] if rep else None
    topic = topic or (theme["theme"] if theme else "Why gas prices are rising")
    project_id = projects.new_project_id(topic)
    return pipeline.generate(project_id, topic, theme, rep, settings=settings or config.load_settings(), today=TODAY)


def all_wording(project) -> list[str]:
    outline = project["outline"]
    texts = [b["text"] for b in outline["hook"]["bullets"] + outline["what_happened"]["bullets"]]
    for cause in outline["why"]:
        texts += [cause["cause"]] + [b["text"] for b in cause["bullets"]]
    for bullets in outline["what_it_means"].values():
        texts += [b["text"] for b in bullets]
    return texts + [outline["closing"]["line"], outline["closing"]["cta"]] + project["titles"] + project["thumbnails"]


def test_generate_builds_the_whole_package(net, report_file):
    project = run(net)
    folder = projects.project_dir(project["id"])
    assert project["status"] == "ready" and project["llm_used"] is False

    # charts: 3-6, both sizes, exact pixels
    assert 3 <= len(project["charts"]) <= 6
    for chart in project["charts"]:
        assert Image.open(folder / "charts" / chart["files"]["1920x1080"]).size == (1920, 1080)
        assert Image.open(folder / "charts" / chart["files"]["1080x1920"]).size == (1080, 1920)
        assert all(s["source_url"].startswith("https://") for s in chart["series"])

    # fact sheet: every fact has a source; news is flagged; raw data is saved
    assert all(f["source_name"] for f in project["facts"])
    assert all(f["source_url"].startswith("https://") for f in project["facts"])
    news = [f for f in project["facts"] if f["key"].startswith("NEWS.")]
    assert len(news) == 2 and all(f["status"] == "verify" for f in news)
    assert (folder / "data" / "MORTGAGE30US.csv").read_text().startswith("date,MORTGAGE30US")

    # outline has the six sections in the presenter's structure
    outline = project["outline"]
    assert outline["hook"]["title"] == "Hook (0-15 s)"
    assert 2 <= len(outline["why"]) <= 3 and all(c["chart"] in {ch["n"] for ch in project["charts"]} for c in outline["why"])
    assert set(outline["what_it_means"]) == {"mortgage", "job", "groceries", "retirement"}
    assert outline["watch_next"]["bullets"] and outline["closing"]["cta"]

    # titles and thumbnails obey the limits
    assert len(project["titles"]) == 8 and all(len(t) <= 60 for t in project["titles"])
    assert len(project["thumbnails"]) == 3 and all(len(t.split()) <= 4 for t in project["thumbnails"])
    assert project["competitor_outliers"][0]["title"] == "Why Your Mortgage Just Got Worse"

    # shot list: every type present, AI visuals labelled
    types = {s["type"].split(" ")[0] for s in project["shots"]}
    assert {"TALKING", "CHART", "HEADLINE", "B-ROLL"} <= types
    ai = [s for s in project["shots"] if s["type"] == "B-ROLL (AI)"]
    assert ai and all("ILLUSTRATIVE" in s["label"] and "No real people" in s["prompt"] for s in ai)

    # description and compliance
    assert "not investment" in project["description"] and "AI-generated" in project["description"]
    assert all(s["source_url"] in project["description"] for c in project["charts"] for s in c["series"])
    by_id = {i["id"]: i["status"] for i in project["compliance"]["automatic"]}
    assert by_id == {"no_buy_sell": "pass", "no_price_targets": "pass", "no_promises": "pass", "disclaimer": "pass",
                     "ai_disclosed": "pass", "sources_listed": "pass", "numbers_traced": "pass", "news_flagged": "warn"}

    for name in ("project.json", "fact_sheet.md", "outline.md", "shot_list.md", "titles_and_thumbnails.md",
                 "youtube_description.txt", "compliance_checklist.md"):
        assert (folder / name).stat().st_size > 100


def test_every_number_in_the_wording_comes_from_the_fact_sheet(net, report_file):
    project = run(net)
    allowed = " ".join(f["claim"] + " " + f["value"] for f in project["facts"] if f["status"] != "verify")
    allowed_numbers = set(re.findall(r"\d[\d,]*\.?\d*", allowed))
    for text in all_wording(project):
        if text.startswith("[HEADLINE"):
            continue  # quotes a real headline verbatim, and tells the presenter to verify it
        stripped = re.sub(r"\[(CHART|HEADLINE|B-ROLL) \d+\]|401\(k\)|S&P 500|\d+-year|like I'm 12|You're 12", "", text)
        for number in re.findall(r"\d[\d,]*\.?\d*", stripped):
            assert number.rstrip(".,") in {n.rstrip(".,") for n in allowed_numbers}, f"{number!r} in {text!r} is not on the fact sheet"


def test_a_failed_source_is_skipped_not_invented(net, report_file):
    net.overrides["MSPUS"] = "observation_date,MSPUS\n"  # median home price comes back empty
    project = run(net)
    assert project["status"] == "ready"
    assert any("MSPUS" in w for w in project["warnings"])
    assert not any(f["key"] == "WALLET.mortgage_payment" for f in project["facts"])


def test_no_data_at_all_fails_loudly_instead_of_producing_an_empty_package(net, report_file):
    net.fail_hosts.add("fred.stlouisfed.org")
    with pytest.raises(RuntimeError, match="No chart data could be fetched"):
        run(net)
    saved = projects.list_projects()[0]
    assert saved["status"] == "error"


def test_custom_topic_without_a_report(net):
    project = run(net, report=False, topic="Why gas prices are rising")
    assert project["status"] == "ready" and project["plan"]["primary"] == "oil"
    assert not [f for f in project["facts"] if f["status"] == "verify"]
    assert next(i for i in project["compliance"]["automatic"] if i["id"] == "news_flagged")["status"] == "pass"


def test_llm_wording_cannot_smuggle_in_numbers_advice_or_real_people(net, report_file, monkeypatch):
    def fake_parse(settings, system, user, schema, max_tokens=16000):
        payload = json.loads(user[user.index("{"):])
        first = payload["facts"][0]["id"]
        assert "{F7}" in system and "never type a digit" in system
        return llm.Wording(
            hook=[f"Mortgage rates are now {{{first}}} [CHART 1]", "Experts say they will hit 9% by 2027"],
            what_happened=["Borrowing got pricier [HEADLINE 1]"],
            causes=[llm.Cause(cause="Yields rose", chart=1, bullets=[f"The key number is {{{first}}}"]),
                    llm.Cause(cause="Inflation", chart=99, bullets=["Prices rose 40% (made up)"])],
            mortgage=["Payments are up"], job=["Hiring slows"], groceries=["Food follows fuel"], retirement=["Stocks wobble"],
            watch_takeaway="Watch the next report", closing_line="That's the story", cta="Subscribe!",
            titles=[f"Mortgage Rates Hit {{{first}}}: Here's Why", "7 Reasons Rates Will Hit 10%", "You Should Buy Now Before Rates Drop",
                    "This Title Is Far Too Long To Ever Fit Inside The Sixty Character Limit For YouTube"],
            thumbnails=["RATES EXPLAINED", "THIS ONE HAS WAY TOO MANY WORDS"],
            broll=[llm.BrollIdea(section="hook", idea="houses", prompt="Aerial shot of a quiet suburb at sunset"),
                   llm.BrollIdea(section="why", idea="the Fed", prompt="Jerome Powell speaking at a press conference")],
            description_summary="Mortgage rates explained.",
        ), "claude-test"

    monkeypatch.setattr(llm, "_parse", fake_parse)
    settings = {**config.load_settings(), "ANTHROPIC_API_KEY": "sk-test"}
    project = run(net, settings=settings)

    assert project["llm_used"] is True and project["wording_source"] == "llm:claude-test"
    hook = [b["text"] for b in project["outline"]["hook"]["bullets"]]
    first_fact = project["facts"][0]
    assert first_fact["value"] in hook[0] and project["outline"]["hook"]["bullets"][0]["facts"] == [first_fact["id"]]
    assert "9%" not in hook[1] and "2027" not in hook[1] and REMOVED in hook[1]
    assert set(project["removed_numbers"]) >= {"9%", "2027", "40%"}
    assert project["outline"]["why"][1]["chart"] == 1  # a chart number that does not exist is corrected

    titles = project["titles"]
    assert len(titles) == 8 and titles[0].startswith("Mortgage Rates Hit " + first_fact["value"])
    assert not any("10%" in t or "Buy Now" in t or len(t) > 60 for t in titles)
    assert project["thumbnails"][0] == "RATES EXPLAINED" and all(len(t.split()) <= 4 for t in project["thumbnails"])

    blocked = [s for s in project["shots"] if s.get("blocked")]
    assert len(blocked) == 1 and blocked[0]["prompt"] == "" and "real person" in blocked[0]["note"]
    status = {i["id"]: i["status"] for i in project["compliance"]["automatic"]}
    assert status["numbers_traced"] == "warn" and status["ai_disclosed"] == "fail"
    assert project["compliance"]["summary"] == "fail"


def test_llm_failure_falls_back_to_templates(net, report_file, monkeypatch):
    def boom(*_args, **_kwargs):
        raise llm.LLMUnavailable("The Anthropic API key was rejected.")

    monkeypatch.setattr(llm, "_parse", boom)
    project = run(net, settings={**config.load_settings(), "ANTHROPIC_API_KEY": "sk-bad"})
    assert project["status"] == "ready" and project["llm_used"] is False
    assert any("key was rejected" in w for w in project["warnings"])


def test_transcript_upload_adds_a_clip_plan_and_zip_export_contains_everything(net, report_file):
    from tests.test_rules import SRT
    project = run(net)
    updated = pipeline.add_transcript(project["id"], "video.srt", SRT)
    assert len(updated["clips"]["clips"]) >= 3
    pipeline.set_manual_checks(project["id"], {"said_disclaimer": True})
    assert next(i for i in projects.load(project["id"])["compliance"]["manual"] if i["id"] == "said_disclaimer")["checked"]

    archive = zipfile.ZipFile(io.BytesIO(projects.zip_bytes(project["id"])))
    names = {n.split("/", 1)[1] for n in archive.namelist()}
    assert {"project.json", "fact_sheet.md", "outline.md", "shot_list.md", "youtube_description.txt",
            "compliance_checklist.md", "clip_plan.md", "transcript.srt"} <= names
    assert sum(1 for n in names if n.startswith("charts/") and n.endswith(".png")) == 2 * len(project["charts"])


def test_project_paths_cannot_escape_the_projects_folder(net, report_file):
    project = run(net)
    for bad in ("../secrets", "..", "a/b", ""):
        with pytest.raises(ValueError):
            projects.project_dir(bad)
    with pytest.raises(FileNotFoundError):
        projects.safe_file(project["id"], "../../.env")


def test_api_keys_are_saved_to_env_and_never_echoed(isolated):
    config.save_settings({"FRED_API_KEY": "abcdef0123456789abcdef0123456789", "CHART_THEME": "light", "NOT_A_SETTING": "x"})
    assert "abcdef0123456789abcdef0123456789" in (isolated / ".env").read_text()
    assert "NOT_A_SETTING" not in (isolated / ".env").read_text()
    public = config.public_settings()
    assert public["FRED_API_KEY"] == {"secret": True, "set": True, "hint": "...6789"}
    assert "abcdef" not in json.dumps(public)
    assert config.load_settings()["CHART_THEME"] == "light"
