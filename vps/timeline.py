"""Exports from the recording-view cue log: YouTube chapters, a CMX3600 .edl and an .fcpxml.

Times come from the keys pressed while recording, so they describe the RAW recording.
Takes flagged "needs another take" are left out of the timelines and listed as notes.
"""
from __future__ import annotations

from xml.sax.saxutils import quoteattr

FPS = 30


def segments(cues: list[dict], total_seconds: float, cards: list[dict]) -> list[dict]:
    """Cue list -> segments with an end time and the card's title."""
    titles = {c["id"]: c["title"] for c in cards}
    ordered = sorted(cues, key=lambda c: c["start"])
    out = []
    for i, cue in enumerate(ordered):
        end = ordered[i + 1]["start"] if i + 1 < len(ordered) else max(total_seconds, cue["start"])
        if end <= cue["start"]:
            continue
        out.append({"card_id": cue["card_id"], "title": titles.get(cue["card_id"], cue["card_id"]),
                    "start": cue["start"], "end": end, "flagged": bool(cue.get("flagged"))})
    return out


def clock(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def timecode(seconds: float, fps: int = FPS) -> str:
    frames = int(round(seconds * fps))
    hours, rest = divmod(frames, 3600 * fps)
    minutes, rest = divmod(rest, 60 * fps)
    secs, frame = divmod(rest, fps)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frame:02d}"


def chapters_text(segs: list[dict]) -> str:
    """YouTube chapter lines. The last good take of each card wins; times are placed on a
    timeline with flagged takes removed, so they match a cut made from the EDL."""
    good = [s for s in segs if not s["flagged"]]
    last_take = {s["card_id"]: i for i, s in enumerate(good)}
    lines, position = [], 0.0
    for i, seg in enumerate(good):
        if last_take[seg["card_id"]] == i:
            lines.append(f"{clock(position)} {seg['title']}")
            position += seg["end"] - seg["start"]
    if lines and not lines[0].startswith("0:00"):
        lines[0] = "0:00 " + lines[0].split(" ", 1)[1]
    return "\n".join(lines) + ("\n" if lines else "")


def _kept(segs: list[dict]) -> list[dict]:
    good = [s for s in segs if not s["flagged"]]
    last_take = {s["card_id"]: i for i, s in enumerate(good)}
    return [s for i, s in enumerate(good) if last_take[s["card_id"]] == i]


def edl_text(title: str, segs: list[dict], fps: int = FPS) -> str:
    """CMX3600 edit decision list: one cut per kept take, in order, flagged takes skipped."""
    lines = [f"TITLE: {title[:60]}", "FCM: NON-DROP FRAME", ""]
    position = 0.0
    for number, seg in enumerate(_kept(segs), 1):
        length = seg["end"] - seg["start"]
        lines.append(f"{number:03d}  AX       AA/V  C        {timecode(seg['start'], fps)} {timecode(seg['end'], fps)} "
                     f"{timecode(position, fps)} {timecode(position + length, fps)}")
        lines.append(f"* FROM CLIP NAME: {seg['title']}")
        position += length
    skipped = [s for s in segs if s not in _kept(segs)]
    if skipped:
        lines.append("")
        lines += [f"* SKIPPED TAKE: {s['title']} at {timecode(s['start'], fps)}"
                  f"{' (flagged: needs another take)' if s['flagged'] else ' (an earlier take)'}" for s in skipped]
    return "\n".join(lines) + "\n"


def _t(seconds: float, fps: int = FPS) -> str:
    return f"{int(round(seconds * fps))}/{fps}s"


def fcpxml_text(title: str, segs: list[dict], total_seconds: float, media_uri: str = "file:///recording.mp4",
                fps: int = FPS) -> str:
    """Final Cut Pro XML (v1.9; DaVinci Resolve and Premiere can import it too).
    One clip per kept take with a marker carrying the card title. Relink the media if asked."""
    kept = _kept(segs)
    total = max(total_seconds, max((s["end"] for s in segs), default=0.0))
    sequence_length = sum(s["end"] - s["start"] for s in kept)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE fcpxml>", '<fcpxml version="1.9">', "  <resources>",
        f'    <format id="r1" name="FFVideoFormat1080p{fps}" frameDuration="1/{fps}s" width="1920" height="1080"/>',
        f'    <asset id="r2" name="recording" start="0s" duration="{_t(total, fps)}" hasVideo="1" hasAudio="1" format="r1">',
        f"      <media-rep kind=\"original-media\" src={quoteattr(media_uri)}/>", "    </asset>", "  </resources>",
        "  <library>", f"    <event name={quoteattr(title[:80])}>", f"      <project name={quoteattr(title[:80])}>",
        f'        <sequence format="r1" duration="{_t(sequence_length, fps)}" tcStart="0s" tcFormat="NDF">', "          <spine>",
    ]
    position = 0.0
    for seg in kept:
        length = seg["end"] - seg["start"]
        lines.append(f'            <asset-clip ref="r2" name={quoteattr(seg["title"][:80])} offset="{_t(position, fps)}" '
                     f'start="{_t(seg["start"], fps)}" duration="{_t(length, fps)}">')
        lines.append(f'              <marker start="{_t(seg["start"], fps)}" duration="1/{fps}s" value={quoteattr(seg["title"][:80])}/>')
        lines.append("            </asset-clip>")
        position += length
    lines += ["          </spine>", "        </sequence>", "      </project>", "    </event>", "  </library>", "</fcpxml>"]
    return "\n".join(lines) + "\n"


def export_all(project: dict, state: dict, media_uri: str = "") -> dict[str, str]:
    """All three exports as text, keyed by file name."""
    segs = segments(state.get("cues", []), state.get("total_seconds", 0), state["cards"])
    title = project.get("topic", "Video")
    return {
        "chapters.txt": chapters_text(segs),
        "timeline.edl": edl_text(title, segs),
        "timeline.fcpxml": fcpxml_text(title, segs, state.get("total_seconds", 0), media_uri or "file:///recording.mp4"),
    }
