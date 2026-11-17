"""Thumbnail workshop: 1280x720 thumbnails drawn with Pillow, plus a phone-feed-size preview.

Any number on a thumbnail comes from a fact on the fact sheet (or from the chart's own
fetched data for the peak marker). Headlines pass the same number guard and compliance
scan as every other piece of wording.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import compliance, config, projects, store
from .facts import fact_label
from .charts import fmt_compact
from .numbers import fill_placeholders, unknown_placeholders, unverified_numbers

SIZE = (1280, 720)
PHONE_SIZE = (168, 94)  # roughly how big a thumbnail is in the YouTube mobile feed
MAX_WORDS = 4
HOST_TYPES = (".png", ".jpg", ".jpeg", ".webp")
MIN_PHONE_TEXT_PX = 9  # below this, letters blur together at phone size

LAYOUTS = {
    "chart_hero_right_host": {"name": "Chart hero + host", "needs_chart": True, "facts": 0,
                              "about": "Bold chart line behind a big headline, presenter on the right."},
    "split_comparison": {"name": "Split comparison", "needs_chart": False, "facts": 2,
                         "about": "Two verified numbers side by side, presenter on the right."},
    "big_stat_badge": {"name": "Big stat badge", "needs_chart": False, "facts": 1,
                       "about": "One giant verified number in a badge, with headline and presenter."},
    "minimal_editorial": {"name": "Minimal editorial", "needs_chart": True, "facts": 0,
                          "about": "Dark grid, chart line with its peak marked, headline on top."},
}
THEMES = {
    "dark": {"name": "Dark", "top": "#14161c", "bottom": "#07080b", "ink": "#ffffff", "accent": "#fab219",
             "line": "#3987e5", "muted": "#b9c0cf", "badge_ink": "#0b0b0b"},
    "slate": {"name": "Slate", "top": "#22303f", "bottom": "#0c131b", "ink": "#f3f6fa", "accent": "#5cc8ff",
              "line": "#5cc8ff", "muted": "#a9b8c8", "badge_ink": "#06131d"},
    "crimson_alert": {"name": "Crimson alert", "top": "#4a0d12", "bottom": "#120305", "ink": "#ffffff",
                      "accent": "#ff5348", "line": "#ffb3a8", "muted": "#f0c4c0", "badge_ink": "#ffffff"},
    "emerald_growth": {"name": "Emerald growth", "top": "#083626", "bottom": "#02110b", "ink": "#ffffff",
                       "accent": "#35e08a", "line": "#35e08a", "muted": "#b5e3cc", "badge_ink": "#03130c"},
}


class ThumbnailError(ValueError):
    """Something about the request is not allowed. The message is shown to the user."""


# ---------------------------------------------------------------- fonts and text
def _font(size: int) -> ImageFont.FreeTypeFont:
    """A heavy font: Impact where Windows has it, otherwise the bold font bundled with matplotlib."""
    for name in ("impact.ttf", "Impact.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    import matplotlib
    return ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans-Bold.ttf"), size)


def _wrap(draw: ImageDraw.ImageDraw, words: list[str], font, width: int) -> list[str]:
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and draw.textlength(trial, font=font) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    return lines + ([current] if current else [])


def _fit(draw, text: str, width: int, height: int, max_size: int, max_lines: int = 3, min_size: int = 24):
    """Largest font at which the text fits the box. Returns (font, lines, line_height)."""
    words = text.split()
    for size in range(max_size, min_size - 1, -4):
        font = _font(size)
        lines = _wrap(draw, words, font, width)
        line_height = int(size * 1.08)
        if (len(lines) <= max_lines and line_height * len(lines) <= height
                and all(draw.textlength(line, font=font) <= width for line in lines)):
            return font, lines, line_height
    font = _font(min_size)
    return font, _wrap(draw, words, font, width)[:max_lines], int(min_size * 1.08)


def _text_block(draw, text: str, box: tuple[int, int, int, int], color: str, max_size: int, max_lines: int = 3,
                stroke: int = 6) -> int:
    """Draw fitted text top-left in box with a dark outline. Returns the font size used."""
    x, y, w, h = box
    font, lines, line_height = _fit(draw, text, w, h, max_size, max_lines)
    for i, line in enumerate(lines):
        draw.text((x, y + i * line_height), line, font=font, fill=color, stroke_width=stroke, stroke_fill="#000000")
    return font.size


# ---------------------------------------------------------------- validation
def clean_headline(text: str, project: dict, max_words: int = MAX_WORDS, what: str = "Thumbnail text") -> tuple[str, list[str]]:
    """Fill {F7} placeholders and enforce the rules. Returns (text, fact ids used)."""
    text = " ".join((text or "").split())
    if not text:
        raise ThumbnailError(f"{what} is empty.")
    facts = project.get("facts", [])
    by_id = {f["id"]: f for f in facts}
    unknown = unknown_placeholders(text, by_id)
    if unknown:
        raise ThumbnailError(f"{what} refers to {', '.join(unknown)}, which is not on the fact sheet.")
    filled, used = fill_placeholders(text, by_id)
    stray = unverified_numbers(text, facts)
    if stray:
        raise ThumbnailError(f"{what} contains a number that is not on the fact sheet: {', '.join(stray)}. "
                             "Use a verified fact (for example {F1}) instead.")
    if len(filled.split()) > max_words:
        raise ThumbnailError(f"{what} must be {max_words} words or fewer (it has {len(filled.split())}).")
    if not compliance.is_clean(filled):
        raise ThumbnailError(f"{what} reads like investment advice, a price target or a promise. Reword it.")
    return filled, used


def _stat(fact_id: str, project: dict, label: str | None) -> dict:
    fact = next((f for f in project.get("facts", []) if f["id"] == fact_id), None)
    if fact is not None and fact["status"] == "verify":
        raise ThumbnailError(f"{fact_id} comes only from a news article. Pick a verified fact.")
    if fact is None or not fact.get("value"):
        raise ThumbnailError(f"{fact_id} is not a fact with a value on this project's fact sheet.")
    if label:
        label, _ = clean_headline(label, project, max_words=4, what="Stat label")
    else:
        label = fact_label(fact)
    return {"id": fact_id, "value": fact["value"], "label": label.upper(), "as_of": fact.get("as_of", "")}


# ---------------------------------------------------------------- drawing pieces
def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _gradient(theme: dict) -> Image.Image:
    top, bottom = _rgb(theme["top"]), _rgb(theme["bottom"])
    column = Image.new("RGB", (1, SIZE[1]))
    for y in range(SIZE[1]):
        t = y / (SIZE[1] - 1)
        column.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return column.resize(SIZE).convert("RGBA")


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    scale = max(size[0] / image.width, size[1] / image.height)
    resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
    left, top = (resized.width - size[0]) // 2, (resized.height - size[1]) // 2
    return resized.crop((left, top, left + size[0], top + size[1]))


def _series_points(spec: dict, box: tuple[int, int, int, int], max_points: int = 400) -> tuple[list[tuple[float, float]], dict]:
    """The chart's first series as pixel points inside box, to true proportion (no smoothing)."""
    values = spec["series"][0]["values"]
    dates = spec["series"][0]["dates"]
    step = max(1, len(values) // max_points)
    index = list(range(0, len(values), step))
    if index[-1] != len(values) - 1:
        index.append(len(values) - 1)
    peak = max(range(len(values)), key=lambda i: values[i])
    if peak not in index:
        index = sorted(index + [peak])
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    x0, y0, w, h = box
    points = [(x0 + w * i / max(1, len(values) - 1), y0 + h - h * (values[i] - lo) / span) for i in index]
    peak_point = points[index.index(peak)]
    return points, {"peak_point": peak_point, "peak_value": values[peak], "peak_date": dates[peak],
                    "latest_value": values[-1], "latest_date": dates[-1]}


def _chart_line(canvas: Image.Image, spec: dict, box, color: str, width: int = 12, fill_alpha: int = 46) -> dict:
    points, info = _series_points(spec, box)
    layer = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    r, g, b = _rgb(color)
    x0, y0, w, h = box
    draw.polygon(points + [(points[-1][0], y0 + h), (points[0][0], y0 + h)], fill=(r, g, b, fill_alpha))
    glow = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(glow).line(points, fill=(r, g, b, 150), width=width * 3, joint="curve")
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)))
    draw.line(points, fill=(r, g, b, 255), width=width, joint="curve")
    end = points[-1]
    draw.ellipse((end[0] - width * 1.4, end[1] - width * 1.4, end[0] + width * 1.4, end[1] + width * 1.4),
                 fill=(255, 255, 255, 255), outline=(r, g, b, 255), width=6)
    canvas.alpha_composite(layer)
    return info


def _host(canvas: Image.Image, host_path: Path | None, theme: dict, box=(760, 30, 500, 690)) -> bool:
    """Presenter on the right: transparent cutouts stand on the bottom edge; photos get a frame."""
    if host_path is None:
        return False
    photo = Image.open(host_path).convert("RGBA")
    x, y, w, h = box
    has_cutout = photo.getchannel("A").getextrema()[0] < 250
    if has_cutout:
        scale = min(w / photo.width, h / photo.height)
        photo = photo.resize((max(1, round(photo.width * scale)), max(1, round(photo.height * scale))), Image.LANCZOS)
        shadow = Image.new("RGBA", SIZE, (0, 0, 0, 0))
        position = (x + w - photo.width, SIZE[1] - photo.height)
        shadow.paste((0, 0, 0, 170), (position[0] - 10, position[1] + 8), photo.getchannel("A"))
        canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(16)))
        canvas.alpha_composite(photo, position)
    else:
        frame_w, frame_h = w - 40, h - 60
        photo = _cover(photo, (frame_w, frame_h))
        mask = Image.new("L", (frame_w, frame_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, frame_w, frame_h), radius=36, fill=255)
        position = (x + 20, y + 20)
        ImageDraw.Draw(canvas).rounded_rectangle(
            (position[0] - 8, position[1] - 8, position[0] + frame_w + 8, position[1] + frame_h + 8),
            radius=44, fill=theme["accent"])
        canvas.paste(photo, position, mask)
    return True


def _stat_panel(draw, stat: dict, box, theme: dict, filled: bool) -> None:
    x, y, w, h = box
    if filled:
        draw.rounded_rectangle((x, y, x + w, y + h), radius=34, fill=theme["accent"])
        ink, sub = theme["badge_ink"], theme["badge_ink"]
    else:
        draw.rounded_rectangle((x, y, x + w, y + h), radius=34, fill=(0, 0, 0, 150), outline=theme["accent"], width=6)
        ink, sub = theme["ink"], theme["muted"]
    font, lines, line_height = _fit(draw, stat["value"], w - 48, h - 96, 190, max_lines=2)
    top = y + 20 + max(0, (h - 96 - line_height * len(lines)) // 2)
    for i, line in enumerate(lines):
        draw.text((x + 24, top + i * line_height), line, font=font, fill=ink)
    label_font, label_lines, label_height = _fit(draw, stat["label"], w - 48, 64, 34, max_lines=2, min_size=18)
    for i, line in enumerate(label_lines):
        draw.text((x + 24, y + h - 20 - label_height * (len(label_lines) - i)), line, font=label_font, fill=sub)


# ---------------------------------------------------------------- layouts
def render(project: dict, project_folder: Path, options: dict) -> tuple[Image.Image, dict]:
    """Draw one thumbnail. Returns (image, details). Raises ThumbnailError on a bad request."""
    layout = options.get("layout", "")
    if layout not in LAYOUTS:
        raise ThumbnailError(f"Unknown layout. Choose one of: {', '.join(LAYOUTS)}.")
    theme = THEMES.get(options.get("theme") or "dark")
    if theme is None:
        raise ThumbnailError(f"Unknown theme. Choose one of: {', '.join(THEMES)}.")
    headline, used = clean_headline(options.get("headline", ""), project)
    headline = headline.upper()

    spec = None
    chart_n = options.get("chart_n")
    if chart_n:
        chart = next((c for c in project.get("charts", []) if c["n"] == int(chart_n)), None)
        if chart is None:
            raise ThumbnailError(f"This project has no chart {chart_n}.")
        if not chart.get("spec_file"):
            raise ThumbnailError("This project was generated before chart data was saved. Generate it again to use its charts here.")
        spec = json.loads((project_folder / "charts" / chart["spec_file"]).read_text(encoding="utf-8"))
    if LAYOUTS[layout]["needs_chart"] and spec is None:
        raise ThumbnailError("This layout needs a chart. Pick one of the project's charts.")

    fact_ids = list(options.get("fact_ids") or [])
    labels = list(options.get("labels") or [])
    need = LAYOUTS[layout]["facts"]
    if len(fact_ids) < need:
        raise ThumbnailError(f"This layout needs {need} verified fact{'s' if need > 1 else ''} from the fact sheet.")
    stats = [_stat(fid, project, labels[i] if i < len(labels) else None) for i, fid in enumerate(fact_ids[:need])]

    host_path = host_file(options["host"]) if options.get("host") else None
    canvas = _gradient(theme)
    background = options.get("background")
    if background:
        try:
            image = Image.open(projects.safe_file(project["id"], background)).convert("RGB")
        except (FileNotFoundError, OSError):
            raise ThumbnailError("That background image could not be opened. Pick an image from this project.") from None
        canvas = _cover(image, SIZE).convert("RGBA")
        canvas.alpha_composite(Image.new("RGBA", SIZE, (0, 0, 0, 140)))  # darken so text stays readable
    draw = ImageDraw.Draw(canvas, "RGBA")
    text_width = 700 if host_path else 1160
    details: dict = {}

    if layout == "chart_hero_right_host":
        _chart_line(canvas, spec, (0, 250, SIZE[0], 400), theme["line"])
        _host(canvas, host_path, theme)
        draw = ImageDraw.Draw(canvas, "RGBA")
        size = _text_block(draw, headline, (56, 48, text_width, 400), theme["ink"], 190)
        draw.rectangle((56, 34, 56 + 180, 44), fill=theme["accent"])
    elif layout == "split_comparison":
        _host(canvas, host_path, theme)
        draw = ImageDraw.Draw(canvas, "RGBA")
        size = _text_block(draw, headline, (56, 40, text_width, 220), theme["ink"], 130, max_lines=2)
        panel_w = (text_width - 60) // 2
        _stat_panel(draw, stats[0], (56, 300, panel_w, 360), theme, filled=False)
        _stat_panel(draw, stats[1], (56 + panel_w + 60, 300, panel_w, 360), theme, filled=True)
        arrow_x, arrow_y = 56 + panel_w + 30, 480
        draw.polygon([(arrow_x - 22, arrow_y - 30), (arrow_x + 24, arrow_y), (arrow_x - 22, arrow_y + 30)], fill=theme["ink"])
    elif layout == "big_stat_badge":
        _host(canvas, host_path, theme)
        draw = ImageDraw.Draw(canvas, "RGBA")
        size = _text_block(draw, headline, (56, 40, text_width, 220), theme["ink"], 130, max_lines=2)
        _stat_panel(draw, stats[0], (56, 290, text_width, 380), theme, filled=True)
    else:  # minimal_editorial
        for gx in range(0, SIZE[0], 80):
            draw.line((gx, 0, gx, SIZE[1]), fill=(255, 255, 255, 16), width=1)
        for gy in range(0, SIZE[1], 80):
            draw.line((0, gy, SIZE[0], gy), fill=(255, 255, 255, 16), width=1)
        info = _chart_line(canvas, spec, (60, 330, (680 if host_path else 1160), 320), theme["line"], width=9, fill_alpha=30)
        _host(canvas, host_path, theme)
        draw = ImageDraw.Draw(canvas, "RGBA")
        px, py = info["peak_point"]
        # the peak comes straight from the chart's fetched data
        tag = fmt_compact(info["peak_value"], spec["units"], spec.get("decimals", 2))
        tag_font = _font(54)
        tag_w = draw.textlength(tag, font=tag_font)
        tag_x = min(max(60, px - tag_w / 2 - 18), (700 if host_path else 1180) - tag_w - 36)
        tag_y = max(250, py - 150)
        draw.rounded_rectangle((tag_x, tag_y, tag_x + tag_w + 36, tag_y + 76), radius=16, fill=theme["accent"])
        draw.text((tag_x + 18, tag_y + 8), tag, font=tag_font, fill=theme["badge_ink"])
        draw.line((px, tag_y + 76, px, py - 18), fill=theme["accent"], width=7)
        draw.polygon([(px - 16, py - 30), (px + 16, py - 30), (px, py - 6)], fill=theme["accent"])
        size = _text_block(draw, headline, (60, 44, text_width, 210), theme["ink"], 120, max_lines=2)
        details["data_callout"] = {"text": tag, "value": info["peak_value"], "date": info["peak_date"], "what": "chart peak"}

    details.update(headline=headline, headline_font_px=size, fact_ids=list(dict.fromkeys(used + [s["id"] for s in stats])),
                   stats=stats, layout=layout, theme=options.get("theme") or "dark", chart_n=int(chart_n) if chart_n else None,
                   host=options.get("host") or "", background=background or "")
    return canvas.convert("RGB"), details


def phone_preview(details: dict, title: str, channel: str) -> dict:
    """What the phone-feed mockup shows, and how big the headline letters end up there."""
    letter_px = round(details["headline_font_px"] * PHONE_SIZE[1] / SIZE[1], 1)
    legible = letter_px >= MIN_PHONE_TEXT_PX
    return {"width": PHONE_SIZE[0], "height": PHONE_SIZE[1], "title": title[:60], "channel": channel,
            "headline_px": letter_px, "legible": legible,
            "note": (f"Headline letters are about {letter_px} px tall at phone size."
                     + ("" if legible else f" Under {MIN_PHONE_TEXT_PX} px is hard to read: use fewer or shorter words."))}


def create(project_id: str, options: dict, channel: str = "") -> dict:
    """Render, save the full-size PNG and the phone-size PNG, and record it on the project."""
    project = projects.load(project_id)
    folder = projects.project_dir(project_id)
    image, details = render(project, folder, options)
    title = " ".join((options.get("title") or (project.get("titles") or [""])[0]).split())
    if len(title) > 60:
        raise ThumbnailError("The title shown beside the thumbnail must be 60 characters or fewer.")
    renders = project.get("thumbnail_renders", [])
    number = max([r["n"] for r in renders], default=0) + 1
    out = folder / "thumbnails"
    out.mkdir(exist_ok=True)
    name = f"thumb_{number:02d}.png"
    image.save(out / name)
    image.resize(PHONE_SIZE, Image.LANCZOS).save(out / f"thumb_{number:02d}_phone.png")
    entry = {"n": number, "id": f"thumb_{number:02d}", "file": f"thumbnails/{name}",
             "phone_file": f"thumbnails/thumb_{number:02d}_phone.png", "width": SIZE[0], "height": SIZE[1],
             "preset": options.get("preset", ""), "created": store.now_iso(),
             "phone": phone_preview(details, title, channel), **details}
    project["thumbnail_renders"] = renders + [entry]
    projects.save(project)
    return entry


def remove(project_id: str, number: int) -> list[dict]:
    project = projects.load(project_id)
    keep = [r for r in project.get("thumbnail_renders", []) if r["n"] != number]
    for entry in project.get("thumbnail_renders", []):
        if entry["n"] == number:
            for key in ("file", "phone_file"):
                (projects.project_dir(project_id) / entry[key]).unlink(missing_ok=True)
    project["thumbnail_renders"] = keep
    projects.save(project)
    return keep


# ---------------------------------------------------------------- presenter photos and presets
def hosts_dir() -> Path:
    path = config.assets_dir() / "hosts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_hosts() -> list[dict]:
    return [{"name": p.name} for p in sorted(hosts_dir().iterdir()) if p.suffix.lower() in HOST_TYPES]


def add_host(filename: str, source: BinaryIO) -> dict:
    if Path(filename).suffix.lower() not in HOST_TYPES:
        raise ThumbnailError("Presenter photos must be .png, .jpg or .webp. A transparent PNG cutout works best.")
    data = source.read(25 * 1024 * 1024 + 1)
    if len(data) > 25 * 1024 * 1024:
        raise ThumbnailError("That photo is larger than 25 MB.")
    target = store.unique_path(hosts_dir(), store.safe_name(filename, "host"))
    target.write_bytes(data)
    try:
        with Image.open(target) as image:
            image.verify()
    except Exception:
        target.unlink(missing_ok=True)
        raise ThumbnailError("That file is not an image Pillow can open.") from None
    return {"name": target.name}


def host_file(name: str) -> Path:
    for item in list_hosts():
        if item["name"] == name:
            return hosts_dir() / name
    raise ThumbnailError("That presenter photo is not in the library. Upload it again.")


def remove_host(name: str) -> list[dict]:
    host_file(name).unlink(missing_ok=True)
    return list_hosts()


def _presets_path() -> Path:
    return config.assets_dir() / "thumbnail_presets.json"


def list_presets() -> list[dict]:
    return store.read_json(_presets_path(), [])


def save_preset(name: str, layout: str, theme: str, host: str = "") -> list[dict]:
    name = " ".join((name or "").split())[:40]
    if not name:
        raise ThumbnailError("Give the preset a name.")
    if layout not in LAYOUTS or theme not in THEMES:
        raise ThumbnailError("A preset needs a valid layout and theme.")
    presets = [p for p in list_presets() if p["name"].lower() != name.lower()]
    presets.append({"name": name, "layout": layout, "theme": theme, "host": host})
    store.write_json(_presets_path(), presets)
    return presets


def delete_preset(name: str) -> list[dict]:
    presets = [p for p in list_presets() if p["name"] != name]
    store.write_json(_presets_path(), presets)
    return presets


def options() -> dict:
    return {"layouts": [{"id": k, **v} for k, v in LAYOUTS.items()],
            "themes": [{"id": k, "name": v["name"], "accent": v["accent"], "top": v["top"]} for k, v in THEMES.items()],
            "hosts": list_hosts(), "presets": list_presets(), "max_words": MAX_WORDS,
            "size": list(SIZE), "phone_size": list(PHONE_SIZE)}
