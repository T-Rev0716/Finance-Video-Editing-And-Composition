"""Optional local tools (ffmpeg, ffprobe). Everything that uses them has a fallback."""
from __future__ import annotations

import json
import shutil
import subprocess


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def ffprobe_path() -> str | None:
    return shutil.which("ffprobe")


class MediaError(RuntimeError):
    """ffmpeg failed. The message carries the end of its error output."""


def run(cmd: list[str], stdin_bytes: bytes | None = None, timeout: float | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, input=stdin_bytes, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        tail = result.stderr.decode("utf-8", errors="replace").strip().splitlines()[-3:]
        raise MediaError(" ".join(tail) or f"{cmd[0]} exited with code {result.returncode}")
    return result


def probe(path: str) -> dict:
    """Duration and whether the file has video/audio. Falls back to the file extension."""
    info = {"duration": 0.0, "has_video": not path.lower().endswith((".wav", ".mp3", ".m4a", ".flac")),
            "has_audio": True, "width": 0, "height": 0, "probed": False}
    tool = ffprobe_path()
    if not tool:
        return info
    try:
        out = run([tool, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                   "-of", "json", path], timeout=60).stdout
        data = json.loads(out)
    except (MediaError, ValueError, subprocess.TimeoutExpired, OSError):
        return info
    streams = data.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video"]
    info.update(duration=float(data.get("format", {}).get("duration") or 0), has_video=bool(video),
                has_audio=any(s.get("codec_type") == "audio" for s in streams), probed=True)
    if video:
        info.update(width=int(video[0].get("width") or 0), height=int(video[0].get("height") or 0))
    return info
