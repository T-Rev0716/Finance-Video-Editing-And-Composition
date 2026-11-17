"""The number guard: wording may only contain numbers that came from the fact sheet.

Writers (the LLM, or the built-in templates) refer to a fact as {F7}. This module swaps
each placeholder for that fact's fetched value and removes any other number, so a figure
that was never fetched cannot reach the outline, a title or the description.
"""
from __future__ import annotations

import re

PLACEHOLDER = re.compile(r"\{(F\d+)\}")
MARKER = re.compile(r"\[(?:CHART|HEADLINE|B-ROLL) \d+\]")
# Names that happen to contain digits. These are not data.
ALLOWED_TERMS = re.compile(
    r"401\s?\(k\)|401k|S&P\s?500|Nasdaq[- ]100|Russell 2000|\b(?:1|2|3|5|7|10|20|30)[- ]year\b|\b(?:1|3|6)[- ]month\b"
    r"|\b24/7\b|\bCOVID-19\b|\bQ[1-4]\b|\bH[12]\b|like (?:I'm|I am|you're) 12|\b12[- ]year[- ]old\b|\bG7\b|\bG20\b|\b10-[KQ]\b|\b8-K\b|\bWeb3\b",
    re.IGNORECASE,
)
STRAY_NUMBER = re.compile(
    r"[$€£]?\d(?:[\d,]*\d)?(?:\.\d+)?\s?(?:%|percent\b|bps\b|basis points\b|trillion\b|billion\b|million\b|[kKmMbB]\b)?"
)
REMOVED = "[number removed - not on the fact sheet]"

# Protected spans are swapped for single private-use characters (no digits) while we scan.
_BASE = 0xE000
_TOKEN = re.compile("[\ue000-\uf8ff]")


def _token(index: int) -> str:
    return chr(_BASE + index)


def apply_facts(text: str, facts_by_id: dict[str, dict]) -> tuple[str, list[str], list[str]]:
    """Returns (clean text, fact ids used, numbers removed)."""
    used: list[str] = []
    removed: list[str] = []
    protected: list[str] = []

    def protect(match: re.Match) -> str:
        protected.append(match.group(0))
        return _token(len(protected) - 1)

    def placeholder(match: re.Match) -> str:
        fact = facts_by_id.get(match.group(1))
        if not fact or not fact.get("value"):
            removed.append(match.group(0))
            protected.append(REMOVED)
        else:
            if fact["id"] not in used:
                used.append(fact["id"])
            protected.append(fact["value"])
        return _token(len(protected) - 1)

    work = PLACEHOLDER.sub(placeholder, text)
    work = MARKER.sub(protect, work)
    work = ALLOWED_TERMS.sub(protect, work)

    def stray(match: re.Match) -> str:
        removed.append(match.group(0).strip())
        protected.append(REMOVED)
        return _token(len(protected) - 1)

    work = STRAY_NUMBER.sub(stray, work)
    clean = _TOKEN.sub(lambda m: protected[ord(m.group(0)) - _BASE], work)
    return clean, used, removed


def has_stray_number(text: str) -> bool:
    """True if the text contains a number that is neither a placeholder nor an allowed name."""
    work = PLACEHOLDER.sub("", text)
    work = MARKER.sub("", work)
    work = ALLOWED_TERMS.sub("", work)
    return bool(STRAY_NUMBER.search(work))
