"""The web API, driven the way the browser drives it."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from tests.test_rules import SRT
from vps import server


@pytest.fixture
def client(net, report_file):
    return TestClient(server.app)


def wait_ready(client, project_id):
    for _ in range(200):
        progress = client.get(f"/api/projects/{project_id}/progress").json()
        if progress["done"]:
            return progress
        time.sleep(0.1)
    raise AssertionError("generation did not finish")


def test_pick_a_theme_generate_and_download(client):
    state = client.get("/api/state").json()
    assert state["report"]["themes"][0]["theme"].startswith("Mortgage rates")
    assert state["keys"] == {"fred": False, "llm": False}

    project_id = client.post("/api/projects", json={"topic": state["report"]["themes"][0]["theme"], "theme_index": 0}).json()["id"]
    assert wait_ready(client, project_id)["error"] == ""
    project = client.get(f"/api/projects/{project_id}").json()
    assert project["status"] == "ready" and len(project["headlines"]) == 2

    png = client.get(f"/api/projects/{project_id}/file/charts/{project['charts'][0]['files']['1920x1080']}")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert client.get(f"/api/projects/{project_id}/file/../../.env").status_code == 404

    upload = client.post(f"/api/projects/{project_id}/transcript", files={"file": ("video.srt", SRT, "text/plain")})
    assert upload.status_code == 200 and len(upload.json()["clips"]["clips"]) >= 3
    assert client.post(f"/api/projects/{project_id}/transcript", files={"file": ("video.mp4", b"x", "video/mp4")}).status_code == 400

    zipped = client.get(f"/api/projects/{project_id}/export")
    assert zipped.status_code == 200 and zipped.content[:2] == b"PK"
    assert client.get("/api/state").json()["projects"][0]["id"] == project_id


def test_empty_topic_is_rejected_and_unknown_project_is_404(client):
    assert client.post("/api/projects", json={"topic": "   "}).status_code == 400
    assert client.get("/api/projects/nope").status_code == 404


def test_settings_roundtrip_hides_keys(client):
    saved = client.post("/api/settings", json={"values": {"FRED_API_KEY": "abcdef0123456789abcdef0123456789", "CHANNEL_NAME": "Money, Plainly"}}).json()
    assert saved["settings"]["FRED_API_KEY"] == {"secret": True, "set": True, "hint": "...6789"}
    assert saved["settings"]["CHANNEL_NAME"]["value"] == "Money, Plainly"
    # a blank key field keeps the saved key; "clear" removes it
    assert client.post("/api/settings", json={"values": {"FRED_API_KEY": ""}}).json()["settings"]["FRED_API_KEY"]["set"] is True
    assert client.post("/api/settings", json={"values": {}, "clear": ["FRED_API_KEY"]}).json()["settings"]["FRED_API_KEY"]["set"] is False


def test_home_page_and_static_files_are_served(client):
    assert "Video Prep Studio" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
