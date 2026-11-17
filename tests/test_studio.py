"""Pass A, part 1: recording cards (edits, pinned numbers, undo/redo, cues), timelines, asset board."""
from __future__ import annotations

import io
import xml.dom.minidom

import pytest
from fastapi.testclient import TestClient

from vps import asset_board, projects, recording_cards, server, store, timeline


def card(view: dict, card_id: str) -> dict:
    return next(c for c in view["cards"] if c["id"] == card_id)


def cards_view(project_id: str) -> dict:
    return recording_cards.view(recording_cards.load(project_id), projects.load(project_id))


# ---------------------------------------------------------------- recording cards
def test_cards_follow_the_outline_and_pin_their_facts(project):
    view = cards_view(project["id"])
    ids = [c["id"] for c in view["cards"]]
    assert ids[:2] == ["hook", "what_happened"] and ids[-2:] == ["watch_next", "closing"]
    assert {"means_mortgage", "means_job", "means_groceries", "means_retirement"} <= set(ids)
    assert any(i.startswith("why_") for i in ids)
    hook = card(view, "hook")
    assert hook["status"] == "unrecorded" and hook["pinned"], "the hook has sourced numbers pinned to it"
    for fact in hook["pinned"]:
        assert fact["value"] and fact["source_url"].startswith("https://") and fact["as_of"]
    assert any(v["kind"] == "CHART" and v["file"].endswith("_1920x1080.png") for v in hook["visuals"])
    assert any(v["kind"] == "HEADLINE" and v["url"] for v in card(view, "what_happened")["visuals"])
    assert all(c["warnings"]["ok"] for c in view["cards"]), "generated wording starts clean"
    assert (projects.project_dir(project["id"]) / "recording_cards.json").exists()
    assert projects.load(project["id"])["recording_cards"][0]["id"] == "hook"


def test_rewriting_a_card_keeps_its_pinned_numbers(project):
    pid = project["id"]
    before = card(cards_view(pid), "hook")
    recording_cards.update_card(pid, "hook", {"text": "Okay so here's the thing nobody tells you about mortgages."})
    after = card(cards_view(pid), "hook")
    assert after["text"].startswith("Okay so") and after["edited"] is True
    assert [f["id"] for f in after["pinned"]] == [f["id"] for f in before["pinned"]]
    assert after["pinned"][0]["value"] == before["pinned"][0]["value"]
    assert after["warnings"]["ok"]


def test_live_checks_flag_unverified_digits_advice_and_unknown_facts(project):
    pid = project["id"]
    value = project["facts"][0]["value"]
    check = lambda text: recording_cards.check_text(text, project)  # noqa: E731
    assert check(f"Rates are now {value}, plain and simple.")["ok"], "a number that is on the fact sheet is fine"
    assert check("Rates are now {F1}, and your 401(k) tracks the S&P 500. [CHART 1]")["ok"]
    made_up = check("Rates will be 9.75% by spring.")
    assert made_up["unverified_numbers"] == ["9.75%"] and not made_up["ok"]
    assert check("Honestly you should buy bonds now.")["advice"]
    assert check("The figure is {F999}.")["unknown_facts"] == ["F999"]
    news = next(f for f in project["facts"] if f["status"] == "verify")
    assert "7.2%" in news["claim"] and check("Rates hit 7.2% this year.")["unverified_numbers"] == ["7.2%"], \
        "a number that appears only in a news headline is not verified"
    recording_cards.update_card(pid, "hook", {"text": "Rates will be 9.75% by spring."})
    assert card(cards_view(pid), "hook")["warnings"]["unverified_numbers"] == ["9.75%"]
    assert recording_cards.load(pid)["cards"][0]["text"] == "Rates will be 9.75% by spring.", "warn, never rewrite"


def test_undo_and_redo_restore_wording_and_sources(project):
    pid = project["id"]
    original = card(cards_view(pid), "hook")
    recording_cards.update_card(pid, "hook", {"text": "First rewrite."})
    recording_cards.update_card(pid, "hook", {"text": "Second rewrite.", "fact_ids": []})
    view = cards_view(pid)
    assert view["can_undo"] and not view["can_redo"] and card(view, "hook")["pinned"] == []

    recording_cards.undo(pid)
    step = card(cards_view(pid), "hook")
    assert step["text"] == "First rewrite." and [f["id"] for f in step["pinned"]] == [f["id"] for f in original["pinned"]]
    recording_cards.undo(pid)
    assert card(cards_view(pid), "hook")["text"] == original["text"]
    assert not cards_view(pid)["can_undo"]
    recording_cards.undo(pid)  # nothing left: a no-op, not an error

    recording_cards.redo(pid)
    recording_cards.redo(pid)
    assert card(cards_view(pid), "hook")["text"] == "Second rewrite."
    recording_cards.update_card(pid, "hook", {"text": "A new branch."})
    assert not cards_view(pid)["can_redo"], "a new edit clears redo"


def test_autosave_bursts_fold_into_one_undo_step(project):
    pid = project["id"]
    original = card(cards_view(pid), "closing")["text"]
    recording_cards.update_card(pid, "closing", {"text": "T"}, checkpoint=True)
    for text in ("Th", "Tha", "Thanks"):
        recording_cards.update_card(pid, "closing", {"text": text}, checkpoint=False)
    assert len(recording_cards.load(pid)["undo"]) == 1
    recording_cards.undo(pid)
    assert card(cards_view(pid), "closing")["text"] == original


def test_history_is_capped(project):
    pid = project["id"]
    for i in range(recording_cards.MAX_HISTORY + 15):
        recording_cards.update_card(pid, "closing", {"pronunciation": f"note {i}"})
    assert len(recording_cards.load(pid)["undo"]) == recording_cards.MAX_HISTORY


def test_reorder_move_status_and_pronunciation(project):
    pid = project["id"]
    ids = [c["id"] for c in cards_view(pid)["cards"]]
    recording_cards.move(pid, ids[2], -2)
    assert [c["id"] for c in cards_view(pid)["cards"]][0] == ids[2]
    recording_cards.reorder(pid, ids)
    assert [c["id"] for c in cards_view(pid)["cards"]] == ids
    with pytest.raises(ValueError):
        recording_cards.reorder(pid, ids[:-1])

    recording_cards.set_status(pid, "hook", "recorded")
    recording_cards.set_status(pid, "closing", "needs_another_take")
    recording_cards.update_card(pid, "hook", {"pronunciation": "Pause one beat before the chart. FRED = 'fred'."})
    view = cards_view(pid)
    assert view["counts"] == {"unrecorded": len(ids) - 2, "recorded": 1, "needs_another_take": 1}
    assert card(view, "hook")["pronunciation"].startswith("Pause one beat")
    with pytest.raises(ValueError):
        recording_cards.set_status(pid, "hook", "done")
    recording_cards.undo(pid)  # undo the pronunciation note
    recording_cards.undo(pid)  # undo the closing status
    assert card(cards_view(pid), "closing")["status"] == "unrecorded"


def test_reset_card_restores_generated_wording(project):
    pid = project["id"]
    original = card(cards_view(pid), "hook")["original_text"]
    recording_cards.update_card(pid, "hook", {"text": "Changed."})
    recording_cards.reset_card(pid, "hook")
    assert card(cards_view(pid), "hook")["text"] == original


# ---------------------------------------------------------------- cue log and timeline exports
CARDS = [{"id": "hook", "title": "Hook"}, {"id": "why", "title": "Why it happened & more"}, {"id": "close", "title": "Closing"}]
CUES = [{"card_id": "hook", "start": 0}, {"card_id": "why", "start": 15.5, "flagged": True},
        {"card_id": "why", "start": 40}, {"card_id": "close", "start": 100}]


def test_timecode_and_clock():
    assert timeline.timecode(15.5) == "00:00:15:15"
    assert timeline.timecode(3661.0) == "01:01:01:00"
    assert timeline.clock(75) == "1:15" and timeline.clock(3675) == "1:01:15"


def test_chapters_skip_flagged_takes_and_start_at_zero():
    segs = timeline.segments(CUES, 130, CARDS)
    assert [s["end"] for s in segs] == [15.5, 40, 100, 130]
    assert timeline.chapters_text(segs) == "0:00 Hook\n0:15 Why it happened & more\n1:15 Closing\n"


def test_edl_lists_kept_takes_in_order():
    edl = timeline.edl_text("My video", timeline.segments(CUES, 130, CARDS))
    lines = edl.splitlines()
    assert lines[0] == "TITLE: My video" and lines[1] == "FCM: NON-DROP FRAME"
    assert "001  AX       AA/V  C        00:00:00:00 00:00:15:15 00:00:00:00 00:00:15:15" in lines
    assert "002  AX       AA/V  C        00:00:40:00 00:01:40:00 00:00:15:15 00:01:15:15" in lines
    assert "* SKIPPED TAKE: Why it happened & more at 00:00:15:15 (flagged: needs another take)" in lines


def test_fcpxml_is_well_formed_with_one_clip_per_kept_take():
    text = timeline.fcpxml_text("Rates & yields", timeline.segments(CUES, 130, CARDS), 130, "file:///C:/video/raw.mp4")
    doc = xml.dom.minidom.parseString(text)
    clips = doc.getElementsByTagName("asset-clip")
    assert [c.getAttribute("name") for c in clips] == ["Hook", "Why it happened & more", "Closing"]
    assert clips[1].getAttribute("start") == "1200/30s" and clips[1].getAttribute("offset") == "465/30s"
    assert doc.getElementsByTagName("media-rep")[0].getAttribute("src") == "file:///C:/video/raw.mp4"
    assert doc.getElementsByTagName("sequence")[0].getAttribute("duration") == f"{int((15.5 + 60 + 30) * 30)}/30s"


def test_cues_are_saved_and_exported_for_a_project(project):
    pid = project["id"]
    ids = [c["id"] for c in cards_view(pid)["cards"]]
    recording_cards.set_cues(pid, [{"card_id": ids[1], "start": 14.2}, {"card_id": ids[0], "start": 0}, {"card_id": "nope", "start": 3}], 61.0)
    state = recording_cards.load(pid)
    assert [c["card_id"] for c in state["cues"]] == ids[:2] and state["total_seconds"] == 61.0
    files = timeline.export_all(projects.load(pid), state)
    assert files["chapters.txt"].startswith("0:00 Hook") and "TITLE:" in files["timeline.edl"]
    xml.dom.minidom.parseString(files["timeline.fcpxml"])


# ---------------------------------------------------------------- asset board
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_board_links_charts_and_counts_what_is_missing(project):
    pid = project["id"]
    view = asset_board.view(asset_board.load(pid))
    kinds = {s["kind"] for s in view["slots"]}
    assert kinds == {"chart", "talking_head", "headline", "broll"}
    charts = [s for s in view["slots"] if s["kind"] == "chart"]
    assert charts and all(s["status"] == "ready" and s["source"] == "pipeline" and s["file"].startswith("charts/") for s in charts)
    assert all(not s["required"] and s["status"] == "camera" for s in view["slots"] if s["kind"] == "talking_head")
    required = [s for s in view["slots"] if s["required"]]
    missing = len(required) - len(charts)
    assert view["summary"]["text"] == f"{len(charts)} of {len(required)} scene visuals ready \u2014 {missing} missing"
    assert len(view["slots"]) == len(project["shots"])


def test_importing_a_local_file_fills_a_slot(project):
    pid = project["id"]
    slot = next(s for s in asset_board.view(asset_board.load(pid))["slots"] if s["kind"] == "broll")
    before = asset_board.summary(asset_board.load(pid))["missing"]
    board = asset_board.attach_file(pid, slot["shot_n"], "C:\\Users\\me\\Videos\\Suburb drone (final).MP4", io.BytesIO(b"fake video bytes"))
    updated = board["slots"][str(slot["shot_n"])]
    assert updated["status"] == "ready" and updated["media"] == "video" and updated["source"] == "upload"
    assert updated["original_name"] == "Suburb drone (final).MP4"
    assert updated["file"] == f"assets/shot_{slot['shot_n']:02d}_Suburb-drone-final.mp4"
    assert (projects.project_dir(pid) / updated["file"]).read_bytes() == b"fake video bytes"
    assert asset_board.summary(board)["missing"] == before - 1
    assert projects.load(pid)["asset_board"]["slots"][str(slot["shot_n"])]["status"] == "ready"

    board = asset_board.set_status(pid, slot["shot_n"], "needs_replacement")
    assert asset_board.summary(board)["needs_replacement"] == 1 and asset_board.summary(board)["missing"] == before
    asset_board.set_status(pid, slot["shot_n"], "ready")


def test_board_rejects_bad_files_and_bad_requests(project):
    pid = project["id"]
    slot = next(s for s in asset_board.view(asset_board.load(pid))["slots"] if s["kind"] == "headline")
    with pytest.raises(asset_board.AssetError, match="mp4"):
        asset_board.attach_file(pid, slot["shot_n"], "notes.exe", io.BytesIO(b"x"))
    with pytest.raises(asset_board.AssetError, match="empty"):
        asset_board.attach_file(pid, slot["shot_n"], "shot.png", io.BytesIO(b""))
    with pytest.raises(asset_board.AssetError, match="no scene"):
        asset_board.attach_file(pid, 999, "shot.png", io.BytesIO(PNG))
    with pytest.raises(asset_board.AssetError, match="Add a file"):
        asset_board.set_status(pid, slot["shot_n"], "ready")
    assert not list((projects.project_dir(pid) / "assets").glob("*")) if (projects.project_dir(pid) / "assets").exists() else True


def test_clearing_a_chart_slot_relinks_the_generated_chart(project):
    pid = project["id"]
    slot = next(s for s in asset_board.view(asset_board.load(pid))["slots"] if s["kind"] == "chart")
    asset_board.attach_file(pid, slot["shot_n"], "my_chart.png", io.BytesIO(PNG))
    assert asset_board.load(pid)["slots"][str(slot["shot_n"])]["source"] == "upload"
    restored = asset_board.clear(pid, slot["shot_n"])["slots"][str(slot["shot_n"])]
    assert restored["source"] == "pipeline" and restored["file"] == slot["file"]


def test_reusable_library_across_episodes(project, isolated):
    import shutil
    pid = project["id"]
    slot = next(s for s in asset_board.view(asset_board.load(pid))["slots"] if s["kind"] == "broll")
    asset_board.attach_file(pid, slot["shot_n"], "channel intro.mp4", io.BytesIO(b"intro"), save_to_library=True)
    items = asset_board.library_list()
    assert [i["name"] for i in items] == ["channel intro.mp4"] and items[0]["from_project"] == pid and items[0]["media"] == "video"
    assert (isolated / "assets" / "library" / items[0]["file"]).read_bytes() == b"intro"

    # a later episode picks it from the library in one step
    other = pid + "-2"
    shutil.copytree(projects.project_dir(pid), isolated / "projects" / other)
    second = projects.load(other)
    second["id"] = other
    projects.save(second)
    (projects.project_dir(other) / asset_board.BOARD_FILE).unlink()
    target = next(s for s in asset_board.view(asset_board.load(other))["slots"] if s["kind"] == "broll")
    assert target["status"] == "missing"
    board = asset_board.assign_from_library(other, target["shot_n"], items[0]["id"])
    picked = board["slots"][str(target["shot_n"])]
    assert picked["source"] == "library" and picked["status"] == "ready"
    assert (projects.project_dir(other) / picked["file"]).read_bytes() == b"intro"
    with pytest.raises(asset_board.AssetError):
        asset_board.assign_from_library(other, target["shot_n"], "missing.mp4")
    assert asset_board.library_remove(items[0]["id"]) == []


def test_safe_names_and_unique_paths(tmp_path):
    assert store.safe_name("../../etc/passwd") == "passwd"
    assert store.safe_name("My Clip (v2).MOV") == "My-Clip-v2.mov"
    assert store.safe_name("???.png") == "file.png"
    (tmp_path / "a.png").write_bytes(b"1")
    assert store.unique_path(tmp_path, "a.png").name == "a-2.png"


# ---------------------------------------------------------------- through the web API
@pytest.fixture
def client(project):
    return TestClient(server.app)


def test_cards_api_edit_check_undo_and_export(client, project):
    pid = project["id"]
    view = client.get(f"/api/projects/{pid}/cards").json()
    hook = card(view, "hook")
    edited = client.put(f"/api/projects/{pid}/cards/hook", json={"text": "My own words, plus 12.5% I made up."}).json()
    assert card(edited, "hook")["warnings"]["unverified_numbers"] == ["12.5%"]
    assert [f["id"] for f in card(edited, "hook")["pinned"]] == [f["id"] for f in hook["pinned"]]
    assert client.post(f"/api/projects/{pid}/cards-check", json={"text": "you should sell now"}).json()["advice"]
    undone = client.post(f"/api/projects/{pid}/cards-undo").json()
    assert card(undone, "hook")["text"] == hook["text"] and undone["can_redo"]
    assert client.put(f"/api/projects/{pid}/cards/nope", json={"text": "x"}).status_code == 404
    assert client.post(f"/api/projects/{pid}/cards/hook/status", json={"status": "bogus"}).status_code == 400

    recorded = client.post(f"/api/projects/{pid}/cards/hook/status", json={"status": "recorded"}).json()
    assert recorded["frozen_at"] and (projects.project_dir(pid) / "frozen_facts.json").exists(), "marking a card recorded freezes the facts"

    ids = [c["id"] for c in view["cards"]]
    client.post(f"/api/projects/{pid}/cards-cues", json={"cues": [{"card_id": ids[0], "start": 0}, {"card_id": ids[1], "start": 12}], "total_seconds": 40})
    chapters = client.get(f"/api/projects/{pid}/timeline/chapters.txt")
    assert chapters.status_code == 200 and chapters.text.startswith("0:00 ") and "attachment" in chapters.headers["content-disposition"]
    assert "FCM: NON-DROP FRAME" in client.get(f"/api/projects/{pid}/timeline/timeline.edl").text
    xml.dom.minidom.parseString(client.get(f"/api/projects/{pid}/timeline/timeline.fcpxml").text)
    assert client.get(f"/api/projects/{pid}/timeline/other.txt").status_code == 404
    assert (projects.project_dir(pid) / "timeline" / "timeline.edl").exists()


def test_asset_board_api_upload_status_and_library(client, project):
    pid = project["id"]
    board = client.get(f"/api/projects/{pid}/asset-board").json()
    slot = next(s for s in board["slots"] if s["kind"] == "broll")
    url = f"/api/projects/{pid}/shots/{slot['shot_n']}"
    uploaded = client.post(f"{url}/asset", files={"file": ("b-roll one.webm", b"webm-bytes", "video/webm")}, data={"save_to_library": "true"}).json()
    filled = next(s for s in uploaded["slots"] if s["shot_n"] == slot["shot_n"])
    assert filled["status"] == "ready" and uploaded["summary"]["missing"] == board["summary"]["missing"] - 1
    assert client.get(f"/api/projects/{pid}/file/{filled['file']}").content == b"webm-bytes"
    assert client.post(f"{url}/asset", files={"file": ("virus.exe", b"x", "application/octet-stream")}).status_code == 400
    assert client.post(f"{url}/asset-status", json={"status": "needs_replacement"}).json()["summary"]["needs_replacement"] == 1
    library = client.get("/api/library").json()["items"]
    assert len(library) == 1 and client.get(f"/api/library/file/{library[0]['id']}").content == b"webm-bytes"
    assert client.get("/api/library/file/..%2F..%2F.env").status_code == 404
    other = next(s for s in board["slots"] if s["kind"] == "headline")
    picked = client.post(f"/api/projects/{pid}/shots/{other['shot_n']}/asset-library", json={"library_id": library[0]["id"]}).json()
    assert next(s for s in picked["slots"] if s["shot_n"] == other["shot_n"])["source"] == "library"
    cleared = client.post(f"{url}/asset-clear").json()
    assert next(s for s in cleared["slots"] if s["shot_n"] == slot["shot_n"])["status"] == "missing"
