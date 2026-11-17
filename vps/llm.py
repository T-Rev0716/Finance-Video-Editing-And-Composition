"""Optional LLM wording (Anthropic API). Wording only - the model never supplies a number.

The model is given the fact sheet and must refer to facts as {F7}. numbers.apply_facts
then inserts the fetched value and deletes any number the model typed itself.
If there is no API key, or the call fails for any reason, the caller falls back to the
built-in templates.
"""
from __future__ import annotations

import json

from pydantic import BaseModel

from .numbers import apply_facts, has_stray_number
from .voice import ILLUSTRATIVE_LABEL


class LLMUnavailable(Exception):
    """No key configured, or the request failed. The message is shown to the user."""


class Cause(BaseModel):
    cause: str
    chart: int
    bullets: list[str]


class BrollIdea(BaseModel):
    section: str
    idea: str
    prompt: str


class Wording(BaseModel):
    hook: list[str]
    what_happened: list[str]
    causes: list[Cause]
    mortgage: list[str]
    job: list[str]
    groceries: list[str]
    retirement: list[str]
    watch_takeaway: str
    closing_line: str
    cta: str
    titles: list[str]
    thumbnails: list[str]
    broll: list[BrollIdea]
    description_summary: str


class ClipPick(BaseModel):
    start_segment: int
    end_segment: int
    caption_hook: str
    why: str


class ClipPlan(BaseModel):
    clips: list[ClipPick]


SYSTEM_PROMPT = f"""You help a YouTube presenter prepare a 5-15 minute finance explainer video.

About the presenter and the channel:
- High-energy, on camera, talks freestyle from bullet points. Cuts to charts, headline screenshots and B-roll.
- Covers world financial and AI news with chart-driven macro stories, for people who do not understand finance. \
The angle is always "what this means for your wallet".
- The presenter is studying for a securities licence. Everything must be education and commentary, never personal \
investment advice.

How numbers work here (the most important rule):
- You never type a digit yourself. The user message contains a fact sheet; each fact has an id like F7. \
To use a number, write its placeholder, for example {{F7}}, and software will insert the exact fetched value. \
The "value" field shows what will be inserted, so write the sentence around it \
(for a value of "7.11%" write "mortgage rates are now {{F7}}").
- Any other digit you write is deleted automatically, including years, counts and dollar amounts, so spell small \
counts as words ("three reasons") and leave out any figure that is not on the fact sheet. \
The names 401(k), S&P 500, 10-year, 2-year and 30-year are fine.
- Facts with status "verify" come only from news articles. You may tell the presenter to show that headline, \
but do not build a claim on its numbers.

Compliance (the presenter's future licence depends on it):
- No buy, sell or hold recommendations, no price targets, no predictions stated as certain, no promises of returns.
- Explain what happened and how it works; say "what to watch", never "what to do with your money".

Format:
- Bullets are short talking points for someone who speaks freestyle, not sentences to read aloud. One idea each.
- Write for a smart 12-year-old: everyday words, concrete comparisons, no jargon without a five-word explanation.
- Mark visuals inline: [CHART 2] where a chart goes (use the chart numbers given), [HEADLINE 1] for a headline \
screenshot, [B-ROLL 1] for B-roll (numbered in the order of your broll list).
- hook: the surprising fact or question for the first fifteen seconds, two or three bullets.
- what_happened: three to five bullets in plain English.
- causes: two or three causes, each tied to one chart number, each with two or three bullets.
- mortgage, job, groceries, retirement: two or three bullets each on what this means for that part of a viewer's life. \
Use the wallet facts given for each.
- watch_takeaway: one bullet on what to watch next. The dates are added by software; do not write dates.
- closing_line: one closing thought. cta: a subscribe call to action in the presenter's voice.
- titles: exactly eight YouTube title options, each sixty characters or fewer after placeholders are filled in. \
Curiosity without clickbait promises. thumbnails: exactly three thumbnail text ideas of four words or fewer.
- broll: three or four B-roll ideas. Each prompt will be pasted into Higgsfield AI, so describe one generic, \
symbolic shot: subject, camera move, light, mood. Never a real person (no Fed chair, president, CEO or any named \
or recognisable individual), never a real company's logo or product, never a re-creation of a real event or \
news footage. Every AI visual is labelled "{ILLUSTRATIVE_LABEL}" on screen.
- description_summary: two sentences for the top of the YouTube description. No digits."""


def _client(settings: dict):
    key = settings.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise LLMUnavailable("No Anthropic API key in Settings; used the built-in templates for wording.")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - listed in requirements.txt
        raise LLMUnavailable("The 'anthropic' package is not installed.") from exc
    return anthropic, anthropic.Anthropic(api_key=key, timeout=180.0, max_retries=2)


def _parse(settings: dict, system: str, user: str, schema, max_tokens: int = 16000):
    """One structured-output request. Returns (parsed object, model that answered)."""
    anthropic, client = _client(settings)
    model = settings.get("ANTHROPIC_MODEL") or "claude-opus-5-5"
    try:
        # fallbacks="default": if the model's safety filter declines by mistake, the API
        # retries on the fallback model Anthropic recommends instead of returning nothing.
        response = client.beta.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as exc:
        raise LLMUnavailable("The Anthropic API key was rejected. Check it in Settings.") from exc
    except anthropic.RateLimitError as exc:
        raise LLMUnavailable("The Anthropic API rate limit was hit. Try again in a minute.") from exc
    except anthropic.APIStatusError as exc:
        raise LLMUnavailable(f"The Anthropic API returned an error ({exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMUnavailable("Could not reach the Anthropic API. Check your internet connection.") from exc
    if response.stop_reason == "refusal":
        raise LLMUnavailable("The model declined this request.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise LLMUnavailable("The model's answer was cut off or not in the expected format.")
    return response.parsed_output, response.model


def build_user_message(brief: dict) -> str:
    """Everything the model may use. Numbers appear only as the 'value' of a fact id."""
    payload = {
        "topic": brief["topic"],
        "facts": [{"id": f["id"], "group": f.get("group", ""), "claim": f["claim"], "value": f["value"],
                   "status": f["status"]} for f in brief["facts"]],
        "charts": [{"number": c["n"], "title": c["title"], "what_it_teaches": c["teaches"],
                    "fact_ids": c.get("fact_ids", [])} for c in brief["charts"]],
        "wallet_fact_ids": brief["wallet"],
        "headlines": [{"number": h["n"], "title": h["title"], "source": h["source"]} for h in brief.get("headlines", [])],
        "upcoming_releases": [w["name"] for w in brief.get("watch", [])],
        "competitor_titles_for_style_only": brief.get("competitor_titles", [])[:8],
    }
    return ("Prepare the wording for this video. Use only the facts below.\n\n"
            + json.dumps(payload, indent=1, ensure_ascii=False))


def _guard(text: str, facts_by_id: dict, removed: list[str]) -> dict:
    clean, used, gone = apply_facts(text, facts_by_id)
    removed += gone
    return {"text": clean, "facts": used}


def guard_wording(raw: Wording, brief: dict, model: str) -> dict:
    """Turn the model's draft into the same structure the templates produce, with every
    placeholder filled from the fact sheet and every other number removed."""
    facts_by_id = {f["id"]: f for f in brief["facts"]}
    removed: list[str] = []
    chart_numbers = {c["n"] for c in brief["charts"]}

    def bullets(items: list[str]) -> list[dict]:
        return [_guard(item, facts_by_id, removed) for item in items if item.strip()]

    causes = []
    for cause in raw.causes[:3]:
        number = cause.chart if cause.chart in chart_numbers else (brief["charts"][0]["n"] if brief["charts"] else 0)
        causes.append({"cause": _guard(cause.cause, facts_by_id, removed)["text"], "chart": number,
                       "bullets": bullets(cause.bullets)})

    # Titles and thumbnails: a stray number means the line is dropped, not patched.
    titles = [apply_facts(t, facts_by_id)[0] for t in raw.titles if not has_stray_number(t)]
    thumbnails = [apply_facts(t, facts_by_id)[0] for t in raw.thumbnails if not has_stray_number(t)]
    closing = _guard(raw.closing_line, facts_by_id, removed)
    return {
        "source": f"llm:{model}",
        "hook": bullets(raw.hook),
        "what_happened": bullets(raw.what_happened),
        "causes": causes,
        "wallet": {"mortgage": bullets(raw.mortgage), "job": bullets(raw.job),
                   "groceries": bullets(raw.groceries), "retirement": bullets(raw.retirement)},
        "watch_takeaway": _guard(raw.watch_takeaway, facts_by_id, removed),
        "closing_line": closing["text"],
        "closing_facts": closing["facts"],
        "cta": _guard(raw.cta, facts_by_id, removed)["text"],
        "titles": titles,
        "thumbnails": thumbnails,
        "broll": [{"section": b.section, "idea": _guard(b.idea, facts_by_id, removed)["text"],
                   "prompt": _guard(b.prompt, facts_by_id, removed)["text"]} for b in raw.broll[:4]],
        "description_summary": _guard(raw.description_summary, facts_by_id, removed)["text"],
        "removed_numbers": removed,
    }


def llm_wording(brief: dict, settings: dict) -> dict:
    raw, model = _parse(settings, SYSTEM_PROMPT, build_user_message(brief), Wording)
    return guard_wording(raw, brief, model)


CLIP_SYSTEM_PROMPT = """You pick short clips from the transcript of a finance explainer video for TikTok.

You are given the transcript as numbered segments with their start and end times in seconds.
Pick three to five clips. Each clip must:
- run between thirty and sixty seconds (check the times),
- make sense on its own to someone who has not seen the rest of the video: it starts at the beginning of a \
thought and ends at the end of one,
- open with something that stops a scroll: a surprising fact, a question, or a "here's what this means for you".
Do not overlap clips. Prefer the parts that explain what something means for an ordinary person's money.

For each clip give start_segment and end_segment (the segment numbers, inclusive), a caption_hook of twelve words \
or fewer to put on screen, and a short reason. The caption must be education and commentary: no buy or sell \
advice, no price targets, no promises. Only use a number in a caption if the presenter says it in that clip."""


def llm_clip_plan(segments: list[dict], settings: dict) -> list[dict]:
    listing = "\n".join(f"[{i}] {s['start']:.1f}-{s['end']:.1f}s: {s['text']}" for i, s in enumerate(segments))
    raw, _model = _parse(settings, CLIP_SYSTEM_PROMPT, "Transcript segments:\n\n" + listing, ClipPlan, max_tokens=8000)
    return [pick.model_dump() for pick in raw.clips]
