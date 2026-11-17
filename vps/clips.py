"""Clip plan: find 3-5 self-contained 30-60 second clips in a recorded video's transcript.

Timestamps always come from the transcript file. When a .txt has no timestamps they are
estimated from word count and clearly marked as estimates.
"""
from __future__ import annotations

import re

from . import compliance
from .numbers import STRAY_NUMBER

MIN_SECONDS, MAX_SECONDS = 30.0, 60.0
WORDS_PER_SECOND = 2.5  # ~150 words a minute, used only when a .txt has no timestamps

_SRT_TIME = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")
_TXT_TIME = re.compile(r"^\s*[\[(]?(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[\])]?\s*[-:]?\s*(.*)$")
_SENTENCE_END = re.compile(r"[.!?][\"')\]]?\s*$")
_WEAK_START = re.compile(r"^(and|but|so|because|which|that|this|it|they|those|these|then|also|or)\b", re.IGNORECASE)
_HOOK_WORDS = re.compile(
    r"\b(here's|here is|why|what this means|what it means|your|you|wallet|mortgage|rent|groceries|paycheck|401|"
    r"job|surprising|nobody|actually|the truth|most people|imagine|think about)\b", re.IGNORECASE)


def format_time(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def parse_srt(text: str) -> list[dict]:
    segments = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").strip()):
        lines = [line for line in block.split("\n") if line.strip()]
        for i, line in enumerate(lines):
            match = _SRT_TIME.search(line)
            if match:
                g = [int(x) for x in match.groups()]
                start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
                end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
                body = " ".join(re.sub(r"<[^>]+>", "", part).strip() for part in lines[i + 1:]).strip()
                if body and end > start:
                    segments.append({"start": start, "end": end, "text": body})
                break
    return segments


def parse_txt(text: str) -> tuple[list[dict], bool]:
    """Returns (segments, estimated). Handles '[1:23] words', a time on its own line
    (YouTube's copy-paste transcript), or plain prose with no times at all."""
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    stamped: list[tuple[float, str]] = []
    pending: float | None = None
    plain_lines = 0
    for line in lines:
        match = _TXT_TIME.match(line)
        if match and (match.group(4) == "" or not line[0].isalpha()):
            seconds = int(match.group(1) or 0) * 3600 + int(match.group(2)) * 60 + int(match.group(3))
            if match.group(4):
                stamped.append((seconds, match.group(4)))
                pending = None
            else:
                pending = seconds
        elif pending is not None:
            stamped.append((pending, line))
            pending = None
        else:
            plain_lines += 1
            if stamped:
                stamped[-1] = (stamped[-1][0], stamped[-1][1] + " " + line)

    if len(stamped) >= 2 and plain_lines <= len(stamped):
        segments = []
        for i, (start, body) in enumerate(stamped):
            end = stamped[i + 1][0] if i + 1 < len(stamped) else start + max(2.0, len(body.split()) / WORDS_PER_SECOND)
            if end > start:
                segments.append({"start": float(start), "end": float(end), "text": body})
        return segments, False

    # No usable timestamps: split into sentences and estimate times from word count.
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", " ".join(lines)) if s.strip()]
    segments, clock = [], 0.0
    for sentence in sentences:
        duration = max(1.0, len(sentence.split()) / WORDS_PER_SECOND)
        segments.append({"start": clock, "end": clock + duration, "text": sentence})
        clock += duration
    return segments, True


def parse_transcript(filename: str, text: str) -> tuple[list[dict], bool]:
    if filename.lower().endswith(".srt") or _SRT_TIME.search(text):
        return parse_srt(text), False
    return parse_txt(text)


def _starts_thought(segments: list[dict], i: int) -> bool:
    if _WEAK_START.match(segments[i]["text"]):
        return False
    return i == 0 or bool(_SENTENCE_END.search(segments[i - 1]["text"]))


def _score(segments: list[dict], start: int, end: int) -> float:
    text = " ".join(s["text"] for s in segments[start:end + 1])
    first = segments[start]["text"]
    duration = segments[end]["end"] - segments[start]["start"]
    score = 2.0 * len(_HOOK_WORDS.findall(first)) + 0.4 * len(_HOOK_WORDS.findall(text))
    score += 2.0 if "?" in first else 0.0
    score += 1.0 if STRAY_NUMBER.search(first) else 0.0
    score += 1.5 if _SENTENCE_END.search(segments[end]["text"]) else -2.0
    score += 1.0 if 38 <= duration <= 55 else 0.0
    return score


def heuristic_picks(segments: list[dict], want: int = 5) -> list[dict]:
    """Rule-based fallback: windows that begin and end on a complete sentence.

    Picks the set of non-overlapping windows with the most clips (up to `want`), and
    among those the strongest opening lines.
    """
    candidates: list[tuple[float, int, int]] = []  # (score, start, end)
    for start in range(len(segments)):
        if not _starts_thought(segments, start):
            continue
        for end in range(start, len(segments)):
            duration = segments[end]["end"] - segments[start]["start"]
            if duration > MAX_SECONDS:
                break
            if duration >= MIN_SECONDS and _SENTENCE_END.search(segments[end]["text"]):
                candidates.append((_score(segments, start, end), start, end))
    candidates.sort(key=lambda c: (c[2], c[1]))

    # best[k] = (total score, picks) for the best k non-overlapping clips seen so far,
    # tracked per "last segment used" so a later clip can only start after it.
    best: dict[tuple[int, int], tuple[float, list]] = {(0, -1): (0.0, [])}
    for score, start, end in candidates:
        for (count, last), (total, picks) in list(best.items()):
            if start <= last or count >= want:
                continue
            key = (count + 1, end)
            if key not in best or total + score > best[key][0]:
                best[key] = (total + score, picks + [(start, end)])
    most = max(count for count, _ in best)
    _total, chosen = max((value for (count, _), value in best.items() if count == most), key=lambda v: v[0])
    return [{"start_segment": s, "end_segment": e, "caption_hook": "",
             "why": "Starts and ends on a complete thought; strong opening line."} for s, e in chosen]


def _caption_from_text(text: str) -> str:
    first = re.split(r"(?<=[.!?])\s+", text.strip())[0]
    words = first.split()
    return " ".join(words[:12]) + ("..." if len(words) > 12 else "")


def finalize_clips(segments: list[dict], picks: list[dict], estimated: bool) -> list[dict]:
    """Validate picks against the real transcript and compute timestamps from it."""
    clips = []
    taken: list[tuple[int, int]] = []
    for pick in picks:
        start, end = int(pick["start_segment"]), int(pick["end_segment"])
        if not (0 <= start <= end < len(segments)):
            continue
        if any(not (end < a or start > b) for a, b in taken):
            continue
        # Stretch or trim to land inside 30-60 seconds where the transcript allows it.
        while segments[end]["end"] - segments[start]["start"] < MIN_SECONDS and end + 1 < len(segments):
            end += 1
        while segments[end]["end"] - segments[start]["start"] > MAX_SECONDS and end > start:
            end -= 1
        duration = segments[end]["end"] - segments[start]["start"]
        if not MIN_SECONDS <= duration <= MAX_SECONDS:
            continue
        text = " ".join(s["text"] for s in segments[start:end + 1])
        caption = " ".join((pick.get("caption_hook") or "").split())
        notes = []
        # A caption may only use a number the presenter actually says in that clip.
        for number in STRAY_NUMBER.findall(caption):
            if number.strip() and number.strip() not in text:
                caption = ""
                notes.append("Suggested caption used a number not said in the clip; replaced with the opening line.")
                break
        if caption and not compliance.is_clean(caption):
            caption = ""
            notes.append("Suggested caption read like advice; replaced with the opening line.")
        if not caption:
            caption = _caption_from_text(text)
        flags = compliance.scan_text(text)
        if any(flags.values()):
            notes.append("This part of the transcript contains wording that reads like advice or a prediction. Review before posting.")
        taken.append((start, end))
        clips.append({
            "n": len(clips) + 1, "start": format_time(segments[start]["start"]), "end": format_time(segments[end]["end"]),
            "start_seconds": round(segments[start]["start"], 1), "end_seconds": round(segments[end]["end"], 1),
            "duration_seconds": round(duration), "caption": caption, "why": pick.get("why", ""),
            "opens_with": _caption_from_text(text), "text": text, "notes": notes, "estimated_times": estimated,
        })
        if len(clips) == 5:
            break
    return clips


def plan_clips(filename: str, text: str, llm_picker=None) -> dict:
    """llm_picker(segments) -> picks, or None to use the rule-based picker."""
    segments, estimated = parse_transcript(filename, text)
    if not segments:
        return {"clips": [], "source": "none", "estimated_times": False, "message": "No transcript text found in that file."}
    total = segments[-1]["end"] - segments[0]["start"]
    if total < MIN_SECONDS:
        return {"clips": [], "source": "none", "estimated_times": estimated,
                "message": "The transcript is shorter than 30 seconds, so there is nothing to clip."}
    source, message, clips = "rules", "", []
    if llm_picker:
        try:
            clips = finalize_clips(segments, llm_picker(segments), estimated)
            source = "llm"
        except Exception as exc:  # any LLM problem falls back to the rule-based picker
            message = f"{exc} Used the rule-based picker instead."
    if len(clips) < 3:
        fallback = finalize_clips(segments, heuristic_picks(segments), estimated)
        if len(fallback) > len(clips):
            clips, source = fallback, "rules"
    if estimated:
        message = (message + " " if message else "") + (
            "This transcript has no timestamps, so times are estimates from word count. Upload the .srt for exact times.")
    if len(clips) < 3 and not message:
        message = "Fewer than three self-contained 30-60 second clips were found in this transcript."
    return {"clips": clips, "source": source, "estimated_times": estimated, "message": message.strip(),
            "transcript_seconds": round(total), "segments": len(segments)}
