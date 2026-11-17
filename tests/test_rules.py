"""Reports, topic planning, compliance and the clip planner."""
from __future__ import annotations

import pytest

from vps import clips, compliance, reports, topics


# ---------- reports ----------
def test_report_is_normalised_and_sorted_by_score(report_file):
    report = reports.latest_report()
    assert [t["theme"] for t in report["themes"]] == ["Mortgage rates climb as Treasury yields rise", "Low score theme"]
    top = report["themes"][0]
    assert top["open_lane"] is True
    assert top["headlines"][0] == {"title": "Mortgage rates hit 7.2%, highest this year", "url": "https://news.example/a", "source": "news.example"}
    assert top["competitor_videos"][0]["views"] == 1_200_000
    assert top["competitor_videos"][0]["url"] == "https://www.youtube.com/watch?v=abc123"
    assert report["themes"][1]["headlines"][0]["title"] == "Just a string headline"
    assert report["tickers"] == ["NVDA", "MSFT"]
    assert report["competitor_outliers"][0]["views"] == 2_500_000


def test_latest_report_is_chosen_by_date_in_filename(isolated):
    folder = isolated / "reports"
    (folder / "2026-11-15.json").write_text('{"themes": [{"theme": "old", "score": 1}]}')
    (folder / "2026-11-16.json").write_text('{"themes": [{"theme": "new", "score": 1}]}')
    (folder / "broken.json").write_text("{not json")
    assert reports.latest_report()["themes"][0]["theme"] == "new"


def test_no_reports_is_not_an_error(isolated):
    assert reports.latest_report() is None


@pytest.mark.parametrize("raw,expected", [("1.2M", 1_200_000), ("340K views", 340_000), ("12,345", 12345), (987, 987), (None, None), ("lots", None)])
def test_parse_views(raw, expected):
    assert reports.parse_views(raw) == expected


# ---------- topic planning ----------
def test_the_subject_named_first_leads_the_video():
    theme = {"headlines": [{"title": "Treasury yields surge as bond selloff deepens"}], "search_trends": ["10 year treasury yield"]}
    plan = topics.plan_topic("Mortgage rates back above 7% as the 10-year Treasury yield tops 5%", theme)
    assert plan["primary"] == "housing" and "bonds" in plan["categories"]
    assert plan["charts"][0] == "mortgage_vs_10y"
    assert 3 <= len(plan["charts"]) <= 6


def test_unknown_topic_still_gets_three_charts():
    plan = topics.plan_topic("Something nobody has a keyword for")
    assert plan["primary"] == "" and len(plan["charts"]) == 3


def test_companies_in_the_topic_become_tickers():
    plan = topics.plan_topic("Nvidia earnings and the AI data center boom")
    assert plan["tickers"] == ["NVDA"] and plan["primary"] == "ai"
    assert "ticker_revenue" in plan["charts"]


def test_ai_is_matched_as_a_word_not_inside_other_words():
    assert "ai" not in topics.plan_topic("Why retail chains are raising prices")["categories"]


# ---------- compliance ----------
@pytest.mark.parametrize("text", [
    "You should buy Nvidia now before it doubles",
    "My price target of $300",
    "This is a guaranteed 10% return",
    "Bitcoin is going to hit $100,000",
    "Interest Rates Are About to DROP… Here’s Where I’m Putting My Money",
    "Time to sell your bonds",
])
def test_advice_language_is_caught(text):
    assert not compliance.is_clean(text)


@pytest.mark.parametrize("text", [
    "Mortgage Rates Are Now 7.11%. Here's Why",
    "Past performance does not guarantee future results.",
    "What it means for your mortgage, job and 401(k)",
    "Subscribe for plain-English money news",
])
def test_education_language_passes(text):
    assert compliance.is_clean(text)


def test_broll_prompts_naming_real_people_or_fake_news_are_blocked():
    assert compliance.check_broll_prompt("Jerome Powell at a podium")
    assert compliance.check_broll_prompt("Photorealistic breaking news footage of a bank run")
    assert compliance.check_broll_prompt("The Fed chair walking into a meeting")
    assert compliance.check_broll_prompt("Slow dolly down a server aisle, cool blue light") == []
    assert compliance.check_broll_prompt("A cook stirring a pot in a kitchen") == []


# ---------- clip planner ----------
SRT = """1
00:00:00,000 --> 00:00:20,000
Mortgage rates just went back above seven percent. And the Fed didn't do it.

2
00:00:20,000 --> 00:00:40,000
It comes down to one number most people never look at. That's the whole trick.

3
00:00:40,000 --> 00:01:05,000
Here's what this means for your wallet. If you have a fixed-rate mortgage, nothing changes.

4
00:01:05,000 --> 00:01:25,000
But if you're buying now, the same house costs more every month. That is the price of borrowing.

5
00:01:25,000 --> 00:01:50,000
What about your job? Higher borrowing costs make it more expensive for companies to grow.

6
00:01:50,000 --> 00:02:10,000
This is education, not investment advice. Subscribe if this helped.
"""


def test_parse_srt():
    segments = clips.parse_srt(SRT)
    assert len(segments) == 6
    assert segments[2]["start"] == 40.0 and segments[2]["end"] == 65.0
    assert segments[0]["text"].startswith("Mortgage rates just went back")


def test_clips_are_30_to_60_seconds_and_do_not_overlap():
    plan = clips.plan_clips("video.srt", SRT)
    assert plan["source"] == "rules" and plan["estimated_times"] is False
    assert 3 <= len(plan["clips"]) <= 5
    for clip in plan["clips"]:
        assert 30 <= clip["duration_seconds"] <= 60
        assert clip["caption"]
    spans = [(c["start_seconds"], c["end_seconds"]) for c in plan["clips"]]
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))
    assert plan["clips"][0]["start"] == "0:00" and plan["clips"][0]["end"] == "0:40"


def test_llm_picks_are_checked_against_the_real_transcript():
    def picker(_segments):
        return [
            {"start_segment": 0, "end_segment": 1, "caption_hook": "Rates hit 9% overnight", "why": "hook"},   # 9% is never said
            {"start_segment": 2, "end_segment": 3, "caption_hook": "You should buy now", "why": "wallet"},   # advice
            {"start_segment": 4, "end_segment": 99, "caption_hook": "Out of range", "why": ""},              # bad index
            {"start_segment": 4, "end_segment": 5, "caption_hook": "What about your job?", "why": "job"},
        ]

    plan = clips.plan_clips("video.srt", SRT, picker)
    assert plan["source"] == "llm" and len(plan["clips"]) == 3
    first, second, third = plan["clips"]
    assert "9%" not in first["caption"] and first["caption"].startswith("Mortgage rates just went back")
    assert "buy" not in second["caption"].lower()
    assert third["caption"] == "What about your job?"
    assert (first["start"], first["end"]) == ("0:00", "0:40")  # times come from the file, not the model


def test_llm_failure_falls_back_to_rules():
    def broken(_segments):
        raise RuntimeError("API down.")

    plan = clips.plan_clips("video.srt", SRT, broken)
    assert plan["source"] == "rules" and len(plan["clips"]) >= 3 and "API down." in plan["message"]


def test_txt_with_timestamps_and_without():
    stamped = "[0:00] First thought here.\n[0:20] Second thought here.\n[0:45] Third thought here.\n"
    segments, estimated = clips.parse_txt(stamped)
    assert estimated is False and [s["start"] for s in segments] == [0.0, 20.0, 45.0]
    prose = "This is a sentence about money. " * 60
    plan = clips.plan_clips("notes.txt", prose)
    assert plan["estimated_times"] is True and "estimates" in plan["message"]
    assert all(c["estimated_times"] for c in plan["clips"])


def test_short_or_empty_transcripts_are_handled():
    assert clips.plan_clips("a.txt", "")["clips"] == []
    assert "shorter than 30 seconds" in clips.plan_clips("a.txt", "Too short.")["message"]
