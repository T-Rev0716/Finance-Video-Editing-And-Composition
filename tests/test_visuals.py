"""Pass A, part 2: thumbnail workshop and explanation graphics."""
from __future__ import annotations

import io
import json
from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from vps import charts, graphics, media, projects, server, thumbnails

needs_ffmpeg = pytest.mark.skipif(not media.ffmpeg_path(), reason="ffmpeg not installed")


def png_bytes(size=(300, 500), color=(200, 60, 60, 255), transparent=True) -> io.BytesIO:
    image = Image.new("RGBA", size, (0, 0, 0, 0) if transparent else color)
    if transparent:
        image.paste(color, (60, 40, size[0] - 60, size[1]))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def fact(project, suffix=".latest"):
    return next(f for f in project["facts"] if f["key"].endswith(suffix) and f["status"] != "verify")


def open_file(project, relative):
    return Image.open(projects.project_dir(project["id"]) / relative)


# ---------------------------------------------------------------- thumbnails
@pytest.mark.parametrize("layout", list(thumbnails.LAYOUTS))
def test_every_layout_renders_full_size_and_phone_size(project, layout):
    thumbnails.add_host("me.png", png_bytes())
    facts = [f["id"] for f in project["facts"] if f["status"] != "verify" and f["value"]][:2]
    entry = thumbnails.create(project["id"], {"layout": layout, "theme": "dark", "headline": "why it's rising", "chart_n": 1,
                                              "fact_ids": facts, "host": "me.png", "title": "Mortgage Rates, Explained"},
                              channel="Money, Plainly")
    assert entry["file"] == "thumbnails/thumb_01.png" and open_file(project, entry["file"]).size == (1280, 720)
    assert open_file(project, entry["phone_file"]).size == (168, 94)
    phone = entry["phone"]
    assert (phone["width"], phone["height"]) == (168, 94)
    assert phone["title"] == "Mortgage Rates, Explained" and phone["channel"] == "Money, Plainly"
    assert phone["headline_px"] == round(entry["headline_font_px"] * 94 / 720, 1) and phone["legible"] is True
    assert entry["headline"] == "WHY IT'S RISING" and entry["layout"] == layout
    assert projects.load(project["id"])["thumbnail_renders"][0]["id"] == "thumb_01"
    if thumbnails.LAYOUTS[layout]["facts"]:
        assert entry["stats"][0]["value"] == next(f for f in project["facts"] if f["id"] == facts[0])["value"]
    if layout == "minimal_editorial":
        spec = json.loads((projects.project_dir(project["id"]) / "charts" / project["charts"][0]["spec_file"]).read_text())
        assert entry["data_callout"]["value"] == max(spec["series"][0]["values"]), "the peak tag is the chart's own data"


def test_headline_placeholder_is_filled_from_the_fact_sheet(project):
    first = fact(project)
    entry = thumbnails.create(project["id"], {"layout": "chart_hero_right_host", "chart_n": 1, "headline": f"rates at {{{first['id']}}}"})
    assert entry["headline"] == f"RATES AT {first['value'].upper()}" and entry["fact_ids"] == [first["id"]]


@pytest.mark.parametrize("headline,problem", [
    ("this has way too many words", "4 words or fewer"),
    ("rates hit 9.9% soon", "not on the fact sheet"),
    ("buy now before", "investment advice"),
    ("rates at {F999}", "not on the fact sheet"),
    ("   ", "empty"),
])
def test_headline_rules_are_enforced(project, headline, problem):
    with pytest.raises(thumbnails.ThumbnailError, match=problem):
        thumbnails.create(project["id"], {"layout": "chart_hero_right_host", "chart_n": 1, "headline": headline})
    assert not projects.load(project["id"]).get("thumbnail_renders")


def test_stats_must_be_verified_facts(project):
    news = next(f for f in project["facts"] if f["status"] == "verify")
    with pytest.raises(thumbnails.ThumbnailError, match="news article"):
        thumbnails.create(project["id"], {"layout": "big_stat_badge", "headline": "what changed", "fact_ids": [news["id"]]})
    with pytest.raises(thumbnails.ThumbnailError, match="needs 2 verified facts"):
        thumbnails.create(project["id"], {"layout": "split_comparison", "headline": "what changed", "fact_ids": [fact(project)["id"]]})
    with pytest.raises(thumbnails.ThumbnailError, match="needs a chart"):
        thumbnails.create(project["id"], {"layout": "minimal_editorial", "headline": "what changed"})
    with pytest.raises(thumbnails.ThumbnailError, match="Unknown layout"):
        thumbnails.create(project["id"], {"layout": "nope", "headline": "what changed"})
    with pytest.raises(thumbnails.ThumbnailError, match="60 characters"):
        thumbnails.create(project["id"], {"layout": "chart_hero_right_host", "chart_n": 1, "headline": "ok", "title": "x" * 61})


def test_themes_and_background_image_change_the_picture(project):
    def corner(theme, **extra):
        entry = thumbnails.create(project["id"], {"layout": "big_stat_badge", "headline": "what changed", "theme": theme,
                                                  "fact_ids": [fact(project)["id"]], **extra})
        return open_file(project, entry["file"]).convert("RGB").getpixel((1270, 10))

    colors = {theme: corner(theme) for theme in thumbnails.THEMES}
    assert len(set(colors.values())) == 4
    assert colors["crimson_alert"][0] > colors["crimson_alert"][2] and colors["emerald_growth"][1] > colors["emerald_growth"][0]
    with_chart_background = corner("dark", background=f"charts/{project['charts'][0]['files']['1920x1080']}")
    assert with_chart_background != colors["dark"]
    with pytest.raises(thumbnails.ThumbnailError, match="background"):
        corner("dark", background="../../.env")


def test_phone_preview_flags_text_too_small_to_read():
    small = thumbnails.phone_preview({"headline_font_px": 40}, "A title", "Channel")
    assert small["headline_px"] == 5.2 and small["legible"] is False and "hard to read" in small["note"]
    assert thumbnails.phone_preview({"headline_font_px": 120}, "A title", "Channel")["legible"] is True
    assert "score" not in json.dumps(small).lower()


def test_presenter_photos_and_presets(project, isolated):
    assert thumbnails.add_host("C:\\photos\\Me Pointing.PNG", png_bytes()) == {"name": "Me-Pointing.png"}
    thumbnails.add_host("studio.jpg", png_bytes(transparent=False))
    assert [h["name"] for h in thumbnails.list_hosts()] == ["Me-Pointing.png", "studio.jpg"]
    assert (isolated / "assets" / "hosts" / "Me-Pointing.png").exists()
    with pytest.raises(thumbnails.ThumbnailError, match="png"):
        thumbnails.add_host("me.gif", png_bytes())
    with pytest.raises(thumbnails.ThumbnailError, match="not an image"):
        thumbnails.add_host("broken.png", io.BytesIO(b"definitely not a png"))
    for host in ("Me-Pointing.png", "studio.jpg"):  # cutout and framed photo both render
        thumbnails.create(project["id"], {"layout": "chart_hero_right_host", "chart_n": 1, "headline": "what changed", "host": host})
    with pytest.raises(thumbnails.ThumbnailError, match="not in the library"):
        thumbnails.create(project["id"], {"layout": "chart_hero_right_host", "chart_n": 1, "headline": "what changed", "host": "../x.png"})

    presets = thumbnails.save_preset("  Red alert  ", "big_stat_badge", "crimson_alert", "Me-Pointing.png")
    assert presets == [{"name": "Red alert", "layout": "big_stat_badge", "theme": "crimson_alert", "host": "Me-Pointing.png"}]
    thumbnails.save_preset("red ALERT", "split_comparison", "dark")  # same name replaces
    assert [p["layout"] for p in thumbnails.list_presets()] == ["split_comparison"]
    assert json.loads((isolated / "assets" / "thumbnail_presets.json").read_text())[0]["name"] == "red ALERT"
    with pytest.raises(thumbnails.ThumbnailError):
        thumbnails.save_preset("bad", "nope", "dark")
    assert thumbnails.delete_preset("red ALERT") == []
    assert thumbnails.remove_host("studio.jpg") == [{"name": "Me-Pointing.png"}]
    assert len(thumbnails.remove(project["id"], 1)) == 1


# ---------------------------------------------------------------- explanation graphics
def test_highlight_keeps_the_axis_scale_and_uses_a_real_observation(project):
    entry = graphics.highlight_chart(project["id"], 1, "peak", "Highest point on this chart")
    assert entry["type"] == "highlight" and entry["format"] == "png" and entry["sources"][0]["url"].startswith("https://")
    assert open_file(project, entry["files"]["1920x1080"]).size == (1920, 1080)
    assert open_file(project, entry["files"]["1080x1920"]).size == (1080, 1920)
    chart, _ = graphics.load_chart(project, 1)
    series = chart["series"][0]
    assert entry["params"]["value"] == max(series.values)
    assert date.fromisoformat(entry["params"]["date"]) in series.dates

    plain = charts._draw(chart, "1920x1080", "dark", None)
    chart["highlight"] = {"date": series.dates[len(series) // 2], "value": series.values[len(series) // 2], "label_lines": ["Event", "x"]}
    marked = charts._draw(chart, "1920x1080", "dark", None)
    assert marked["axes_px"] == plain["axes_px"] and marked["series_px"] == plain["series_px"], "same scale, same points"
    left = (0, plain["axes_px"][1], plain["axes_px"][0] - 4, plain["axes_px"][3])  # the y-axis tick labels
    assert np.array_equal(np.asarray(marked["image"].crop(left)), np.asarray(plain["image"].crop(left)))
    assert not np.array_equal(np.asarray(marked["image"]), np.asarray(plain["image"])), "the callout was drawn"


def test_highlight_date_snaps_to_an_observation_and_label_is_guarded(project):
    chart, _ = graphics.load_chart(project, 1)
    series = chart["series"][0]
    target = series.dates[10]
    assert graphics.resolve_point(series, target.isoformat()) == (target, series.values[10])
    assert graphics.resolve_point(series, "1990-01-01")[0] == series.dates[0]
    assert graphics.resolve_point(series, "trough")[1] == min(series.values)
    assert graphics.resolve_point(series, "latest")[0] == series.dates[-1]
    for label, problem in (("Rates will hit 12% here", "not on the fact sheet"), ("Time to buy now", "advice")):
        with pytest.raises(graphics.GraphicsError, match=problem):
            graphics.highlight_chart(project["id"], 1, "latest", label)
    with pytest.raises(graphics.GraphicsError, match="YYYY-MM-DD"):
        graphics.highlight_chart(project["id"], 1, "last tuesday", "An event")
    with pytest.raises(graphics.GraphicsError, match="no chart 99"):
        graphics.highlight_chart(project["id"], 99, "peak", "An event")
    assert not projects.load(project["id"]).get("graphics")


def test_reveal_frames_wipe_the_data_in_without_touching_the_axes(project):
    chart, _ = graphics.load_chart(project, 1)
    frames = list(graphics.reveal_frames(chart, "1920x1080", "dark", 6))
    assert len(frames) == 7 and [final for _, final in frames] == [False] * 6 + [True]
    assert all(image.size == (1920, 1080) for image, _ in frames)
    info = charts._draw(chart, "1920x1080", "dark", None)
    x0, y0, x1, y1 = info["axes_px"]
    empty = np.asarray(charts._draw(chart, "1920x1080", "dark", None, show_marks=False)["image"])[y0:y1, x0:x1]
    counts = [int((np.asarray(image)[y0:y1, x0:x1] != empty).any(axis=2).sum()) for image, _ in frames[:-1]]  # drawn pixels
    assert counts == sorted(counts) and counts[0] < counts[-1], "more of the line appears each frame"
    outside = (0, 0, x0 - 6, 1080)  # title, y-axis labels and source never change
    first, last = np.asarray(frames[0][0].crop(outside)), np.asarray(frames[-2][0].crop(outside))
    assert np.array_equal(first, last)
    assert np.array_equal(np.asarray(frames[-1][0]), np.asarray(info["image"])), "the last frame is the finished chart"


def test_reveal_falls_back_to_gif_without_ffmpeg(project, monkeypatch):
    monkeypatch.setattr(media, "ffmpeg_path", lambda: None)
    entry = graphics.reveal_animation(project["id"], 1)
    assert entry["format"] == "gif" and "ffmpeg is not installed" in entry["note"]
    for size, expected in (("1920x1080", (960, 540)), ("1080x1920", (540, 960))):
        gif = open_file(project, entry["files"][size])
        assert gif.size == expected and gif.n_frames > 25
    assert entry["fact_ids"] == project["charts"][0]["fact_ids"]


@needs_ffmpeg
def test_reveal_makes_a_five_second_mp4_with_ffmpeg(project):
    entry = graphics.reveal_animation(project["id"], 1)
    assert entry["format"] == "mp4" and entry["note"] == ""
    for size in ("1920x1080", "1080x1920"):
        info = media.probe(str(projects.project_dir(project["id"]) / entry["files"][size]))
        assert f"{info['width']}x{info['height']}" == size and abs(info["duration"] - 5.0) < 0.05


def test_comparison_card_from_two_facts(project):
    a, b = [f for f in project["facts"] if f["key"].endswith(".latest")][:2]
    entry = graphics.comparison_card(project["id"], "Side by side", [a["id"], b["id"]])
    assert open_file(project, entry["files"]["1920x1080"]).size == (1920, 1080)
    assert open_file(project, entry["files"]["1080x1920"]).size == (1080, 1920)
    assert [p["value"] for p in entry["params"]["panels"]] == [a["value"], b["value"]]
    assert entry["fact_ids"] == [a["id"], b["id"]] and {s["url"] for s in entry["sources"]} == {a["source_url"], b["source_url"]}
    news = next(f for f in project["facts"] if f["status"] == "verify")
    for ids, problem in (([a["id"], a["id"]], "two different"), ([a["id"], news["id"]], "news article"), ([a["id"], "F999"], "not a fact")):
        with pytest.raises(graphics.GraphicsError, match=problem):
            graphics.comparison_card(project["id"], "", ids)
    with pytest.raises(graphics.GraphicsError, match="not on the fact sheet"):
        graphics.comparison_card(project["id"], "Up 400% in a year", [a["id"], b["id"]])


def test_comparison_card_from_two_dates_of_a_series(project):
    chart, _ = graphics.load_chart(project, 1)
    series = chart["series"][0]
    entry = graphics.comparison_card(project["id"], "", chart_n=1, dates=[series.dates[5].isoformat(), "latest"])
    panels = entry["params"]["panels"]
    assert panels[0]["value"] == charts.fmt_compact(series.values[5], chart["units"], chart["decimals"])
    assert panels[1]["value"] == charts.fmt_compact(series.values[-1], chart["units"], chart["decimals"])
    assert entry["chart_n"] == 1 and entry["title"] == series.title
    with pytest.raises(graphics.GraphicsError, match="same observation"):
        graphics.comparison_card(project["id"], "", chart_n=1, dates=["latest", "latest"])
    with pytest.raises(graphics.GraphicsError, match="Pick two facts"):
        graphics.comparison_card(project["id"], "")


def test_flow_diagram_fills_facts_and_refuses_other_numbers(project):
    a, b = [f for f in project["facts"] if f["key"].endswith(".latest")][:2]
    entry = graphics.flow_diagram(project["id"], [f"10-Year Yield {{{b['id']}}}", f"30-Year Mortgage {{{a['id']}}}", "Household payment impact"],
                                  "How it connects")
    assert open_file(project, entry["files"]["1920x1080"]).size == (1920, 1080)
    assert open_file(project, entry["files"]["1080x1920"]).size == (1080, 1920)
    assert entry["params"]["steps"][0] == f"10-Year Yield {b['value']}" and entry["fact_ids"] == [b["id"], a["id"]]
    assert {s["url"] for s in entry["sources"]} == {a["source_url"], b["source_url"]}
    for steps, problem in ((["a", "b"], "3 or 4 steps"), (["a", "b", "c", "d", "e"], "3 or 4 steps"),
                           (["Yields jump 3%", "b", "c"], "not on the fact sheet"), (["You should buy bonds", "b", "c"], "advice")):
        with pytest.raises(graphics.GraphicsError, match=problem):
            graphics.flow_diagram(project["id"], steps)
    assert len(projects.load(project["id"])["graphics"]) == 1
    assert graphics.remove(project["id"], entry["n"]) == []
    assert not (projects.project_dir(project["id"]) / entry["files"]["1920x1080"]).exists()


def test_old_projects_without_saved_chart_data_get_a_clear_message(project):
    saved = projects.load(project["id"])
    for chart in saved["charts"]:
        chart.pop("spec_file", None)
    projects.save(saved)
    with pytest.raises(graphics.GraphicsError, match="Generate it again"):
        graphics.reveal_animation(project["id"], 1)


# ---------------------------------------------------------------- through the web API
def test_thumbnail_and_graphics_api(project):
    client = TestClient(server.app)
    pid = project["id"]
    options = client.get("/api/thumbnails/options").json()
    assert [layout["id"] for layout in options["layouts"]] == list(thumbnails.LAYOUTS) and options["phone_size"] == [168, 94]
    assert client.post("/api/assets/hosts", files={"file": ("me.png", png_bytes().getvalue(), "image/png")}).json()["hosts"] == [{"name": "me.png"}]
    assert client.get("/api/assets/hosts/file/me.png").headers["content-type"] == "image/png"
    assert client.post("/api/assets/hosts", files={"file": ("me.txt", b"x", "text/plain")}).status_code == 400

    made = client.post(f"/api/projects/{pid}/thumbnails", json={"layout": "big_stat_badge", "theme": "slate", "headline": "what it costs",
                                                                "fact_ids": [fact(project)["id"]], "host": "me.png"})
    assert made.status_code == 200 and made.json()["phone"]["width"] == 168
    assert client.get(f"/api/projects/{pid}/file/{made.json()['file']}").headers["content-type"] == "image/png"
    bad = client.post(f"/api/projects/{pid}/thumbnails", json={"layout": "big_stat_badge", "headline": "up 50% tomorrow", "fact_ids": [fact(project)["id"]]})
    assert bad.status_code == 400 and "not on the fact sheet" in bad.json()["detail"]
    assert client.post("/api/thumbnails/presets", json={"name": "Slate badge", "layout": "big_stat_badge", "theme": "slate"}).json()["presets"][0]["name"] == "Slate badge"
    assert client.delete("/api/thumbnails/presets/Slate badge").json()["presets"] == []

    flow = client.post(f"/api/projects/{pid}/graphics", json={"type": "flow", "steps": ["Yields rise", "Mortgage rates follow", "Payments go up"]})
    assert flow.status_code == 200 and flow.json()["type"] == "flow"
    highlight = client.post(f"/api/projects/{pid}/graphics", json={"type": "highlight", "chart_n": 1, "when": "trough", "label": "The low point"})
    assert highlight.status_code == 200
    assert client.post(f"/api/projects/{pid}/graphics", json={"type": "flow", "steps": ["Up 9%", "b", "c"]}).status_code == 400
    assert client.post(f"/api/projects/{pid}/graphics", json={"type": "magic"}).status_code == 400
    assert len(client.get(f"/api/projects/{pid}").json()["graphics"]) == 2
    assert client.delete(f"/api/projects/{pid}/graphics/1").json()["graphics"][0]["type"] == "highlight"
    assert client.delete(f"/api/projects/{pid}/thumbnails/1").json()["thumbnail_renders"] == []
