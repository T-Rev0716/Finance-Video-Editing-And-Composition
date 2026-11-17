"""Pass B: fact-freeze diffing, learning log, local transcription, spoken fact-check,
dead-air stripping, 9:16 shorts, local Ollama wording and the topic-radar import."""
from __future__ import annotations

import io
import json
import sys
import types
import wave
import zipfile
from datetime import timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tests.conftest import TODAY, synthetic_csv
from tests.test_rules import SRT
from vps import (clips, config, fact_diff, graphics, learning_log, llm, media, pipeline, projects, recording_cards,
                 reports, server, thumbnails, transcribe)

needs_ffmpeg = pytest.mark.skipif(not media.ffmpeg_path(), reason="ffmpeg not installed")


# ================================================================ Upgrade 5: fact freeze and diff
def F(key, value, as_of="Nov 12, 2026", fact_id="F1", **extra):
    return {"id": fact_id, "key": key, "value": value, "as_of": as_of, "claim": f"It was {value}.", "status": "primary",
            "series_id": key.split(".")[0], "source_url": "https://x.test/" + key.split(".")[0], "source_name": "FRED (Test)", **extra}


def test_compute_diff_finds_new_data_revisions_and_missing_facts():
    frozen = [F("MORTGAGE30US.latest", "7.11%"), F("DGS10.latest", "5.15%", fact_id="F2"), F("UNRATE.latest", "4.1%", "October 2026", "F3"),
              F("SP500.latest", "7,417", fact_id="F4"), F("NEWS.1", "", "", "F5", status="verify")]
    live = [F("MORTGAGE30US.latest", "7.25%", "Nov 19, 2026"), F("DGS10.latest", "5.15%", fact_id="F9"),
            F("UNRATE.latest", "4.2%", "October 2026"), F("NEWS.1", "", "")]
    result = fact_diff.compute_diff(frozen, live)
    by_key = {c["key"]: c for c in result["changes"]}
    assert set(by_key) == {"MORTGAGE30US.latest", "UNRATE.latest"}, "unchanged facts and news are not listed"
    mortgage = by_key["MORTGAGE30US.latest"]
    assert (mortgage["fact_id"], mortgage["frozen_value"], mortgage["live_value"]) == ("F1", "7.11%", "7.25%")
    assert mortgage["delta"] == pytest.approx(0.14) and mortgage["delta_text"] == "+0.14 percentage points"
    assert mortgage["kind"] == "new_data" and mortgage["label"] == "30-year fixed mortgage rate"
    assert by_key["UNRATE.latest"]["kind"] == "revised", "same date, different value = a revision"
    assert [u["key"] for u in result["unavailable"]] == ["SP500.latest"]


@pytest.mark.parametrize("frozen,live,delta,text", [
    ("$2,117 a month", "$2,150 a month", 33, "+$33"),
    ("7,417", "7,300", -117, "-117"),
    ("up 0.89 percentage points in a year", "down 0.10 percentage points in a year", None, ""),
    ("highest since Oct 2007", "7.1%", None, ""),
])
def test_delta_only_when_both_values_have_the_same_shape(frozen, live, delta, text):
    assert fact_diff._delta(frozen, live) == (delta, text)


def changed_mortgage_csv(bump: float = 0.5) -> str:
    """The same series one week later: every old row unchanged, one new observation."""
    rows = synthetic_csv("MORTGAGE30US").strip().splitlines()
    last = float(rows[-1].split(",")[1])
    rows.append(f"{(TODAY + timedelta(days=1)).isoformat()},{last + bump:.3f}")
    return "\n".join(rows) + "\n"


def test_freeze_saves_facts_series_and_timestamps(project):
    pid = project["id"]
    snapshot = fact_diff.freeze(pid)
    saved = json.loads((projects.project_dir(pid) / "frozen_facts.json").read_text())
    assert saved["facts"] == project["facts"] and saved["frozen_at"] == snapshot["frozen_at"]
    assert saved["series"]["MORTGAGE30US"]["last_date"] == TODAY.isoformat() and saved["series"]["MORTGAGE30US"]["observations"] > 1000
    assert projects.load(pid)["fact_freeze"]["facts"] == len(project["facts"])
    again = fact_diff.ensure_frozen(pid, "card recorded")
    assert again["frozen_at"] == snapshot["frozen_at"], "an existing snapshot is not replaced automatically"


def test_checking_without_a_snapshot_is_refused(project):
    with pytest.raises(fact_diff.FactDiffError, match="Freeze the facts first"):
        fact_diff.check_changes(project["id"])


def test_no_changes_reported_when_nothing_moved(project, net):
    fact_diff.freeze(project["id"])
    report = fact_diff.check_changes(project["id"], today=TODAY)
    assert report["changes"] == [] and report["summary"].startswith("Nothing changed")


def test_changed_fact_is_traced_to_everything_that_uses_it(project, net):
    pid = project["id"]
    graphics.highlight_chart(pid, 1, "latest", "Where we are now")
    lead = next(f for f in project["facts"] if f["key"] == "MORTGAGE30US.latest")
    thumbnails.create(pid, {"layout": "big_stat_badge", "headline": "what changed", "fact_ids": [lead["id"]]})
    fact_diff.freeze(pid)
    before = json.dumps(projects.load(pid)["facts"])

    net.overrides["MORTGAGE30US"] = changed_mortgage_csv()
    report = fact_diff.check_changes(pid, today=TODAY + timedelta(days=1))
    change = next(c for c in report["changes"] if c["key"] == "MORTGAGE30US.latest")
    assert change["fact_id"] == lead["id"] and change["frozen_value"] == lead["value"] and change["live_value"] != lead["value"]
    assert change["delta"] == pytest.approx(0.5, abs=0.006) and change["kind"] == "new_data"
    affected = change["affected"]
    assert "hook" in [c["id"] for c in affected["cards"]]
    assert 1 in [c["n"] for c in affected["charts"]]
    assert [g["type"] for g in affected["graphics"]] == ["highlight"]
    assert [t["n"] for t in affected["thumbnails"]] == [1]
    assert any(lead["source_url"] in line["text"] for line in affected["description_lines"])
    assert all(c["decision"] is None for c in report["changes"])
    assert not any(c["key"].startswith("DGS2.") for c in report["changes"]), "untouched series are not reported"

    # checking changes nothing in the project: it only fills staging/
    assert json.dumps(projects.load(pid)["facts"]) == before
    assert (projects.project_dir(pid) / "staging" / "live.json").exists()
    assert fact_diff.last_report(pid)["checked_at"] == report["checked_at"]


def test_accept_new_value_flags_cards_for_retake_and_never_rewrites_wording(project, net):
    pid = project["id"]
    recording_cards.update_card(pid, "hook", {"text": "My own hook, in my own words, about {F1}."})
    recording_cards.set_status(pid, "hook", "recorded")
    graphics.highlight_chart(pid, 1, "latest", "Where we are now")
    fact_diff.freeze(pid)
    chart = projects.load(pid)["charts"][0]
    old_png = (projects.project_dir(pid) / "charts" / chart["files"]["1920x1080"]).read_bytes()
    old_value = next(f for f in project["facts"] if f["key"] == "MORTGAGE30US.latest")["value"]

    net.overrides["MORTGAGE30US"] = changed_mortgage_csv()
    report = fact_diff.check_changes(pid, today=TODAY + timedelta(days=1))
    keys = [c["key"] for c in report["changes"] if c["key"].startswith("MORTGAGE30US.")]
    resolved = fact_diff.resolve(pid, {key: "accept_new" for key in keys})

    after = projects.load(pid)
    new_value = next(f for f in after["facts"] if f["key"] == "MORTGAGE30US.latest")["value"]
    assert new_value != old_value and new_value == next(c for c in resolved["changes"] if c["key"] == "MORTGAGE30US.latest")["live_value"]
    hook = next(c for c in recording_cards.load(pid)["cards"] if c["id"] == "hook")
    assert hook["text"] == "My own hook, in my own words, about {F1}.", "the presenter's wording is untouched"
    assert hook["status"] == "needs_another_take"
    assert any(f["kind"] == "retake" and old_value in f["text"] and new_value in f["text"] for f in hook["flags"])
    assert after["graphics"][0]["stale"] is True
    assert (projects.project_dir(pid) / "charts" / chart["files"]["1920x1080"]).read_bytes() != old_png, "chart refreshed"
    assert after["charts"][0]["refreshed_at"]

    version = projects.project_dir(pid) / "versions" / resolved["last_version"]
    assert json.loads((version / "project.json").read_text())["facts"] == project["facts"], "the previous package is kept"
    assert (version / "charts" / chart["files"]["1920x1080"]).read_bytes() == old_png
    assert (version / "recording_cards.json").exists()
    assert all(c["decision"] == "accept_new" for c in resolved["changes"] if c["key"] in keys)

    # the accepted value is the new baseline: checking again reports nothing for it
    again = fact_diff.check_changes(pid, today=TODAY + timedelta(days=1))
    assert not [c for c in again["changes"] if c["key"] in keys]


def test_keep_frozen_value_adds_a_date_note_and_changes_no_numbers(project, net):
    pid = project["id"]
    fact_diff.freeze(pid)
    net.overrides["MORTGAGE30US"] = changed_mortgage_csv()
    report = fact_diff.check_changes(pid, today=TODAY + timedelta(days=1))
    change = next(c for c in report["changes"] if c["key"] == "MORTGAGE30US.latest")
    fact_diff.resolve(pid, {"MORTGAGE30US.latest": "keep_frozen"})

    after = projects.load(pid)
    assert next(f for f in after["facts"] if f["key"] == "MORTGAGE30US.latest")["value"] == change["frozen_value"]
    hook = next(c for c in recording_cards.load(pid)["cards"] if c["id"] == "hook")
    assert hook["status"] == "unrecorded" and hook["text"] == hook["original_text"]
    note = next(f for f in hook["flags"] if f["kind"] == "date_note")
    assert change["frozen_value"] in note["text"] and change["frozen_as_of"] in note["text"] and change["live_value"] in note["text"]
    assert "AS-RECORDED NOTE" in after["description"] and change["frozen_as_of"] in after["description"]
    assert "not investment" in after["description"], "the disclaimer is still there"
    assert (projects.project_dir(pid) / "youtube_description.txt").read_text() == after["description"]
    with pytest.raises(fact_diff.FactDiffError):
        fact_diff.resolve(pid, {"MORTGAGE30US.latest": "overwrite_everything"})
    with pytest.raises(fact_diff.FactDiffError):
        fact_diff.resolve(pid, {"NOT.a.key": "keep_frozen"})


def test_fact_freeze_api(project, net):
    client = TestClient(server.app)
    pid = project["id"]
    assert client.get(f"/api/projects/{pid}/fact-changes").json() == {"frozen": None, "report": None}
    assert client.post(f"/api/projects/{pid}/check-changes").status_code == 400
    frozen = client.post(f"/api/projects/{pid}/freeze-facts").json()
    assert frozen["facts"] == len(project["facts"]) and frozen["series"] >= 5
    net.overrides["MORTGAGE30US"] = changed_mortgage_csv()
    report = client.post(f"/api/projects/{pid}/check-changes").json()
    assert report["changes"], "the revised series shows up"
    key = report["changes"][0]["key"]
    done = client.post(f"/api/projects/{pid}/resolve-changes", json={"decisions": {key: "keep_frozen"}}).json()
    assert next(c for c in done["changes"] if c["key"] == key)["decision"] == "keep_frozen"
    assert client.get(f"/api/projects/{pid}/fact-changes").json()["frozen"]["facts"] == len(project["facts"])


# ================================================================ Upgrade 6: learning log
def episode(i, **values):
    base = {"project_id": f"p{i}", "topic": f"Topic {i}", "created": f"2026-10-{i + 1:02d}", "hook_text": "Rates are 7% now.",
            "hook_structure": "leads with a number", "final_title": f"Title {i}", "thumbnail_layout": "big_stat_badge",
            "topic_family": "housing", "open_lane": i % 2 == 0, "total_minutes": 100 + i * 10, "views_48h": 1000 + i,
            "views_7d": 2000 + i * 100, "ctr_pct": 4.0 + i * 0.1, "avg_view_duration_sec": 200 + i}
    return {**base, **values}


def test_learning_log_saves_one_record_in_both_places(project, isolated):
    pid = project["id"]
    start = learning_log.load(pid)
    assert start["topic_family"] == "housing" and start["open_lane"] is True and start["final_title"] == project["titles"][0]
    assert start["hook_text"].startswith("- ") and start["views_7d"] is None
    thumbnails.create(pid, {"layout": "split_comparison", "headline": "what changed", "preset": "Red alert",
                            "fact_ids": [f["id"] for f in project["facts"] if f["value"] and f["status"] != "verify"][:2]})
    record = learning_log.save(pid, {
        "hook_text": "Why did your mortgage just get pricier?", "final_title": "Mortgage Rates, Explained", "published_date": "2026-11-18",
        "prep_minutes": "45", "recording_minutes": 30, "editing_minutes": 120.4, "views_48h": "1200", "views_7d": 5400,
        "ctr_pct": "6.3", "avg_view_duration_sec": 251, "retention_notes": "Dip at the second chart.", "audience_comments_notes": "Asked for a follow-up."})
    assert record["total_minutes"] == 195 and record["ctr_pct"] == 6.3 and record["views_48h"] == 1200
    assert record["hook_structure"] == "question" and record["thumbnail_layout"] == "split_comparison" and record["thumbnail_preset"] == "Red alert"
    assert json.loads((projects.project_dir(pid) / "learning_log.json").read_text())["final_title"] == "Mortgage Rates, Explained"
    index = json.loads((isolated / "userdata" / "learning_log.json").read_text())
    assert [r["project_id"] for r in index] == [pid]
    learning_log.save(pid, {"views_7d": 6000})
    assert len(learning_log.read_index()) == 1 and learning_log.read_index()[0]["views_7d"] == 6000, "re-saving updates, never duplicates"
    for bad in ({"views_7d": -5}, {"ctr_pct": 140}, {"prep_minutes": "soon"}):
        with pytest.raises(ValueError):
            learning_log.save(pid, bad)


def test_small_samples_are_labelled_tentative_and_there_is_no_score():
    three = learning_log.summarize([episode(i) for i in range(3)])
    assert three["count"] == 3 and three["observations"]
    for observation in three["observations"]:
        assert observation["tentative"] is True
        assert observation["label"] == f"TENTATIVE — small sample size ({observation['n']} episodes)"
    build = next(o for o in three["observations"] if o["title"] == "Median build time")
    assert build["text"].startswith("110 minutes") and build["n"] == 3
    assert "score" not in json.dumps(three).replace("no viral score", "").lower()
    assert "viral" not in json.dumps(three["observations"]).lower()

    eight = learning_log.summarize([episode(i) for i in range(8)])
    assert all(not o["tentative"] and o["label"] == "Based on 8 episodes" for o in eight["observations"])
    assert learning_log.summarize([])["observations"] == []
    one = learning_log.summarize([episode(0)])
    assert one["observations"][0]["label"] == "TENTATIVE — small sample size (1 episode)"


def test_observations_are_plain_medians_of_what_was_logged():
    records = [episode(0, thumbnail_layout="big_stat_badge", ctr_pct=4.0), episode(1, thumbnail_layout="big_stat_badge", ctr_pct=6.0),
               episode(2, thumbnail_layout="split_comparison", ctr_pct=9.0), episode(3, thumbnail_layout="minimal_editorial", ctr_pct=None),
               episode(4, hook_text="Why now?", hook_structure="question", avg_view_duration_sec=400, ctr_pct=None)]
    summary = learning_log.summarize(records)
    by_title = {o["title"]: o for o in summary["observations"]}
    layout = by_title["Thumbnail layout with the highest click-through"]
    assert "'split_comparison': 9.0% median click-through rate across 1 episode" in layout["text"] and layout["n"] == 3
    assert "'question': 400 seconds" in by_title["Hook structure with the longest average view"]["text"]
    assert "Open lane" in by_title["Open-lane topics vs crowded topics"]["text"]
    assert [e["project_id"] for e in summary["episodes"]] == ["p4", "p3", "p2", "p1", "p0"], "newest first"


@pytest.mark.parametrize("hook,expected", [
    ("Why did your mortgage just get more expensive?", "question"),
    ("Mortgage rates are 7.11% as of today.", "leads with a number"),
    ("The bond market just did something strange.", "statement"),
])
def test_hook_structure_is_a_transparent_rule(hook, expected):
    assert learning_log.hook_structure(hook) == expected


def test_learning_log_api(project):
    client = TestClient(server.app)
    pid = project["id"]
    assert client.get(f"/api/projects/{pid}/learning-log").json()["topic"] == project["topic"]
    saved = client.post(f"/api/projects/{pid}/learning-log", json={"prep_minutes": 20, "editing_minutes": 60, "views_7d": 900}).json()
    assert saved["total_minutes"] == 80
    assert client.post(f"/api/projects/{pid}/learning-log", json={"ctr_pct": 500}).status_code == 400
    summary = client.get("/api/learning-log").json()
    assert summary["count"] == 1 and all(o["label"].startswith("TENTATIVE") for o in summary["observations"])


# ================================================================ Upgrade 7: spoken fact-check
FACTS = [
    {"id": "F1", "status": "primary", "claim": "The average 30-year fixed mortgage rate was 7.11% as of Nov 12, 2026.", "value": "7.11%", "as_of": "Nov 12, 2026"},
    {"id": "F2", "status": "calculated", "claim": "A $314,640 loan costs about $2,117 a month at 7.11%.", "value": "$2,117 a month", "as_of": "Nov 12, 2026"},
    {"id": "F3", "status": "verify", "claim": "Reported: rates hit 9.5%", "value": "", "as_of": ""},
]


@pytest.mark.parametrize("text,expected", [
    ("Rates are seven point one one percent today", [("seven point one one percent", 7.11, "%")]),
    ("It costs $2,117 a month", [("$2,117", 2117.0, "$")]),
    ("up from six percent to 7.5%", [("six percent", 6.0, "%"), ("7.5%", 7.5, "%")]),
    ("a hundred and fifty thousand dollars", [("a hundred and fifty thousand dollars", 150000.0, "$")]),
    ("back in twenty twenty two and in 2008", [("twenty twenty two", 2022.0, ""), ("2008", 2008.0, "")]),
    ("three reasons this one matters for your 401k and the 10-year", []),
])
def test_spoken_numbers_are_found_as_digits_or_words(text, expected):
    assert [(n["spoken"], n["value"], n["unit"]) for n in clips.spoken_numbers(text)] == expected


def test_spoken_fact_check_flags_numbers_that_are_not_on_the_sheet():
    segments = [
        {"start": 4.0, "end": 9.0, "text": "Mortgage rates are seven point one one percent, call it about 7 percent."},
        {"start": 42.5, "end": 50.0, "text": "Some people say nine and a half percent is coming, maybe 9.5% by spring."},
        {"start": 71.0, "end": 78.0, "text": "On that loan it's $2,117 a month. Three reasons why. And the 12 here is a day, not a rate: 12 percent."},
    ]
    result = clips.spoken_fact_check(segments, FACTS)
    by_spoken = {f["spoken"]: f for f in result["flags"]}
    assert "seven point one one percent" not in by_spoken and "$2,117" not in by_spoken, "exact matches are not flagged"
    rounded = by_spoken["7 percent"]
    assert rounded["status"] == "rounded" and rounded["fact_id"] == "F1" and rounded["time"] == "0:04"
    unverified = by_spoken["9.5%"]
    assert unverified["status"] == "unverified" and unverified["time"] == "0:42" and unverified["seconds"] == 42.5
    assert "news" not in unverified["note"] and unverified["text"].startswith("Some people say"), "a news-only number does not count as verified"
    assert by_spoken["12 percent"]["status"] == "unverified", "the 12 in 'Nov 12' does not verify a spoken 12 percent"
    assert result["unverified"] == sum(1 for f in result["flags"] if f["status"] == "unverified") >= 2
    assert result["matched"] == 2 and "not on the fact sheet" in result["summary"]


def test_uploading_a_transcript_runs_the_spoken_check(project):
    value = project["facts"][0]["value"]
    srt = SRT.replace("Mortgage rates just went back above seven percent.", f"Mortgage rates are {value} and maybe 13.9% soon.")
    updated = pipeline.add_transcript(project["id"], "video.srt", srt)
    check = updated["spoken_check"]
    assert [f["spoken"] for f in check["flags"] if f["status"] == "unverified"] == ["13.9%"]
    assert check["flags"][0]["time"] == "0:00" and check["matched"] >= 1


# ================================================================ Upgrade 7: transcription
def test_transcribe_uses_faster_whisper_when_installed(monkeypatch, tmp_path):
    calls = {}

    class FakeModel:
        def __init__(self, name, device, compute_type):
            calls.update(name=name, device=device, compute_type=compute_type)

        def transcribe(self, path, vad_filter):
            calls.update(path=path, vad=vad_filter)
            segment = lambda a, b, t: types.SimpleNamespace(start=a, end=b, text=t)  # noqa: E731
            return iter([segment(0.0, 2.5, " Mortgage rates are 7.11%. "), segment(2.5, 4.0, "   "), segment(4.0, 6.25, "Here's why.")]), types.SimpleNamespace(duration=6.25)

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setattr(transcribe, "_cuda_available", lambda: True)
    segments, label = transcribe.transcribe(tmp_path / "take1.mp4", "auto")
    assert calls == {"name": "large-v3", "device": "cuda", "compute_type": "float16", "path": str(tmp_path / "take1.mp4"), "vad": True}
    assert label == "large-v3 on GPU" and [s["text"] for s in segments] == ["Mortgage rates are 7.11%.", "Here's why."]
    srt = transcribe.segments_to_srt(segments)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:02,500\nMortgage rates are 7.11%.\n") and "00:00:04,000 --> 00:00:06,250" in srt
    assert clips.parse_srt(srt)[1]["start"] == 4.0, "the transcript round-trips through the SRT parser"

    monkeypatch.setattr(transcribe, "_cuda_available", lambda: False)
    transcribe.transcribe(tmp_path / "take1.mp4", "auto")
    assert (calls["name"], calls["device"], calls["compute_type"]) == ("small", "cpu", "int8"), "CPU fallback"
    assert transcribe.capabilities()["faster_whisper"] is True


def test_transcribe_without_faster_whisper_says_what_to_do(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # makes "import faster_whisper" fail
    with pytest.raises(transcribe.Unavailable, match="pip install faster-whisper"):
        transcribe.transcribe(tmp_path / "take1.mp4")
    caps = transcribe.capabilities()
    assert caps["faster_whisper"] is False and ".srt" in caps["transcribe_note"]


def make_wav(path, parts, rate=8000):
    """parts: [(seconds, loud?)] -> a 16-bit mono wav with tone and silence."""
    chunks = []
    for seconds, loud in parts:
        t = np.arange(int(seconds * rate)) / rate
        chunks.append((np.sin(2 * np.pi * 440 * t) * (12000 if loud else 0)).astype("<i2"))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(np.concatenate(chunks).tobytes())


def test_recording_can_be_uploaded_or_used_in_place(project, tmp_path):
    pid = project["id"]
    wav = tmp_path / "raw take.wav"
    make_wav(wav, [(0.5, True)])
    in_place = transcribe.add_path(pid, f'"{wav}"')
    assert in_place["source"] == "path" and in_place["path"] == str(wav.resolve()) and in_place["has_video"] is False
    uploaded = transcribe.add_upload(pid, "Raw Take 2.WAV", io.BytesIO(wav.read_bytes()))
    assert uploaded["source"] == "upload" and (projects.project_dir(pid) / "recording" / "Raw-Take-2.wav").exists()
    for call in (lambda: transcribe.add_upload(pid, "notes.docx", io.BytesIO(b"x")), lambda: transcribe.add_path(pid, str(tmp_path / "missing.mp4")),
                 lambda: transcribe.add_upload(pid, "empty.mp4", io.BytesIO(b""))):
        with pytest.raises(transcribe.Unavailable):
            call()
    names = zipfile.ZipFile(io.BytesIO(projects.zip_bytes(pid))).namelist()
    assert not any("/recording/" in n for n in names), "raw recordings stay out of the ZIP export"


# ================================================================ Upgrade 7: dead air
def test_silencedetect_output_is_parsed():
    log = """[silencedetect @ 0x1] silence_start: 1.5
[silencedetect @ 0x1] silence_end: 2.75 | silence_duration: 1.25
frame=  100 fps=0.0
[silencedetect @ 0x1] silence_start: -0.01
[silencedetect @ 0x1] silence_end: 9.2 | silence_duration: 0.6
[silencedetect @ 0x1] silence_start: 20.0"""
    assert transcribe.parse_silencedetect(log) == [(1.5, 2.75), (0.0, 9.2)]


def test_keep_segments_leave_a_breath_around_speech():
    keeps = transcribe.keep_segments([(1.0, 2.0), (5.0, 5.1), (9.0, 10.0)], 10.0, pad=0.08)
    assert keeps == [(0.0, 1.08), (1.92, 9.08), (9.92, 10.0)], "a gap too short to be worth cutting is left alone"
    assert transcribe.keep_segments([], 12.5) == [(0.0, 12.5)]
    assert round(sum(b - a for a, b in keeps), 2) == 10.0 - 0.84 * 2


def test_dead_air_is_stripped_with_the_wave_fallback_when_ffmpeg_is_missing(project, tmp_path, monkeypatch):
    monkeypatch.setattr(media, "ffmpeg_path", lambda: None)
    monkeypatch.setattr(media, "ffprobe_path", lambda: None)
    wav = tmp_path / "take.wav"
    make_wav(wav, [(1.0, True), (1.2, False), (1.0, True), (0.3, False), (1.0, True)])
    transcribe.add_path(project["id"], str(wav))
    result = transcribe.strip_dead_air(project["id"], 0.45)
    assert result["method"] == "wave" and result["silences"] == 1, "the 0.3 s pause is shorter than 0.45 s and is kept"
    assert result["removed_seconds"] == pytest.approx(1.2 - 2 * transcribe.KEEP_PAD, abs=0.05)
    out = projects.project_dir(project["id"]) / result["file"]
    with wave.open(str(out), "rb") as tight:
        assert tight.getnframes() / tight.getframerate() == pytest.approx(4.5 - result["removed_seconds"], abs=0.05)
    assert wav.stat().st_size > out.stat().st_size, "the original is untouched and longer"
    cut_list = json.loads((projects.project_dir(project["id"]) / "recording" / "cut_list.json").read_text())
    assert len(cut_list["keep"]) == 2 and projects.load(project["id"])["dead_air"]["file"] == result["file"]

    mp3 = tmp_path / "take.mp3"
    mp3.write_bytes(b"not really an mp3")
    transcribe.add_path(project["id"], str(mp3))
    with pytest.raises(transcribe.Unavailable, match="needs ffmpeg"):
        transcribe.strip_dead_air(project["id"])


@needs_ffmpeg
def test_dead_air_is_stripped_with_ffmpeg(project, tmp_path):
    wav = tmp_path / "take.wav"
    make_wav(wav, [(1.0, True), (1.5, False), (1.0, True)])
    transcribe.add_path(project["id"], str(wav))
    result = transcribe.strip_dead_air(project["id"], 0.45)
    assert result["method"] == "ffmpeg" and result["silences"] == 1 and result["file"].endswith("_tight.wav")
    tight = media.probe(str(projects.project_dir(project["id"]) / result["file"]))["duration"]
    assert tight == pytest.approx(3.5 - result["removed_seconds"], abs=0.1) and 1.9 < tight < 2.4


def test_trim_command_and_long_filters():
    keeps = [(0.0, 1.5), (2.0, 4.25)]
    cmd = transcribe.trim_command(__import__("pathlib").Path("in.mp4"), keeps, __import__("pathlib").Path("out.mp4"), has_video=True)
    assert "select='between(t,0.000,1.500)+between(t,2.000,4.250)',setpts=N/FRAME_RATE/TB" in cmd
    assert "aselect='between(t,0.000,1.500)+between(t,2.000,4.250)',asetpts=N/SR/TB" in cmd and cmd[-1] == "out.mp4"
    audio = transcribe.trim_command(__import__("pathlib").Path("in.wav"), keeps, __import__("pathlib").Path("out.wav"), has_video=False)
    assert "-vf" not in audio and "libx264" not in audio


# ================================================================ Upgrade 7: 9:16 shorts
SEGMENTS = [{"start": 10.0, "end": 14.0, "text": "one two three four five six seven eight"},
            {"start": 14.0, "end": 16.0, "text": "nine ten"}, {"start": 30.0, "end": 31.0, "text": "later"}]


def test_caption_chunks_are_timed_from_the_transcript():
    chunks = clips.caption_chunks(SEGMENTS, 10.0, 16.0, max_words=5)
    assert chunks == [{"start": 0.0, "end": 2.5, "text": "one two three four five"}, {"start": 2.5, "end": 4.0, "text": "six seven eight"},
                      {"start": 4.0, "end": 6.0, "text": "nine ten"}]
    assert clips.caption_chunks(SEGMENTS, 12.0, 15.0)[0] == {"start": 0.0, "end": 0.5, "text": "one two three four five"}
    assert clips.caption_chunks(SEGMENTS, 20.0, 25.0) == []


def test_short_command_layouts():
    from pathlib import Path
    captions = [{"start": 0.0, "end": 1.5, "text": "a"}, {"start": 1.5, "end": 3.0, "text": "b"}]
    files = [Path("c0.png"), Path("c1.png")]
    stacked = transcribe.short_command(Path("raw.mp4"), 12.0, 30.0, Path("out.mp4"), captions, files, Path("chart.png"), has_video=True)
    graph = stacked[stacked.index("-filter_complex") + 1]
    assert stacked[stacked.index("-ss") + 1] == "12.000" and stacked[stacked.index("-t") + 1] == "30.000"
    assert "color=c=0x1a1a19:s=1080x1920" in graph and "scale=1080:608" in graph and "scale=1080:1080" in graph
    assert "[v0][2:v]overlay=0:1500:enable='between(t,0.00,1.50)'[v1]" in graph and "[v1][3:v]overlay=0:1500:enable='between(t,1.50,3.00)'[v2]" in graph
    assert stacked[stacked.index("-map") + 1] == "[v2]" and "0:a?" in stacked and stacked[-1] == "out.mp4"

    full = transcribe.short_command(Path("raw.mp4"), 0, 30, Path("out.mp4"), [], [], None, has_video=True)
    assert "crop=1080:1920" in full[full.index("-filter_complex") + 1] and full[full.index("-map") + 1] == "[v0]"
    audio_only = transcribe.short_command(Path("raw.wav"), 0, 30, Path("out.mp4"), [], [], Path("chart_v.png"), has_video=False)
    assert "force_original_aspect_ratio=decrease" in audio_only[audio_only.index("-filter_complex") + 1]


def with_clip(project, start=0.0, end=3.0):
    pipeline.add_transcript(project["id"], "video.srt", SRT)
    saved = projects.load(project["id"])
    saved["clips"]["clips"] = [{**saved["clips"]["clips"][0], "n": 1, "start_seconds": start, "end_seconds": end}]
    projects.save(saved)


def test_short_export_without_ffmpeg_saves_captions_and_cut_times(project, tmp_path, monkeypatch):
    monkeypatch.setattr(media, "ffmpeg_path", lambda: None)
    monkeypatch.setattr(media, "ffprobe_path", lambda: None)
    with_clip(project, 0.0, 40.0)
    result = transcribe.export_short(project["id"], 1)
    assert result["file"] == "" and "Add your recording first" in result["note"]
    captions = (projects.project_dir(project["id"]) / result["captions_file"]).read_text()
    assert "Mortgage rates just went back" in captions and "-->" in captions
    wav = tmp_path / "take.wav"
    make_wav(wav, [(1.0, True)])
    transcribe.add_path(project["id"], str(wav))
    result = transcribe.export_short(project["id"], 1, chart_n=1)
    assert result["file"] == "" and "ffmpeg is not installed" in result["note"] and "0:00 to 0:40" in result["note"]
    assert projects.load(project["id"])["shorts"][0]["clip"] == 1
    with pytest.raises(transcribe.Unavailable, match="not in the clip plan"):
        transcribe.export_short(project["id"], 9)


@needs_ffmpeg
def test_short_export_with_ffmpeg_makes_a_1080x1920_mp4(project, tmp_path):
    raw = tmp_path / "raw.mp4"
    media.run([media.ffmpeg_path(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=15",
               "-f", "lavfi", "-i", "sine=frequency=440", "-t", "4", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
               "-c:a", "aac", str(raw)])
    transcribe.add_path(project["id"], str(raw))
    assert projects.load(project["id"])["recording"]["has_video"] is True
    with_clip(project, 0.5, 3.5)
    for chart_n in (1, None):
        result = transcribe.export_short(project["id"], 1, chart_n=chart_n)
        assert result["note"] == "" and result["file"] == "shorts/clip_01_9x16.mp4" and result["captions"] >= 1
        info = media.probe(str(projects.project_dir(project["id"]) / result["file"]))
        assert (info["width"], info["height"]) == (1080, 1920) and info["has_audio"] and info["duration"] == pytest.approx(3.0, abs=0.2)
    assert not (projects.project_dir(project["id"]) / "shorts" / "clip_01_captions").exists(), "temporary caption images are cleaned up"


def test_post_production_api(project, tmp_path, monkeypatch):
    client = TestClient(server.app)
    pid = project["id"]
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    caps = client.get("/api/capabilities").json()
    assert caps["faster_whisper"] is False and "pip install faster-whisper" in caps["transcribe_note"]
    assert client.post(f"/api/projects/{pid}/transcribe").status_code == 400, "no recording yet"
    wav = tmp_path / "take.wav"
    make_wav(wav, [(1.0, True), (1.0, False), (1.0, True)])
    assert client.post(f"/api/projects/{pid}/recording-path", json={"path": str(wav)}).json()["name"] == "take.wav"
    assert client.post(f"/api/projects/{pid}/recording-path", json={"path": str(tmp_path / "nope.mp4")}).status_code == 400
    uploaded = client.post(f"/api/projects/{pid}/recording", files={"file": ("take2.wav", wav.read_bytes(), "audio/wav")})
    assert uploaded.status_code == 200 and uploaded.json()["source"] == "upload"
    assert client.post(f"/api/projects/{pid}/recording", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 400
    refused = client.post(f"/api/projects/{pid}/transcribe")
    assert refused.status_code == 400 and "faster-whisper" in refused.json()["detail"]
    stripped = client.post(f"/api/projects/{pid}/strip-dead-air", json={"min_silence": 0.45}).json()
    assert stripped["silences"] == 1 and stripped["file"]
    assert client.post(f"/api/projects/{pid}/strip-dead-air", json={"min_silence": 0.01}).status_code == 400
    client.post(f"/api/projects/{pid}/transcript", files={"file": ("video.srt", SRT, "text/plain")})
    assert client.get(f"/api/projects/{pid}").json()["spoken_check"]["checked"] >= 0
    assert client.post(f"/api/projects/{pid}/clips/1/short", json={"chart_n": None}).status_code == 200
    assert client.post(f"/api/projects/{pid}/clips/99/short", json={}).status_code == 400


def test_transcription_job_runs_in_the_background(project, tmp_path, monkeypatch):
    import time

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, path, vad_filter):
            parsed = clips.parse_srt(SRT)
            return iter([types.SimpleNamespace(start=s["start"], end=s["end"], text=s["text"]) for s in parsed]), types.SimpleNamespace(duration=130)

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setattr(transcribe, "_cuda_available", lambda: False)
    wav = tmp_path / "take.wav"
    make_wav(wav, [(0.5, True)])
    client = TestClient(server.app)
    pid = project["id"]
    client.post(f"/api/projects/{pid}/recording-path", json={"path": str(wav)})
    assert client.post(f"/api/projects/{pid}/transcribe").json() == {"started": True}
    for _ in range(100):
        progress = client.get(f"/api/projects/{pid}/transcribe/progress").json()
        if progress["done"]:
            break
        time.sleep(0.05)
    assert progress["done"] and progress["error"] == "" and any("small on CPU" in step for step in progress["steps"])
    done = client.get(f"/api/projects/{pid}").json()
    assert len(done["clips"]["clips"]) >= 3 and "spoken_check" in done
    assert (projects.project_dir(pid) / "transcript.srt").read_text().startswith("1\n00:00:00,000")


# ================================================================ Upgrade 7: local Ollama wording
def ollama_wording(first_fact: str) -> dict:
    return {
        "hook": [f"Mortgage rates are now {{{first_fact}}} [CHART 1]", "They could reach 9% by 2027"],
        "what_happened": ["Borrowing got pricier [HEADLINE 1]"],
        "causes": [{"cause": "Yields rose", "chart": 1, "bullets": [f"The key number is {{{first_fact}}}"]},
                   {"cause": "Inflation", "chart": 2, "bullets": ["Prices rose 40 percent (made up)"]}],
        "mortgage": ["Payments are up"], "job": ["Hiring slows"], "groceries": ["Food follows fuel"], "retirement": ["Stocks wobble"],
        "watch_takeaway": "Watch the next report", "closing_line": "That's the story", "cta": "Subscribe!",
        "titles": [f"Mortgage Rates Hit {{{first_fact}}}: Here's Why", "5 Reasons Rates Will Hit 10%", "You Should Buy Now Before Rates Drop"],
        "thumbnails": ["RATES EXPLAINED"],
        "broll": [{"section": "hook", "idea": "houses", "prompt": "Aerial shot of a quiet suburb at sunset"},
                  {"section": "why", "idea": "the Fed", "prompt": "Jerome Powell at a press conference"}],
        "description_summary": "Mortgage rates explained.",
    }


def test_provider_selection():
    assert llm.provider({"LLM_PROVIDER": "auto", "ANTHROPIC_API_KEY": ""}) == "templates"
    assert llm.provider({"LLM_PROVIDER": "auto", "ANTHROPIC_API_KEY": "sk"}) == "anthropic"
    assert llm.provider({"LLM_PROVIDER": "ollama", "ANTHROPIC_API_KEY": "sk"}) == "ollama"
    assert llm.provider({"LLM_PROVIDER": "templates", "ANTHROPIC_API_KEY": "sk"}) == "templates"
    assert llm.provider({}) == "templates"


def test_ollama_wording_goes_through_the_same_number_guard_and_compliance(net, report_file, monkeypatch):
    calls = []

    def fake_ollama(url, payload=None, timeout=600.0):
        calls.append((url, payload))
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3:8b"}, {"name": "qwen-local:latest"}]}
        facts = json.loads(payload["messages"][1]["content"].split("\n\n", 1)[1])["facts"]
        return {"message": {"role": "assistant", "content": json.dumps(ollama_wording(facts[0]["id"]))}}

    monkeypatch.setattr(llm, "_ollama_request", fake_ollama)
    settings = {**config.load_settings(), "LLM_PROVIDER": "ollama", "OLLAMA_URL": "http://127.0.0.1:11434/"}
    report = reports.latest_report()
    theme = report["themes"][0]
    project = pipeline.generate(projects.new_project_id(theme["theme"]), theme["theme"], theme, report, settings=settings, today=TODAY)

    chat_url, payload = calls[-1]
    assert chat_url == "http://127.0.0.1:11434/api/chat" and payload["model"] == "qwen-local:latest", "prefers an installed qwen model"
    assert payload["stream"] is False and payload["format"]["type"] == "object" and "never type a digit" in payload["messages"][0]["content"]
    assert all("anthropic" not in url for url, _ in calls)

    assert project["llm_used"] is True and project["wording_source"] == "llm:ollama/qwen-local:latest"
    first = project["facts"][0]
    hook = [b["text"] for b in project["outline"]["hook"]["bullets"]]
    assert first["value"] in hook[0] and "9%" not in hook[1] and "2027" not in hook[1]
    assert {"9%", "2027", "40 percent"} <= set(project["removed_numbers"])
    assert len(project["titles"]) == 8 and not any("10%" in t or "Buy Now" in t for t in project["titles"])
    blocked = [s for s in project["shots"] if s.get("blocked")]
    assert len(blocked) == 1 and blocked[0]["prompt"] == ""
    status = {i["id"]: i["status"] for i in project["compliance"]["automatic"]}
    assert status["numbers_traced"] == "warn" and status["ai_disclosed"] == "fail"


def test_named_ollama_model_is_used_and_failures_fall_back_to_templates(net, report_file, monkeypatch):
    seen = []

    def down(url, payload=None, timeout=600.0):
        seen.append((url, (payload or {}).get("model")))
        raise llm.LLMUnavailable("Could not reach Ollama. Start it (run 'ollama serve') and check the address in Settings.")

    monkeypatch.setattr(llm, "_ollama_request", down)
    settings = {**config.load_settings(), "LLM_PROVIDER": "ollama", "OLLAMA_MODEL": "my-qwen:tag"}
    report = reports.latest_report()
    theme = report["themes"][0]
    project = pipeline.generate(projects.new_project_id(theme["theme"]), theme["theme"], theme, report, settings=settings, today=TODAY)
    assert seen == [("http://127.0.0.1:11434/api/chat", "my-qwen:tag")], "a named model is used as-is, with no model listing call"
    assert project["status"] == "ready" and project["llm_used"] is False
    assert any("Could not reach Ollama" in w for w in project["warnings"])

    monkeypatch.setattr(llm, "_ollama_request", lambda url, payload=None, timeout=600.0: {"message": {"content": "sure! here you go"}})
    with pytest.raises(llm.LLMUnavailable, match="expected format"):
        llm._parse(settings, "system", "user", llm.Wording)
    monkeypatch.setattr(llm, "_ollama_request", lambda url, payload=None, timeout=600.0: {"models": []})
    with pytest.raises(llm.LLMUnavailable, match="no models installed"):
        llm._ollama_model({"OLLAMA_URL": "http://127.0.0.1:11434"})


def test_ollama_settings_and_model_list_api(isolated, monkeypatch):
    client = TestClient(server.app)
    saved = client.post("/api/settings", json={"values": {"LLM_PROVIDER": "ollama", "OLLAMA_MODEL": "qwen-test", "OLLAMA_URL": "http://127.0.0.1:11434"}}).json()
    assert saved["settings"]["LLM_PROVIDER"]["value"] == "ollama" and saved["settings"]["OLLAMA_MODEL"]["value"] == "qwen-test"
    assert client.get("/api/state").json()["wording_engine"] == "ollama"
    client.post("/api/settings", json={"values": {"LLM_PROVIDER": "chatgpt"}})
    assert client.get("/api/settings").json()["settings"]["LLM_PROVIDER"]["value"] == "ollama", "an unknown engine is ignored"
    monkeypatch.setattr(llm, "_ollama_request", lambda url, payload=None, timeout=600.0: {"models": [{"name": "qwen-test"}]})
    assert client.get("/api/ollama/models").json() == {"ok": True, "models": ["qwen-test"]}

    def down(url, payload=None, timeout=600.0):
        raise llm.LLMUnavailable("Could not reach Ollama.")

    monkeypatch.setattr(llm, "_ollama_request", down)
    assert client.get("/api/ollama/models").json() == {"ok": False, "models": [], "message": "Could not reach Ollama."}


# ================================================================ Upgrade 7: topic radar import
def test_import_latest_radar_report(isolated, tmp_path):
    radar = tmp_path / "topic-radar" / "reports"
    radar.mkdir(parents=True)
    (radar / "2026-11-15.json").write_text(json.dumps({"themes": [{"theme": "Old", "score": 5}]}))
    (radar / "2026-11-17.json").write_text(json.dumps({"themes": [{"theme": "Newest radar theme", "score": 80}, {"theme": "Second", "score": 60}]}))
    (radar / "notes.txt").write_text("ignore me")
    result = reports.import_latest_radar(str(radar))
    assert result["status"] == "imported" and result["file"] == "2026-11-17.json" and result["themes"] == 2
    assert reports.latest_report()["themes"][0]["theme"] == "Newest radar theme"
    assert not (isolated / "reports" / "2026-11-15.json").exists(), "only the newest report is copied"
    assert reports.import_latest_radar(str(radar))["status"] == "already_current"

    (radar / "2026-11-18.json").write_text("{broken")
    with pytest.raises(reports.RadarImportError, match="could not be read"):
        reports.import_latest_radar(str(radar))
    with pytest.raises(reports.RadarImportError, match="not found"):
        reports.import_latest_radar(str(tmp_path / "nowhere"))
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(reports.RadarImportError, match="No .json reports"):
        reports.import_latest_radar(str(empty))


def test_radar_import_api_uses_the_folder_from_settings(isolated, tmp_path):
    client = TestClient(server.app)
    assert config.load_settings()["RADAR_REPORTS_DIR"].endswith("topic-radar\\reports"), "defaults to the user's radar folder"
    missing = client.post("/api/reports/refresh")
    assert missing.status_code == 400 and "Set it in Settings" in missing.json()["detail"]
    radar = tmp_path / "radar"
    radar.mkdir()
    (radar / "2026-11-17.json").write_text(json.dumps({"themes": [{"theme": "From the radar", "score": 9}]}))
    client.post("/api/settings", json={"values": {"RADAR_REPORTS_DIR": str(radar)}})
    assert client.post("/api/reports/refresh").json()["status"] == "imported"
    assert client.get("/api/state").json()["report"]["themes"][0]["theme"] == "From the radar"
