"""Local post-production: transcription, dead-air stripping and 9:16 short export.

Everything runs on this computer. faster-whisper (GPU if present) and ffmpeg are optional:
without faster-whisper you upload an .srt instead; without ffmpeg you get cut lists and
caption files to use in your editor.
"""
from __future__ import annotations

import re
import shutil
import wave
from pathlib import Path
from typing import BinaryIO, Callable

from PIL import Image, ImageDraw

from . import clips, media, projects, store

RECORDING_TYPES = (".mp4", ".mov", ".mkv", ".wav", ".mp3")
MIN_SILENCE = 0.45
NOISE_DB = -35.0
KEEP_PAD = 0.08  # leave a breath on each side of a cut
MAX_FILTER_CHARS = 28000  # stay under the Windows command-line limit


class Unavailable(RuntimeError):
    """An optional tool is missing or a request cannot be done. The message tells the user what to do."""


# ---------------------------------------------------------------- what this computer can do
def _cuda_available() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def capabilities() -> dict:
    try:
        import faster_whisper  # noqa: F401
        whisper = True
    except ImportError:
        whisper = False
    gpu = _cuda_available() if whisper else False
    return {
        "faster_whisper": whisper, "gpu": gpu, "ffmpeg": bool(media.ffmpeg_path()),
        "transcribe_note": ("Transcribes on your NVIDIA GPU." if gpu else "Transcribes on the CPU (slower)." if whisper
                            else "faster-whisper is not installed. Run: pip install faster-whisper  (or upload an .srt instead)."),
        "ffmpeg_note": ("" if media.ffmpeg_path() else
                        "ffmpeg is not installed, so cuts and shorts are exported as cut lists and caption files for your editor."),
    }


# ---------------------------------------------------------------- the recording
def _folder(project_id: str) -> Path:
    path = projects.project_dir(project_id) / "recording"
    path.mkdir(exist_ok=True)
    return path


def _register(project_id: str, path: Path, source: str) -> dict:
    info = media.probe(str(path))
    project = projects.load(project_id)
    project["recording"] = {"path": str(path), "name": path.name, "source": source, "duration": round(info["duration"], 2),
                            "has_video": info["has_video"], "added": store.now_iso()}
    projects.save(project)
    return project["recording"]


def add_upload(project_id: str, filename: str, source: BinaryIO) -> dict:
    """Copy an uploaded recording into the project."""
    if Path(filename).suffix.lower() not in RECORDING_TYPES:
        raise Unavailable("Use a .mp4, .mov, .mkv, .wav or .mp3 recording (or a .srt / .txt transcript).")
    target = _folder(project_id) / store.safe_name(filename, "recording")
    with open(target, "wb") as out:
        shutil.copyfileobj(source, out, 4 * 1024 * 1024)
    if target.stat().st_size == 0:
        target.unlink()
        raise Unavailable("That file is empty.")
    return _register(project_id, target, "upload")


def add_path(project_id: str, path_text: str) -> dict:
    """Use a recording where it already is on this computer (no copy - good for multi-GB files)."""
    path = Path(path_text.strip().strip('"')).expanduser()
    if path.suffix.lower() not in RECORDING_TYPES:
        raise Unavailable("Use a .mp4, .mov, .mkv, .wav or .mp3 recording.")
    if not path.is_file():
        raise Unavailable(f"No file found at {path}.")
    return _register(project_id, path.resolve(), "path")


def recording_path(project: dict) -> Path:
    record = project.get("recording")
    if not record:
        raise Unavailable("Add your recording first (upload it, or paste its path).")
    path = Path(record["path"])
    if not path.is_file():
        raise Unavailable(f"The recording is no longer at {path}. Add it again.")
    return path


# ---------------------------------------------------------------- transcription
def segments_to_srt(segments: list[dict]) -> str:
    def stamp(seconds: float) -> str:
        ms = int(round(seconds * 1000))
        hours, ms = divmod(ms, 3_600_000)
        minutes, ms = divmod(ms, 60_000)
        secs, ms = divmod(ms, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

    blocks = [f"{i}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text'].strip()}\n" for i, s in enumerate(segments, 1)]
    return "\n".join(blocks)


def _load_model(model_name: str):
    """GPU first when there is one; fall back to CPU if the GPU model cannot start."""
    from faster_whisper import WhisperModel
    gpu = _cuda_available()
    name = model_name if model_name and model_name != "auto" else ("large-v3" if gpu else "small")
    if gpu:
        try:
            return WhisperModel(name, device="cuda", compute_type="float16"), f"{name} on GPU"
        except Exception:
            pass
    return WhisperModel(name, device="cpu", compute_type="int8"), f"{name} on CPU"


def transcribe(path: Path, model_name: str = "auto", progress: Callable[[str], None] = lambda _m: None) -> tuple[list[dict], str]:
    """Speech to timed segments with faster-whisper. Returns (segments, which model ran)."""
    try:
        model, label = _load_model(model_name)
    except ImportError:
        raise Unavailable("faster-whisper is not installed. Run: pip install faster-whisper  - or upload an .srt transcript instead.") from None
    progress(f"Transcribing with {label}")
    result, info = model.transcribe(str(path), vad_filter=True)
    total = getattr(info, "duration", 0) or 0
    segments = []
    for item in result:
        text = item.text.strip()
        if text:
            segments.append({"start": float(item.start), "end": float(item.end), "text": text})
            if total and len(segments) % 20 == 0:
                progress(f"Transcribing: {min(99, int(item.end / total * 100))}%")
    if not segments:
        raise Unavailable("No speech was found in that recording.")
    return segments, label


# ---------------------------------------------------------------- dead air
_SILENCE_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


def parse_silencedetect(log: str) -> list[tuple[float, float]]:
    """Read ffmpeg's silencedetect output into (start, end) pairs."""
    silences, start = [], None
    for line in log.splitlines():
        if (m := _SILENCE_START.search(line)):
            start = max(0.0, float(m.group(1)))
        elif (m := _SILENCE_END.search(line)) and start is not None:
            silences.append((start, float(m.group(1))))
            start = None
    return silences


def wav_silences(path: Path, min_silence: float = MIN_SILENCE, noise_db: float = NOISE_DB) -> tuple[list[tuple[float, float]], float]:
    """Fallback without ffmpeg, for .wav files: quiet stretches found with the standard library."""
    import numpy as np
    with wave.open(str(path), "rb") as audio:
        rate, channels, width, frames = audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getnframes()
        raw = audio.readframes(frames)
    if width != 2:
        raise Unavailable("Only 16-bit .wav files can be scanned without ffmpeg. Install ffmpeg for other formats.")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32).reshape(-1, channels).mean(axis=1) / 32768.0
    window = max(1, int(rate * 0.01))
    usable = len(samples) // window * window
    peaks = np.abs(samples[:usable]).reshape(-1, window).max(axis=1)
    quiet = peaks < 10 ** (noise_db / 20)
    silences, start = [], None
    for i, flag in enumerate(quiet):
        if flag and start is None:
            start = i
        if not flag and start is not None:
            if (i - start) * 0.01 >= min_silence:
                silences.append((start * 0.01, i * 0.01))
            start = None
    if start is not None and (len(quiet) - start) * 0.01 >= min_silence:
        silences.append((start * 0.01, len(quiet) * 0.01))
    return silences, frames / rate


def detect_silences(path: Path, min_silence: float = MIN_SILENCE, noise_db: float = NOISE_DB) -> tuple[list[tuple[float, float]], float, str]:
    """(silences, duration, method)."""
    tool = media.ffmpeg_path()
    if tool:
        import subprocess
        result = subprocess.run([tool, "-hide_banner", "-nostats", "-i", str(path), "-af",
                                 f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
                                capture_output=True)
        log = result.stderr.decode("utf-8", errors="replace")
        if result.returncode != 0:
            raise Unavailable("ffmpeg could not read that recording: " + " ".join(log.strip().splitlines()[-2:]))
        duration = media.probe(str(path))["duration"]
        silences = parse_silencedetect(log)
        if silences and duration:
            silences = [(a, min(b, duration)) for a, b in silences]
        return silences, duration, "ffmpeg"
    if path.suffix.lower() == ".wav":
        silences, duration = wav_silences(path, min_silence, noise_db)
        return silences, duration, "wave"
    raise Unavailable("Scanning this file for silence needs ffmpeg (a .wav file works without it).")


def keep_segments(silences: list[tuple[float, float]], duration: float, pad: float = KEEP_PAD) -> list[tuple[float, float]]:
    """The parts to keep: everything outside the silences, with a small pad left around speech."""
    keeps, cursor = [], 0.0
    for start, end in sorted(silences):
        cut_from, cut_to = start + pad, end - pad
        if cut_to - cut_from <= 0.05:
            continue
        if cut_from > cursor:
            keeps.append((round(cursor, 3), round(cut_from, 3)))
        cursor = max(cursor, cut_to)
    if duration > cursor:
        keeps.append((round(cursor, 3), round(duration, 3)))
    return keeps


def _select_expr(keeps: list[tuple[float, float]]) -> str:
    return "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in keeps)


def trim_command(source: Path, keeps: list[tuple[float, float]], out: Path, has_video: bool) -> list[str]:
    expr = _select_expr(keeps)
    cmd = [media.ffmpeg_path() or "ffmpeg", "-y", "-loglevel", "error", "-i", str(source)]
    if has_video:
        cmd += ["-vf", f"select='{expr}',setpts=N/FRAME_RATE/TB", "-af", f"aselect='{expr}',asetpts=N/SR/TB",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-af", f"aselect='{expr}',asetpts=N/SR/TB"]
    return cmd + [str(out)]


def _write_wav_keeps(source: Path, keeps: list[tuple[float, float]], out: Path) -> None:
    with wave.open(str(source), "rb") as audio:
        params, rate = audio.getparams(), audio.getframerate()
        with wave.open(str(out), "wb") as target:
            target.setparams(params)
            for start, end in keeps:
                audio.setpos(min(int(start * rate), audio.getnframes()))
                target.writeframes(audio.readframes(int((end - start) * rate)))


def strip_dead_air(project_id: str, min_silence: float = MIN_SILENCE) -> dict:
    """Find silences longer than min_silence and write a tightened copy (the original is never touched)."""
    project = projects.load(project_id)
    source = recording_path(project)
    silences, duration, method = detect_silences(source, min_silence)
    keeps = keep_segments(silences, duration)
    removed = round(duration - sum(b - a for a, b in keeps), 2)
    folder = _folder(project_id)
    result = {"min_silence": min_silence, "silences": len(silences), "removed_seconds": removed,
              "original_seconds": round(duration, 2), "method": method, "file": "", "note": "",
              "cut_list": "recording/cut_list.json", "keeps": [[a, b] for a, b in keeps]}
    store.write_json(folder / "cut_list.json", {"source": str(source), "min_silence": min_silence,
                                                "keep": result["keeps"], "removed_seconds": removed})
    if not silences:
        result["note"] = f"No silences longer than {min_silence} s were found."
    elif method == "ffmpeg":
        has_video = project["recording"].get("has_video", True)
        while len(_select_expr(keeps)) > MAX_FILTER_CHARS and len(keeps) > 1:  # merge the smallest gap until it fits
            gaps = [keeps[i + 1][0] - keeps[i][1] for i in range(len(keeps) - 1)]
            i = gaps.index(min(gaps))
            keeps[i:i + 2] = [(keeps[i][0], keeps[i + 1][1])]
        out = folder / f"{source.stem}_tight{'.mp4' if has_video else '.wav'}"
        try:
            media.run(trim_command(source, keeps, out, has_video))
            result["file"] = f"recording/{out.name}"
        except media.MediaError as exc:
            result["note"] = f"ffmpeg could not write the tightened file ({exc}). The cut list was saved."
    elif source.suffix.lower() == ".wav":
        out = folder / f"{source.stem}_tight.wav"
        _write_wav_keeps(source, keeps, out)
        result["file"] = f"recording/{out.name}"
        result["note"] = "Made with Python's wave module (ffmpeg is not installed)."
    project["dead_air"] = result
    projects.save(project)
    return result


# ---------------------------------------------------------------- 9:16 shorts
def caption_image(text: str, path: Path, width: int = 1080, height: int = 260) -> None:
    """One caption as a transparent PNG: white bold text with a black outline, centred."""
    from .graphics import _font, _wrap
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for size in (76, 66, 58, 50, 44):
        font = _font(size, True)
        lines = _wrap(draw, text, font, width - 120)
        if len(lines) <= 2:
            break
    line_height = int(font.size * 1.2)
    top = (height - line_height * len(lines[:2])) // 2
    for i, line in enumerate(lines[:2]):
        x = (width - draw.textlength(line, font=font)) / 2
        draw.text((x, top + i * line_height), line, font=font, fill="#ffffff", stroke_width=7, stroke_fill="#000000")
    image.save(path)


def short_command(source: Path, start: float, duration: float, out: Path, captions: list[dict], caption_files: list[Path],
                  chart: Path | None, has_video: bool, background: str = "0x1a1a19") -> list[str]:
    """The ffmpeg command for one 1080x1920 short.

    With a chart: chart on top, square camera crop underneath. Without: full-height camera crop.
    Audio-only recordings show the chart full screen. Captions are overlaid as images, so no
    subtitle filter or system font is needed."""
    cmd = [media.ffmpeg_path() or "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source)]
    index = 1
    chart_index = None
    if chart is not None:
        cmd += ["-loop", "1", "-framerate", "30", "-i", str(chart)]
        chart_index, index = index, index + 1
    first_caption = index
    for path in caption_files:
        cmd += ["-loop", "1", "-framerate", "30", "-i", str(path)]
    parts = [f"color=c={background}:s=1080x1920:r=30[bg]"]
    if has_video and chart_index is not None:
        parts += [f"[0:v]crop='min(iw,ih)':'min(iw,ih)',scale=1080:1080,setsar=1[cam]",
                  f"[{chart_index}:v]scale=1080:608,setsar=1[chart]",
                  "[bg][chart]overlay=0:150[b1]", "[b1][cam]overlay=0:790[v0]"]
        caption_y = 1500
    elif has_video:
        parts += ["[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[cam]",
                  "[bg][cam]overlay=0:0[v0]"]
        caption_y = 1300
    elif chart_index is not None:
        parts += [f"[{chart_index}:v]scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[chart]",
                  "[bg][chart]overlay=(W-w)/2:(H-h)/2[v0]"]
        caption_y = 1480
    else:
        parts += ["[bg]null[v0]"]
        caption_y = 830
    last = "v0"
    for i, caption in enumerate(captions):
        label = f"v{i + 1}"
        parts.append(f"[{last}][{first_caption + i}:v]overlay=0:{caption_y}:enable='between(t,{caption['start']:.2f},{caption['end']:.2f})'[{label}]")
        last = label
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-map", "0:a?", "-t", f"{duration:.3f}",
            "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    return cmd


def _transcript_segments(project_id: str) -> list[dict]:
    folder = projects.project_dir(project_id)
    for name in ("transcript.srt", "transcript.txt"):
        if (folder / name).exists():
            return clips.parse_transcript(name, (folder / name).read_text(encoding="utf-8"))[0]
    return []


def export_short(project_id: str, clip_n: int, chart_n: int | None = None) -> dict:
    """Export one planned clip as a 1080x1920 .mp4 with burned-in captions.
    Without ffmpeg (or without a recording) it writes the clip's captions and cut times instead."""
    project = projects.load(project_id)
    clip = next((c for c in (project.get("clips") or {}).get("clips", []) if c["n"] == int(clip_n)), None)
    if clip is None:
        raise Unavailable("That clip is not in the clip plan.")
    start, end = clip["start_seconds"], clip["end_seconds"]
    captions = clips.caption_chunks(_transcript_segments(project_id), start, end)
    folder = projects.project_dir(project_id) / "shorts"
    folder.mkdir(exist_ok=True)
    stem = f"clip_{int(clip_n):02d}"
    (folder / f"{stem}_captions.srt").write_text(segments_to_srt(captions), encoding="utf-8")
    result = {"clip": int(clip_n), "captions_file": f"shorts/{stem}_captions.srt", "file": "", "note": "",
              "start": start, "end": end, "chart_n": chart_n, "captions": len(captions)}

    chart_path, chart_vertical = None, None
    if chart_n:
        entry = next((c for c in project.get("charts", []) if c["n"] == int(chart_n)), None)
        if entry is None:
            raise Unavailable(f"This project has no chart {chart_n}.")
        chart_path = projects.project_dir(project_id) / "charts" / entry["files"]["1920x1080"]
        chart_vertical = projects.project_dir(project_id) / "charts" / entry["files"]["1080x1920"]

    try:
        source = recording_path(project)
    except Unavailable as exc:
        result["note"] = f"{exc} Captions for this clip were saved so you can cut it in your editor."
        return _save_short(project_id, project, result)
    if not media.ffmpeg_path():
        result["note"] = ("ffmpeg is not installed, so no video was made. The clip's captions (.srt) and cut times "
                          f"({clips.format_time(start)} to {clips.format_time(end)}) were saved for your editor.")
        return _save_short(project_id, project, result)

    work = folder / f"{stem}_captions"
    work.mkdir(exist_ok=True)
    caption_files = []
    for i, caption in enumerate(captions):
        path = work / f"cap_{i:03d}.png"
        caption_image(caption["text"], path)
        caption_files.append(path)
    has_video = project["recording"].get("has_video", True)
    out = folder / f"{stem}_9x16.mp4"
    chart_for_video = chart_path if has_video else chart_vertical
    try:
        media.run(short_command(source, start, end - start, out, captions, caption_files, chart_for_video, has_video))
        result["file"] = f"shorts/{out.name}"
    except media.MediaError as exc:
        result["note"] = f"ffmpeg could not make this short ({exc}). The captions file was saved."
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return _save_short(project_id, project, result)


def _save_short(project_id: str, project: dict, result: dict) -> dict:
    shorts = [s for s in project.get("shorts", []) if s["clip"] != result["clip"]] + [result]
    project["shorts"] = sorted(shorts, key=lambda s: s["clip"])
    projects.save(project)
    return result
