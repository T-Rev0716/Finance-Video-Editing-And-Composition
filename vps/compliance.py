"""Compliance checks: education and commentary only, never personal investment advice.

Automatic checks scan every piece of generated text. Manual items are things only the
presenter can confirm, because the on-camera delivery is freestyle.
"""
from __future__ import annotations

import re

from .voice import ILLUSTRATIVE_LABEL

_FLAGS = re.IGNORECASE

BUY_SELL = [
    r"\b(?:you|everyone|viewers|investors)\s+(?:should|need to|must|have to|ought to)\s+(?:buy|sell|short|dump|own|hold|load up|get out|get in|invest)\b",
    r"\bI(?:'d| would)?\s+(?:recommend|suggest|advise)\b",
    r"\b(?:buy|sell|short)\s+(?:now|today|immediately|this stock|these stocks|the dip|before|right now|asap)\b",
    r"\bstrong (?:buy|sell)\b",
    r"\b(?:must[- ]own|must[- ]buy|top picks?|stock picks?|my picks?|best stocks? to buy|stocks? to buy)\b",
    r"\b(?:get|move|put) (?:your|all your) money (?:in|into|out of)\b",
    r"\btime to (?:buy|sell|get in|get out)\b",
    r"\b(?:load up on|back up the truck|all[- ]in on)\b",
    r"\bwhere I'?m putting my money\b",
    r"\bwhat I'?m (?:buying|selling)\b",
]
PRICE_TARGETS = [
    r"\bprice targets?\b",
    r"\b(?:will|is going to|are going to|gonna|is set to|about to)\s+(?:hit|reach|go to|climb to|fall to|drop to|crash to|soar to|surge to|plunge to|double|triple)\b",
    r"\btarget of\s+\$?\d",
    r"\b(?:headed|heading|going) to\s+\$\d",
    r"\bby (?:year[- ]end|next year|20\d\d)[^.]{0,40}\b(?:will|should) (?:be|hit|reach)\b",
]
PROMISES = [
    r"\bguarantee[sd]?\b", r"\brisk[- ]free\b", r"\bcan(?:'t|not) lose\b", r"\bsure thing\b",
    r"\bget rich\b", r"\beasy money\b", r"\bfree money\b", r"\bsafe (?:bet|investment|returns?)\b",
    r"\b(?:double|triple|10x) your money\b", r"\byou(?:'ll| will) (?:make|earn|profit)\b",
    r"\bno[- ]brainer\b", r"\bcan(?:'t|not) miss\b", r"\bpassive income\b",
]
# "past performance does not guarantee future results" is the standard caution, not a promise.
_SAFE_PHRASES = re.compile(r"(?:does not|doesn't|do not|don't|no|not a|never|cannot|can't)\s+guarantee[sd]?|not guaranteed", _FLAGS)

# Well-known people and roles that must never be rendered as realistic AI footage.
REAL_PEOPLE = [
    "powell", "warsh", "yellen", "bessent", "trump", "biden", "kamala harris", "jd vance", "obama", "musk",
    "bezos", "zuckerberg", "altman", "jensen huang", "nadella", "pichai", "tim cook", "lisa cook", "buffett",
    "dimon", "lagarde", "bernanke", "greenspan", "bill gates", "xi jinping", "putin", "zelensky", "ray dalio",
    "ackman", "saylor", "fed chair", "fed chairman", "fed governor", "treasury secretary", "the president",
    "prime minister", "ceo of", "senator", "congressman", "congresswoman",
]
FAKE_FOOTAGE = [
    r"\bnews footage\b", r"\bbreaking news\b", r"\bpress conference\b", r"\bnews anchor\b", r"\bnewscast\b",
    r"\bdocumentary footage\b", r"\bleaked\b", r"\bsecurity camera\b", r"\bbodycam\b", r"\bcongressional hearing\b",
    r"\bphotorealistic (?:portrait|photo) of\b", r"\blookalike\b", r"\bdeepfake\b",
]


def _find(patterns: list[str], text: str) -> list[str]:
    text = text.replace("\u2019", "'")
    hits = []
    seen_spans: list[tuple[int, int]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, _FLAGS):
            if any(a < match.end() and match.start() < b for a, b in seen_spans):
                continue  # the same words already matched another pattern
            seen_spans.append((match.start(), match.end()))
            start = max(0, match.start() - 30)
            hits.append(text[start:match.end() + 30].strip())
    return hits


def scan_text(text: str) -> dict[str, list[str]]:
    """Problems found in one piece of text, by category. Empty lists mean clean."""
    promises = [h for h in _find(PROMISES, text) if not _SAFE_PHRASES.search(h)]
    return {"buy_sell": _find(BUY_SELL, text), "price_target": _find(PRICE_TARGETS, text), "promise": promises}


def is_clean(text: str) -> bool:
    return not any(scan_text(text).values())


def check_broll_prompt(prompt: str) -> list[str]:
    """Reasons a B-roll prompt is not allowed (real person, fake footage of a real event)."""
    problems = []
    lower = prompt.lower()
    for name in REAL_PEOPLE:
        if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", lower):
            problems.append(f"names a real person or office ('{name}')")
    for pattern in FAKE_FOOTAGE:
        if re.search(pattern, prompt, _FLAGS):
            problems.append("asks for realistic news-style footage")
    return list(dict.fromkeys(problems))


MANUAL_ITEMS = [
    ("said_no_advice", "On camera, I did not tell anyone to buy, sell or hold anything."),
    ("said_no_targets", "On camera, I gave no price targets and made no promises about returns."),
    ("said_disclaimer", "I said the \"education only, not investment advice\" disclaimer out loud."),
    ("verified_news", "Every number I quoted from a news article was checked against a primary source."),
    ("labelled_ai", "Every AI-generated clip has an on-screen \"Illustrative\" label in the edit."),
    ("youtube_toggle", "If any AI visual could be mistaken for real, I turned on YouTube's \"altered or synthetic content\" setting."),
    ("description_pasted", "The description with sources and the disclaimer is pasted into YouTube."),
]


def run_checks(package: dict, disclaimer: str) -> dict:
    """Build the checklist for a package. Each item: {id, label, status, detail}."""
    texts: list[tuple[str, str]] = []
    outline = package["outline"]
    for section in ("hook", "what_happened"):
        texts += [(section, b["text"]) for b in outline[section]["bullets"]]
    for cause in outline["why"]:
        texts.append(("why", cause["cause"]))
        texts += [("why", b["text"]) for b in cause["bullets"]]
    for angle, bullets in outline["what_it_means"].items():
        texts += [(angle, b["text"]) for b in bullets]
    texts += [("closing", outline["closing"]["line"]), ("closing", outline["closing"]["cta"])]
    texts += [("title", t) for t in package["titles"]] + [("thumbnail", t) for t in package["thumbnails"]]
    texts.append(("description", package["description"]))
    texts += [("clip caption", c["caption"]) for c in package.get("clips", {}).get("clips", [])]

    found: dict[str, list[str]] = {"buy_sell": [], "price_target": [], "promise": []}
    for where, text in texts:
        for kind, hits in scan_text(text).items():
            found[kind] += [f"{where}: “{hit}”" for hit in hits]

    def text_item(item_id: str, label: str, hits: list[str]) -> dict:
        return {"id": item_id, "label": label, "status": "fail" if hits else "pass",
                "detail": "; ".join(hits[:5]) if hits else f"Scanned {len(texts)} pieces of generated text; nothing found."}

    items = [
        text_item("no_buy_sell", "No buy/sell recommendations", found["buy_sell"]),
        text_item("no_price_targets", "No price targets", found["price_target"]),
        text_item("no_promises", "No promises of returns", found["promise"]),
    ]

    description = package["description"]
    lower = description.lower()
    has_disclaimer = "not investment" in lower and "education" in lower
    items.append({"id": "disclaimer", "label": "Includes the \"education only, not investment advice\" disclaimer",
                  "status": "pass" if has_disclaimer else "fail",
                  "detail": "Present in the YouTube description." if has_disclaimer else "The disclaimer is missing from the description."})

    ai_shots = [s for s in package["shots"] if s["type"] == "B-ROLL (AI)"]
    unlabelled = [s for s in ai_shots if ILLUSTRATIVE_LABEL not in s.get("label", "")]
    blocked = [s for s in ai_shots if s.get("blocked")]
    disclosed = (not ai_shots) or "ai-generated" in lower
    ai_ok = not unlabelled and disclosed and not blocked
    detail = f"{len(ai_shots)} AI visual(s), all labelled \"{ILLUSTRATIVE_LABEL}\" and disclosed in the description."
    if blocked:
        detail = f"{len(blocked)} B-roll prompt(s) were blocked for naming a real person or asking for fake footage. Rewrite them before use."
    elif unlabelled or not disclosed:
        detail = "An AI visual is missing its label or the description lacks the AI disclosure."
    items.append({"id": "ai_disclosed", "label": "AI visuals disclosed and labelled \"illustrative\"",
                  "status": "pass" if ai_ok else "fail", "detail": detail})

    cited = {f["source_url"] for f in package["facts"] if f["id"] in package.get("cited_fact_ids", []) and f.get("source_url")}
    cited |= {s["source_url"] for c in package["charts"] for s in c["series"]}
    missing = [url for url in cited if url not in description]
    items.append({"id": "sources_listed", "label": "Sources listed in the description",
                  "status": "pass" if cited and not missing else "fail",
                  "detail": f"All {len(cited)} source link(s) used are in the description." if cited and not missing
                  else (f"{len(missing)} source link(s) missing from the description." if cited else "No sources were collected.")})

    removed = package.get("removed_numbers", [])
    items.append({"id": "numbers_traced", "label": "Every number traces to the fact sheet",
                  "status": "pass" if not removed else "warn",
                  "detail": "All numbers in the wording were inserted from fetched data." if not removed
                  else f"{len(removed)} number(s) written by the AI were removed because they are not on the fact sheet: {', '.join(removed[:6])}."})

    verify = [f for f in package["facts"] if f["status"] == "verify"]
    items.append({"id": "news_flagged", "label": "News-only claims flagged \"verify\"",
                  "status": "warn" if verify else "pass",
                  "detail": f"{len(verify)} claim(s) come only from news articles. Check each against a primary source before saying it on camera."
                  if verify else "No news-only claims in this package."})

    manual = [{"id": item_id, "label": label, "status": "manual", "detail": ""} for item_id, label in MANUAL_ITEMS]
    checked = package.get("manual_checks", {})
    for item in manual:
        item["checked"] = bool(checked.get(item["id"]))
    failed = [i for i in items if i["status"] == "fail"]
    return {"automatic": items, "manual": manual,
            "summary": "fail" if failed else ("review" if any(i["status"] == "warn" for i in items) else "pass")}
