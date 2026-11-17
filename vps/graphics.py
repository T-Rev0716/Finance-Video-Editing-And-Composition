"""Explanation graphics built from the project's own data, in 1920x1080 and 1080x1920.

1. Line-chart reveal animation (.mp4 with ffmpeg, .gif without)
2. Highlighted date with a callout arrow
3. Side-by-side comparison card (two facts, or two dates of one series)
4. Mechanism flow diagram (A -> B -> C)

Every number shown is a fact-sheet value or an observation from the chart's saved data.
The reveal and the highlight reuse the chart renderer, so axes and scale are identical
to the original chart. Each graphic carries its source line.
"""
from __future__ import annotations

import bisect
import json
import subprocess
import textwrap
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import charts, config, fmt, media, projects, store
from .facts import fact_label
from .thumbnails import ThumbnailError, clean_headline

SIZES = {"1920x1080": (1920, 1080), "1080x1920": (1080, 1920)}
FPS = 30
REVEAL_SECONDS, HOLD_SECONDS = 3.5, 1.5  # 5 seconds in total


class GraphicsError(ValueError):
    """A request the builder cannot honour. The message is shown to the user."""


def _clean(text: str, project: dict, max_words: int, what: str) -> tuple[str, list[str]]:
    try:
        return clean_headline(text, project, max_words=max_words, what=what)
    except ThumbnailError as exc:
        raise GraphicsError(str(exc)) from None


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    import matplotlib
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts" / "ttf" / name), size)


def _theme(project: dict) -> tuple[str, dict]:
    name = (project.get("charts") or [{}])[0].get("theme") or config.load_settings().get("CHART_THEME", "dark")
    return name, charts.THEMES.get(name, charts.THEMES["dark"])


def load_chart(project: dict, chart_n: int) -> tuple[dict, dict]:
    """(chart ready for the renderer, the project's chart entry)."""
    entry = next((c for c in project.get("charts", []) if c["n"] == int(chart_n)), None)
    if entry is None:
        raise GraphicsError(f"This project has no chart {chart_n}.")
    if not entry.get("spec_file"):
        raise GraphicsError("This project was generated before chart data was saved. Generate it again to build graphics from its charts.")
    path = projects.project_dir(project["id"]) / "charts" / entry["spec_file"]
    return charts.chart_from_spec(json.loads(path.read_text(encoding="utf-8"))), entry


def _record(project_id: str, kind: str, title: str, files: dict, file_format: str, fact_ids: list[str],
            chart_n: int | None, sources: list[dict], params: dict, note: str = "") -> dict:
    project = projects.load(project_id)
    number = params.pop("_n")
    entry = {"n": number, "id": f"g{number:02d}", "type": kind, "title": title, "files": files,
             "format": file_format, "fact_ids": fact_ids, "chart_n": chart_n, "sources": sources, "params": params,
             "note": note, "stale": False, "created": store.now_iso()}
    project["graphics"] = project.get("graphics", []) + [entry]
    projects.save(project)
    return entry


def _next(project: dict) -> tuple[int, Path]:
    number = max([g["n"] for g in project.get("graphics", [])], default=0) + 1
    folder = projects.project_dir(project["id"]) / "graphics"
    folder.mkdir(exist_ok=True)
    return number, folder


def _series_sources(chart: dict) -> list[dict]:
    seen, out = set(), []
    for s in chart["series"]:
        if s.source_url not in seen:
            seen.add(s.source_url)
            out.append({"name": f"{s.title} - {s.source_name}", "url": s.source_url})
    return out


def _fact_sources(facts: list[dict]) -> list[dict]:
    seen, out = set(), []
    for fact in facts:
        if fact.get("source_url") and fact["source_url"] not in seen:
            seen.add(fact["source_url"])
            out.append({"name": fact["source_name"], "url": fact["source_url"]})
    return out


def remove(project_id: str, number: int) -> list[dict]:
    project = projects.load(project_id)
    folder = projects.project_dir(project_id)
    for entry in project.get("graphics", []):
        if entry["n"] == number:
            for name in entry["files"].values():
                (folder / name).unlink(missing_ok=True)
    project["graphics"] = [g for g in project.get("graphics", []) if g["n"] != number]
    projects.save(project)
    return project["graphics"]


# ---------------------------------------------------------------- 2. highlighted date
def resolve_point(series, when: str) -> tuple[date, float]:
    """'peak', 'trough', 'latest' or an ISO date, snapped to a real observation (never interpolated)."""
    when = (when or "").strip().lower()
    if when == "peak":
        i = max(range(len(series)), key=lambda k: series.values[k])
    elif when == "trough":
        i = min(range(len(series)), key=lambda k: series.values[k])
    elif when in ("latest", ""):
        i = len(series) - 1
    else:
        try:
            target = date.fromisoformat(when)
        except ValueError:
            raise GraphicsError("Pick a date as YYYY-MM-DD, or choose peak, trough or latest.") from None
        i = max(0, bisect.bisect_right(series.dates, target) - 1)
    return series.dates[i], series.values[i]


def highlight_chart(project_id: str, chart_n: int, when: str, label: str, series_index: int = 0) -> dict:
    project = projects.load(project_id)
    chart, entry = load_chart(project, chart_n)
    if not 0 <= series_index < len(chart["series"]):
        raise GraphicsError("That chart has no such line.")
    label, used = _clean(label, project, 8, "Callout label")
    series = chart["series"][series_index]
    point_date, value = resolve_point(series, when)
    value_text = charts.fmt_compact(value, chart["units"], chart.get("decimals", 2))
    date_text = fmt.fmt_date(point_date, series.frequency or "daily")
    chart["highlight"] = {"date": point_date, "value": value,
                          "label_lines": textwrap.wrap(label, 24) + [f"{value_text}  ·  {date_text}"]}
    number, folder = _next(project)
    theme_name, _ = _theme(project)
    files = {}
    for size_name in SIZES:
        name = f"g{number:02d}_highlight_chart{chart_n}_{size_name}.png"
        charts._draw(chart, size_name, theme_name, folder / name)
        files[size_name] = f"graphics/{name}"
    return _record(project_id, "highlight", f"{chart['title']}: {label}", files, "png",
                   list(dict.fromkeys(used + entry.get("fact_ids", []))), int(chart_n), _series_sources(chart),
                   {"_n": number, "when": when, "label": label, "date": point_date.isoformat(), "value": value,
                    "value_text": value_text, "series_index": series_index})


# ---------------------------------------------------------------- 1. reveal animation
def _ease(t: float) -> float:
    return t * t * (3 - 2 * t)


def _tip_y(points: list[tuple[float, float]], x: float) -> float | None:
    xs = [p[0] for p in points]
    if not xs or x < xs[0]:
        return None
    i = bisect.bisect_right(xs, x) - 1
    if i >= len(points) - 1:
        return points[-1][1]
    (x0, y0), (x1, y1) = points[i], points[i + 1]
    return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def reveal_frames(chart: dict, size_name: str, theme_name: str, reveal_count: int):
    """Yields (image, is_final). The data is wiped in left to right over a chart whose axes,
    scale, title and source never change; the last frame is the finished chart."""
    chart = {k: v for k, v in chart.items() if k != "highlight"}
    theme = charts.THEMES.get(theme_name, charts.THEMES["dark"])
    empty = charts._draw(chart, size_name, theme_name, None, show_marks=False)
    full = charts._draw(chart, size_name, theme_name, None, show_end_labels=False)
    final = charts._draw(chart, size_name, theme_name, None)["image"]
    x0, y0, x1, y1 = full["axes_px"]
    height = full["height"]
    lines = chart["kind"] not in ("bars", "bars_change")
    colors = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in theme["series"]]
    bg = tuple(int(theme["bg"][i:i + 2], 16) for i in (1, 3, 5))
    for k in range(1, reveal_count + 1):
        x = int(round(x0 + (x1 - x0 + 4) * _ease(k / reveal_count)))
        frame = empty["image"].copy()
        if x > x0:
            frame.paste(full["image"].crop((x0 - 6, 0, x, height)), (x0 - 6, 0))
        if lines:
            draw = ImageDraw.Draw(frame)
            for i, points in enumerate(full["series_px"]):
                y = _tip_y(points, x)
                if y is not None and x <= x1:
                    draw.ellipse((x - 11, y - 11, x + 11, y + 11), fill=colors[i % len(colors)], outline=bg, width=3)
        yield frame, False
    yield final, True


def _encode_mp4(frames, size: tuple[int, int], out: Path) -> None:
    """Pipe raw frames into ffmpeg. The final frame is held for HOLD_SECONDS."""
    cmd = [media.ffmpeg_path(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{size[0]}x{size[1]}", "-framerate", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for image, is_final in frames:
            data = image.tobytes()
            for _ in range(int(HOLD_SECONDS * FPS) if is_final else 1):
                process.stdin.write(data)
        process.stdin.close()
        error = process.stderr.read().decode("utf-8", errors="replace")
        if process.wait() != 0:
            raise media.MediaError(error.strip()[-300:] or "ffmpeg failed")
    except BrokenPipeError:
        error = process.stderr.read().decode("utf-8", errors="replace")
        process.wait()
        raise media.MediaError(error.strip()[-300:] or "ffmpeg stopped early") from None


def _encode_gif(frames, size: tuple[int, int], out: Path) -> None:
    """Fallback without ffmpeg: a half-size animated GIF made by Pillow."""
    small = (size[0] // 2, size[1] // 2)
    images, durations = [], []
    for image, is_final in frames:
        images.append(image.resize(small, Image.LANCZOS).quantize(colors=128, method=Image.Quantize.MEDIANCUT))
        durations.append(int(HOLD_SECONDS * 1000) if is_final else 0)
    step = int(REVEAL_SECONDS * 1000 / max(1, len(images) - 1))
    durations = [d or step for d in durations]
    images[0].save(out, save_all=True, append_images=images[1:], duration=durations, loop=0, optimize=False)


def reveal_animation(project_id: str, chart_n: int) -> dict:
    project = projects.load(project_id)
    chart, entry = load_chart(project, chart_n)
    number, folder = _next(project)
    theme_name, _ = _theme(project)
    note = ""

    def build(file_format: str) -> dict:
        files = {}
        for size_name, size in SIZES.items():
            name = f"g{number:02d}_reveal_chart{chart_n}_{size_name}.{file_format}"
            if file_format == "mp4":
                _encode_mp4(reveal_frames(chart, size_name, theme_name, int(REVEAL_SECONDS * FPS)), size, folder / name)
            else:
                _encode_gif(reveal_frames(chart, size_name, theme_name, 36), size, folder / name)
            files[size_name] = f"graphics/{name}"
        return files

    file_format = "mp4" if media.ffmpeg_path() else "gif"
    if file_format == "gif":
        note = "ffmpeg is not installed, so this is a half-size GIF. Install ffmpeg for a full-size 30 fps .mp4."
    try:
        files = build(file_format)
    except (media.MediaError, OSError) as exc:
        if file_format == "gif":
            raise
        file_format, note = "gif", f"ffmpeg failed ({exc}), so this is a half-size GIF instead."
        files = build("gif")
    return _record(project_id, "reveal", f"{chart['title']}: line reveal", files, file_format, entry.get("fact_ids", []),
                   int(chart_n), _series_sources(chart), {"_n": number, "seconds": REVEAL_SECONDS + HOLD_SECONDS}, note)


# ---------------------------------------------------------------- card drawing helpers
def _wrap(draw, text: str, font, width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and draw.textlength(trial, font=font) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    return lines + ([current] if current else [])


def _fit(draw, text: str, width: int, height: int, max_size: int, bold: bool = True, max_lines: int = 3, min_size: int = 20):
    for size in range(max_size, min_size - 1, -2):
        font = _font(size, bold)
        lines = _wrap(draw, text, font, width)
        line_height = int(size * 1.22)
        if (len(lines) <= max_lines and line_height * len(lines) <= height
                and all(draw.textlength(line, font=font) <= width for line in lines)):
            return font, lines, line_height
    font = _font(min_size, bold)
    return font, _wrap(draw, text, font, width)[:max_lines], int(min_size * 1.22)


def _block(draw, text: str, box, color: str, max_size: int, bold: bool = True, max_lines: int = 3,
           align: str = "left", valign: str = "top") -> None:
    x, y, w, h = box
    font, lines, line_height = _fit(draw, text, w, h, max_size, bold, max_lines)
    top = y + (h - line_height * len(lines)) // 2 if valign == "middle" else y
    for i, line in enumerate(lines):
        left = x + (w - draw.textlength(line, font=font)) / 2 if align == "center" else x
        draw.text((left, top + i * line_height), line, font=font, fill=color)


def _footer(draw, size: tuple[int, int], theme: dict, source_lines: list[str]) -> None:
    w, h = size
    portrait = h > w
    x, bottom = int(w * 0.06), int(h * (0.80 if portrait else 0.955))
    font = _font(22 if portrait else 24)
    lines: list[str] = []
    for line in source_lines:
        lines += _wrap(draw, line, font, w - 2 * x)
    lines = lines[-5:]
    for i, line in enumerate(lines):
        draw.text((x, bottom - (len(lines) - i) * 32), line, font=font, fill=theme["muted"])


def _canvas(size_name: str, theme: dict) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", SIZES[size_name], theme["bg"])
    return image, ImageDraw.Draw(image)


# ---------------------------------------------------------------- 3. comparison card
def _draw_comparison(size_name: str, theme: dict, title: str, panels: list[dict], source_lines: list[str]) -> Image.Image:
    image, draw = _canvas(size_name, theme)
    w, h = image.size
    portrait = h > w
    margin = int(w * 0.06)
    top = int(h * (0.13 if portrait else 0.08))
    _block(draw, title, (margin, top, w - 2 * margin, int(h * 0.14)), theme["ink"], 64 if portrait else 68, max_lines=2)
    area_top = top + int(h * (0.15 if portrait else 0.20))
    area_bottom = int(h * (0.66 if portrait else 0.80))
    gap = int(w * 0.04)
    if portrait:
        panel_h = (area_bottom - area_top - gap) // 2
        boxes = [(margin, area_top + i * (panel_h + gap), w - 2 * margin, panel_h) for i in range(2)]
    else:
        panel_w = (w - 2 * margin - gap) // 2
        boxes = [(margin + i * (panel_w + gap), area_top, panel_w, area_bottom - area_top) for i in range(2)]
    for i, (panel, (x, y, pw, ph)) in enumerate(zip(panels, boxes)):
        color = theme["series"][i]
        draw.rounded_rectangle((x, y, x + pw, y + ph), radius=28, outline=theme["axis"], width=3)
        draw.rectangle((x + 3, y + 26, x + 15, y + ph - 26), fill=color)
        pad = 48
        _block(draw, panel["label"], (x + pad, y + 34, pw - 2 * pad, int(ph * 0.24)), theme["ink2"], 40, bold=False, max_lines=2)
        _block(draw, panel["value"], (x + pad, y + int(ph * 0.30), pw - 2 * pad, int(ph * 0.42)), theme["ink"], 170,
               max_lines=2, valign="middle")
        _block(draw, panel["when"], (x + pad, y + int(ph * 0.78), pw - 2 * pad, int(ph * 0.16)), theme["muted"], 32, bold=False, max_lines=1)
    _footer(draw, image.size, theme, source_lines)
    return image


def comparison_card(project_id: str, title: str = "", fact_ids: list[str] | None = None,
                    chart_n: int | None = None, dates: list[str] | None = None, series_index: int = 0) -> dict:
    """Two facts side by side, or one series on two dates."""
    project = projects.load(project_id)
    theme_name, theme = _theme(project)
    used: list[str] = []
    if fact_ids:
        if len(fact_ids) != 2 or fact_ids[0] == fact_ids[1]:
            raise GraphicsError("Pick two different facts to compare.")
        by_id = {f["id"]: f for f in project.get("facts", [])}
        facts = []
        for fact_id in fact_ids:
            fact = by_id.get(fact_id)
            if fact and fact["status"] == "verify":
                raise GraphicsError(f"{fact_id} comes only from a news article. Pick verified facts.")
            if not fact or not fact.get("value"):
                raise GraphicsError(f"{fact_id} is not a fact with a value on the fact sheet.")
            facts.append(fact)
        panels = [{"label": fact_label(f), "value": f["value"], "when": f"As of {f['as_of']}" if f.get("as_of") else ""} for f in facts]
        sources = _fact_sources(facts)
        source_lines = ["Sources: " + "; ".join(f"{f['id']} {f['source_name']} ({f['as_of']})" for f in facts)]
        used = list(fact_ids)
        default_title = "Side by side"
        params = {"fact_ids": list(fact_ids)}
        chart_ref = None
    elif chart_n and dates and len(dates) == 2:
        chart, _entry = load_chart(project, chart_n)
        if not 0 <= series_index < len(chart["series"]):
            raise GraphicsError("That chart has no such line.")
        series = chart["series"][series_index]
        points = [resolve_point(series, d) for d in dates]
        if points[0][0] == points[1][0]:
            raise GraphicsError("Those two dates land on the same observation. Pick dates further apart.")
        freq = series.frequency or "daily"
        panels = [{"label": fmt.fmt_date(d, freq), "value": charts.fmt_compact(v, chart["units"], chart.get("decimals", 2)),
                   "when": series.title} for d, v in points]
        sources = [{"name": f"{series.title} - {series.source_name}", "url": series.source_url}]
        source_lines = [f"Source: {series.source_name}. {series.title}, observations on "
                        f"{fmt.fmt_date(points[0][0], freq)} and {fmt.fmt_date(points[1][0], freq)}."]
        default_title = series.title
        params = {"dates": [p[0].isoformat() for p in points], "series_index": series_index}
        chart_ref = int(chart_n)
    else:
        raise GraphicsError("Pick two facts, or a chart and two dates.")
    if title.strip():
        title, title_used = _clean(title, project, 10, "Card title")
        used = list(dict.fromkeys(used + title_used))
    else:
        title = default_title
    number, folder = _next(project)
    files = {}
    for size_name in SIZES:
        name = f"g{number:02d}_comparison_{size_name}.png"
        _draw_comparison(size_name, theme, title, panels, source_lines).save(folder / name)
        files[size_name] = f"graphics/{name}"
    return _record(project_id, "comparison", title, files, "png", used, chart_ref, sources,
                   {"_n": number, "panels": panels, **params})


# ---------------------------------------------------------------- 4. mechanism flow
def _draw_flow(size_name: str, theme: dict, title: str, steps: list[str], source_lines: list[str]) -> Image.Image:
    image, draw = _canvas(size_name, theme)
    w, h = image.size
    portrait = h > w
    margin = int(w * 0.06)
    top = int(h * (0.13 if portrait else 0.08))
    _block(draw, title, (margin, top, w - 2 * margin, int(h * 0.14)), theme["ink"], 64 if portrait else 68, max_lines=2)
    area_top = top + int(h * (0.15 if portrait else 0.22))
    area_bottom = int(h * (0.68 if portrait else 0.78))
    n = len(steps)
    arrow = int((h if portrait else w) * 0.045)
    accent = theme["accent"]
    if portrait:
        box_h = (area_bottom - area_top - arrow * (n - 1)) // n
        boxes = [(margin, area_top + i * (box_h + arrow), w - 2 * margin, box_h) for i in range(n)]
    else:
        box_w = (w - 2 * margin - arrow * (n - 1)) // n
        boxes = [(margin + i * (box_w + arrow), area_top, box_w, area_bottom - area_top) for i in range(n)]
    for i, (text, (x, y, bw, bh)) in enumerate(zip(steps, boxes)):
        color = theme["series"][i % len(theme["series"])]
        draw.rounded_rectangle((x, y, x + bw, y + bh), radius=26, outline=color, width=6)
        draw.text((x + 26, y + 18), str(i + 1), font=_font(34, True), fill=theme["muted"])
        pad = 36
        _block(draw, text, (x + pad, y + 64, bw - 2 * pad, bh - 96), theme["ink"], 62 if portrait else 56,
               max_lines=4, align="center", valign="middle")
        if i < n - 1:
            if portrait:
                cx, y0 = x + bw // 2, y + bh
                draw.line((cx, y0 + 8, cx, y0 + arrow - 22), fill=accent, width=10)
                draw.polygon([(cx - 22, y0 + arrow - 28), (cx + 22, y0 + arrow - 28), (cx, y0 + arrow - 4)], fill=accent)
            else:
                cy, x0 = y + bh // 2, x + bw
                draw.line((x0 + 8, cy, x0 + arrow - 22, cy), fill=accent, width=10)
                draw.polygon([(x0 + arrow - 28, cy - 22), (x0 + arrow - 28, cy + 22), (x0 + arrow - 4, cy)], fill=accent)
    _footer(draw, image.size, theme, source_lines)
    return image


def flow_diagram(project_id: str, steps: list[str], title: str = "") -> dict:
    """A -> B -> C. Steps may include {F1}-style facts; any other number is refused."""
    project = projects.load(project_id)
    steps = [s for s in (steps or []) if s and s.strip()]
    if not 3 <= len(steps) <= 4:
        raise GraphicsError("A flow diagram needs 3 or 4 steps.")
    by_id = {f["id"]: f for f in project.get("facts", [])}
    cleaned, used = [], []
    for i, step in enumerate(steps, 1):
        text, ids = _clean(step, project, 12, f"Step {i}")
        cleaned.append(text)
        used += [x for x in ids if x not in used]
    if title.strip():
        title, title_used = _clean(title, project, 10, "Diagram title")
        used += [x for x in title_used if x not in used]
    else:
        title = "How it connects"
    facts = [by_id[i] for i in used]
    source_lines = (["Sources: " + "; ".join(f"{f['id']} {f['source_name']} ({f['as_of']})" for f in facts)] if facts
                    else ["Diagram of the mechanism; no figures shown."])
    theme_name, theme = _theme(project)
    number, folder = _next(project)
    files = {}
    for size_name in SIZES:
        name = f"g{number:02d}_flow_{size_name}.png"
        _draw_flow(size_name, theme, title, cleaned, source_lines).save(folder / name)
        files[size_name] = f"graphics/{name}"
    return _record(project_id, "flow", title, files, "png", used, None, _fact_sources(facts),
                   {"_n": number, "steps": cleaned, "raw_steps": steps})
