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


# ---------------------------------------------------------------- spoken fact-check
_ONES = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1_000}
_UNIT_WORDS = {"percent", "%", "dollars", "dollar", "bucks", "points", "point", "basis", "million", "billion",
               "trillion", "thousand", "bps", "cents"}
_WORD = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?|[A-Za-z]+(?:'[a-z]+)?|%")


def _number_words(tokens: list[str], i: int) -> tuple[float, int, bool] | None:
    """Parse spelled-out numbers starting at tokens[i]: 'seven point one one', 'two thousand one hundred'.
    Returns (value, tokens used, had a decimal point)."""
    first, second = tokens[i].lower(), tokens[i + 1].lower() if i + 1 < len(tokens) else ""
    if first in ("nineteen", "twenty") and (second in _TENS or _ONES.get(second, 0) >= 10):
        # a year said in words: "twenty twenty six", "nineteen ninety nine"
        year = (19 if first == "nineteen" else 20) * 100 + (_TENS.get(second) or _ONES[second])
        used = 2
        third = tokens[i + 2].lower() if i + 2 < len(tokens) else ""
        if second in _TENS and 0 < _ONES.get(third, 0) < 10:
            year, used = year + _ONES[third], 3
        return float(year), used, False
    total, current, used, seen = 0.0, 0.0, 0, False
    while i + used < len(tokens):
        word = tokens[i + used].lower()
        if word in _ONES:
            current += _ONES[word]
        elif word in _TENS:
            current += _TENS[word]
        elif word in _SCALES and seen:
            current = max(current, 1) * _SCALES[word]
            if word == "thousand":
                total, current = total + current, 0.0
        elif word == "and" and seen and i + used + 1 < len(tokens) and tokens[i + used + 1].lower() in {**_ONES, **_TENS}:
            used += 1
            continue
        elif word == "a" and not seen and i + used + 1 < len(tokens) and tokens[i + used + 1].lower() in _SCALES:
            current = 1.0
        else:
            break
        seen = True
        used += 1
    if not seen:
        return None
    value, decimal = total + current, False
    if i + used + 1 < len(tokens) and tokens[i + used].lower() == "point" and tokens[i + used + 1].lower() in _ONES:
        digits, j = "", i + used + 1
        while j < len(tokens) and tokens[j].lower() in _ONES and _ONES[tokens[j].lower()] < 10:
            digits += str(_ONES[tokens[j].lower()])
            j += 1
        if digits:
            value, used, decimal = float(f"{int(value)}.{digits}"), j - i, True
    return value, used, decimal


def spoken_numbers(text: str) -> list[dict]:
    """Numbers said in a line of transcript, as digits or as words. Plain small counts
    ('three reasons') and names like 401(k) or 10-year are not treated as data."""
    from .numbers import ALLOWED_TERMS
    text = ALLOWED_TERMS.sub(" ", text)
    tokens = _WORD.findall(text)
    found, i = [], 0
    while i < len(tokens):
        token = tokens[i]
        nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
        if token[0].isdigit() or token[0] == "$":
            raw = token.strip("$%").replace(",", "")
            try:
                value = float(raw)
            except ValueError:
                i += 1
                continue
            has_unit = token.startswith("$") or token.endswith("%") or nxt in _UNIT_WORDS
            decimals = len(raw.partition(".")[2])
            spoken, used = token + (f" {nxt}" if nxt in _UNIT_WORDS else ""), 1
        else:
            parsed = _number_words(tokens, i)
            if not parsed:
                i += 1
                continue
            value, used, decimal = parsed
            after = tokens[i + used].lower() if i + used < len(tokens) else ""
            has_unit = decimal or after in _UNIT_WORDS
            decimals = len(str(value).partition(".")[2]) if decimal else 0
            spoken = " ".join(tokens[i:i + used]) + (f" {after}" if after in _UNIT_WORDS else "")
        if has_unit or value > 12:
            unit_text = spoken.lower()
            unit = ("$" if "$" in unit_text or any(w in unit_text.split() for w in ("dollars", "dollar", "bucks"))
                    else "%" if "%" in unit_text or any(w in unit_text.split() for w in ("percent", "points", "basis", "bps")) else "")
            found.append({"spoken": spoken, "value": value, "decimals": decimals, "unit": unit})
        i += used
    return found


def _fact_numbers(facts: list[dict]) -> list[tuple[float, str, str, str]]:
    """(number, unit, fact id, the fact's display value) for every number in a sourced fact."""
    from .numbers import _tokens
    out = []
    for fact in facts:
        if fact.get("status") == "verify":
            continue
        for number, unit, _raw in _tokens(f"{fact.get('claim', '')} {fact.get('value', '')} {fact.get('as_of', '')}"):
            try:
                out.append((float(number), unit, fact.get("id", ""), fact.get("value", "") or fact.get("claim", "")[:60]))
            except ValueError:
                continue
    return out


def spoken_fact_check(segments: list[dict], facts: list[dict]) -> dict:
    """Compare every number said on the recording with the fact sheet.

    exact match -> fine. A rounded form of a fact ('about seven percent' for 7.11%) ->
    listed as 'rounded'. Anything else -> 'unverified', with its timestamp, so it can
    be cut or checked before publishing."""
    known = _fact_numbers(facts)
    flags, checked, matched = [], 0, 0
    for segment in segments:
        for item in spoken_numbers(segment["text"]):
            checked += 1
            value = item["value"]
            # a spoken percentage is compared with percentage facts, dollars with dollar facts
            pool = [k for k in known if not item["unit"] or k[1] == item["unit"]]
            if any(abs(value - number) < 1e-9 for number, *_ in pool):
                matched += 1
                continue
            entry = {"seconds": round(segment["start"], 1), "time": format_time(segment["start"]),
                     "spoken": item["spoken"], "text": segment["text"]}
            rounded = next(((n, fid, shown) for n, _unit, fid, shown in pool
                            if n != value and abs(round(n, item["decimals"]) - value) < 1e-9), None)
            if rounded:
                entry.update(status="rounded", fact_id=rounded[1], fact_value=rounded[2],
                             note=f"Looks like a rounded {rounded[2]} ({rounded[1]}). Fine if you said \u201cabout\u201d.")
            else:
                near = min(pool, key=lambda k: abs(k[0] - value) / max(abs(k[0]), 1e-9), default=None)
                close = near is not None and abs(near[0] - value) / max(abs(near[0]), 1e-9) <= 0.15
                entry.update(status="unverified", fact_id=near[2] if close else "", fact_value=near[3] if close else "",
                             note=(f"Not on the fact sheet. The closest fact is {near[3]} ({near[2]})." if close
                                   else "Not on the fact sheet. Cut it, or verify it against a primary source."))
            flags.append(entry)
    unverified = sum(1 for f in flags if f["status"] == "unverified")
    return {"checked": checked, "matched": matched, "unverified": unverified, "rounded": len(flags) - unverified, "flags": flags,
            "summary": (f"{checked} spoken number(s) checked: {matched} match the fact sheet exactly, "
                        f"{len(flags) - unverified} look rounded, {unverified} are not on the fact sheet.")}


def caption_chunks(segments: list[dict], start: float, end: float, max_words: int = 5) -> list[dict]:
    """Short on-screen captions for a clip, timed from the transcript (times relative to the clip start)."""
    chunks = []
    for segment in segments:
        if segment["end"] <= start or segment["start"] >= end:
            continue
        words = segment["text"].split()
        if not words:
            continue
        groups = [words[i:i + max_words] for i in range(0, len(words), max_words)]
        span = segment["end"] - segment["start"]
        cursor = segment["start"]
        for group in groups:
            length = span * len(group) / len(words)
            a, b = max(cursor, start), min(cursor + length, end)
            if b - a > 0.05:
                chunks.append({"start": round(a - start, 2), "end": round(b - start, 2), "text": " ".join(group)})
            cursor += length
    return chunks
