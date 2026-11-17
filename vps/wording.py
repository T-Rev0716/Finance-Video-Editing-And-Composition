"""Built-in wording (no LLM): assembles the outline from fact-sheet sentences and the
plain-English library in voice.py. Used when no API key is set or the LLM call fails."""
from __future__ import annotations

from . import catalog
from .voice import CATEGORY_VOICE, GENERIC_VOICE, WALLET_LINES

TITLE_LIMIT = 60
THUMB_WORD_LIMIT = 4


def _bullet(text: str, *fact_ids: str) -> dict:
    return {"text": text, "facts": [f for f in fact_ids if f]}


def _fact_bullet(fact: dict, suffix: str = "") -> dict:
    return _bullet(f"{fact['claim']}{(' ' + suffix) if suffix else ''}", fact["id"])


def lead_facts(brief: dict) -> dict[str, dict]:
    """The headline number for this topic and its companions, keyed latest/year/month/record."""
    by_key = {f["key"]: f for f in brief["facts"]}
    lead = brief.get("lead_series", "")
    out = {}
    if lead:
        for name, key in (("latest", f"{lead}.yoy"), ("latest", f"{lead}.latest"), ("year", f"{lead}.year"),
                          ("year", f"{lead}.yoy_prev"), ("month", f"{lead}.month"), ("record", f"{lead}.record")):
            if key in by_key and name not in out:
                out[name] = by_key[key]
    if "latest" not in out:
        # No category matched (or its lead series failed): lead with the first chart's first fact.
        for chart in brief["charts"]:
            ids = chart.get("fact_ids", [])
            facts = [f for f in brief["facts"] if f["id"] in ids]
            if facts:
                out["latest"] = facts[0]
                for fact in facts[1:]:
                    if fact["key"].endswith(".year"):
                        out["year"] = fact
                    if fact["key"].endswith(".record"):
                        out["record"] = fact
                break
    return out


def _chart_for_fact(brief: dict, fact: dict | None) -> int | None:
    if fact:
        for chart in brief["charts"]:
            if fact["id"] in chart.get("fact_ids", []):
                return chart["n"]
    return brief["charts"][0]["n"] if brief["charts"] else None


def _trend_words(lead: dict[str, dict]) -> tuple[str, str]:
    trend = (lead.get("year") or {}).get("trend", "")
    if trend in ("up", "highest"):
        return "Rising", "Climbing"
    if trend in ("down", "lowest"):
        return "Falling", "Dropping"
    return "", ""


def template_titles(brief: dict, lead: dict[str, dict]) -> list[str]:
    """Title ideas of 60 characters or fewer. Numbers are inserted from the lead fact only."""
    voice = CATEGORY_VOICE.get(brief.get("primary", ""), GENERIC_VOICE)
    label = brief.get("label") or (brief["topic"] if len(brief["topic"]) <= 28 else "This Story")
    metric = voice.get("metric")
    is_are = "Are" if voice.get("metric_plural") else "Is"
    label_is = "Are" if brief.get("plural") else "Is"
    value = (lead.get("latest") or {}).get("value", "")
    value = value if value and len(value) <= 16 and " " not in value.strip().replace(" trillion", "").replace(" billion", "") else ""
    rising, _ = _trend_words(lead)
    n_charts = {1: "One Chart", 2: "Two Charts", 3: "Three Charts", 4: "Four Charts", 5: "Five Charts", 6: "Six Charts"}.get(len(brief["charts"]), "Charts")

    # "The 10-Year Yield" reads as "the 10-Year Yield" in the middle of a title.
    mid = (metric[0].lower() + metric[1:]) if metric and metric.startswith("The ") else metric
    ideas = []
    if metric and value:
        ideas += [f"{metric} {is_are} Now {value}. Here's Why",
                  f"{metric} at {value}: What It Means for Your Wallet"]
    if metric and rising:
        ideas += [f"Why {mid} {is_are} {rising} (Explained Simply)",
                  f"{metric} {is_are} {rising}. Here's What Changes for You"]
    ideas += [
        f"{label} Explained Like You're 12",
        f"{label}: What Changes for Your Mortgage and 401(k)",
        f"The {n_charts} That Explain {label} Right Now",
        f"What Nobody Tells You About {label}",
        f"{label}: What Just Happened and Why It Matters",
        f"What Happens Next With {label}? Dates to Watch",
        f"{label} {label_is} Changing. Here's the Plain-English Version",
        f"Your Wallet vs {label}: The Simple Breakdown",
    ]
    out = []
    for idea in ideas:
        if len(idea) <= TITLE_LIMIT and idea not in out:
            out.append(idea)
    return out


def template_thumbnails(brief: dict, lead: dict[str, dict]) -> list[str]:
    voice = CATEGORY_VOICE.get(brief.get("primary", ""), GENERIC_VOICE)
    thumb = voice["thumb"]
    value = (lead.get("latest") or {}).get("value", "")
    rising, _ = _trend_words(lead)
    ideas = []
    if value and len(value.split()) == 1:
        ideas.append(f"{thumb} AT {value}")
    ideas.append(f"WHY IT'S {rising.upper()}" if rising else "WHAT JUST CHANGED?")
    ideas += ["WHAT IT COSTS YOU", f"{thumb} EXPLAINED", "YOUR WALLET NEXT?"]
    return [i for i in ideas if len(i.split()) <= THUMB_WORD_LIMIT][:3]


def template_wording(brief: dict) -> dict:
    voice = CATEGORY_VOICE.get(brief.get("primary", ""), GENERIC_VOICE)
    by_id = {f["id"]: f for f in brief["facts"]}
    lead = lead_facts(brief)
    lead_chart = _chart_for_fact(brief, lead.get("latest"))
    chart_tag = f"[CHART {lead_chart}]" if lead_chart else ""

    hook = []
    if lead.get("latest"):
        hook.append(_fact_bullet(lead["latest"], chart_tag))
    if lead.get("record"):
        hook.append(_fact_bullet(lead["record"]))
    elif lead.get("year"):
        hook.append(_fact_bullet(lead["year"]))
    hook.append(_bullet(f"Ask the camera: {voice['question']}"))

    happened = [_bullet(f"Plain English: {voice['plain']}")]
    for name in ("year", "month"):
        if lead.get(name) and not (name == "year" and not lead.get("record")):
            happened.append(_fact_bullet(lead[name]))
    for headline in brief.get("headlines", [])[:2]:
        happened.append(_bullet(
            f"[HEADLINE {headline['n']}] Show the headline: “{headline['title']}” ({headline['source']}). "
            "It is a news report, so check any number in it before you say it.", headline.get("fact_id", "")))

    used: set[str] = {f for b in hook + happened for f in b["facts"]}

    causes = []
    others = [c for c in brief["charts"] if c["n"] != lead_chart] or brief["charts"]
    for chart in others[:3]:
        fresh = [by_id[i] for i in chart.get("fact_ids", []) if i in by_id and i not in used and by_id[i].get("value")][:2]
        used.update(f["id"] for f in fresh)
        bullets = [_fact_bullet(f) for f in fresh]
        bullets.append(_bullet(f"Walk through the chart: point at where the line turns and say what was going on. [CHART {chart['n']}]"))
        causes.append({"cause": chart.get("teaches") or chart["title"], "chart": chart["n"], "bullets": bullets})

    wallet = {}
    for angle, ids in brief["wallet"].items():
        facts = [by_id[i] for i in ids if i in by_id and by_id[i].get("value")]
        if not facts:
            wallet[angle] = [_bullet("No number was fetched for this angle (see the data notes on the fact sheet). "
                                     "Keep it general, or skip it.")]
            continue
        example = [f for f in facts if f["key"] == "WALLET.mortgage_payment"]
        # Lead with the level, then whatever has not been said yet, then the worked example.
        rest = [f for f in facts[1:] if f["id"] not in used and f not in example][:1]
        bullets = [_fact_bullet(f) for f in [facts[0]] + rest + example]
        bullets.append(_bullet(WALLET_LINES[angle]))
        wallet[angle] = bullets

    recap = lead.get("latest")
    channel = f" on {brief['channel']}" if brief.get("channel") else ""
    return {
        "source": "templates",
        "hook": hook,
        "what_happened": happened,
        "causes": causes,
        "wallet": wallet,
        "watch_takeaway": _bullet("Read the dates out loud and tell viewers which one number you will be watching."),
        "closing_line": ("One-line recap: " + recap["claim"] + " Remind viewers this is education, not advice.") if recap
        else "One-line recap of the story, then remind viewers this is education, not advice.",
        "closing_facts": [recap["id"]] if recap else [],
        "cta": f"Subscribe{channel} for plain-English money news, and ask: what should I explain next?",
        "titles": template_titles(brief, lead),
        "thumbnails": template_thumbnails(brief, lead),
        "broll": [{"section": section, "idea": idea, "prompt": prompt}
                  for section, (prompt, idea) in zip(("hook", "why", "what_it_means"), voice["broll"])],
        "description_summary": (
            f"{brief['topic'].rstrip('.')}. What happened, why it happened, and what it means for your mortgage, "
            "your job, your grocery bill and your 401(k), explained in plain English with charts built from official data."),
        "removed_numbers": [],
    }


def release_names(brief: dict) -> list[str]:
    return [catalog.RELEASES[item["key"]]["name"] for item in brief.get("watch", []) if item.get("key") in catalog.RELEASES]
