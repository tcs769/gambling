"""Screen a market's rules text against our matching semantics.

Our counter matches whole words, case-insensitively, plus ``s``/``es``/``'s``/
``s'`` inflections. If a market's rules describe *different* matching - exact
forms only, compound words counting, derivatives counting, once-per-sentence
caps - then our count would diverge from the settlement and we must not trade
it until a human approves.

The screen is deliberately trigger-happy: a false flag costs one skipped
market, a missed flag costs money.
"""

from __future__ import annotations

import re

from .terms import TermMarket

# Each entry: (compiled pattern, human-readable reason).
_SUSPECT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"compound\s+word|as\s+part\s+of\s+(?:a\s+)?(?:larger|another)\s+word|within\s+another\s+word", re.I),
     "rules mention compound/embedded words, which we do not match"),
    (re.compile(r"hyphenat", re.I),
     "rules mention hyphenation, which we do not match"),
    (re.compile(r"substring|partial\s+word", re.I),
     "rules mention substring matching, which we do not match"),
    (re.compile(r"\bexactly\s+as\s+(?:written|stated|shown)|verbatim|exact\s+(?:phrase|word|wording|form)\s+only|must\s+be\s+said\s+exactly", re.I),
     "rules require an exact form; our inflection matching is broader"),
    (re.compile(r"plurals?\s+(?:do\s+not|don't|will\s+not|won't|shall\s+not)\s+count|singular\s+(?:form\s+)?only|not\s+count\s+plurals?", re.I),
     "rules exclude plurals, which we count"),
    (re.compile(r"possessives?\s+(?:do\s+not|don't|will\s+not|won't)\s+count|not\s+count\s+possessives?", re.I),
     "rules exclude possessives, which we count"),
    (re.compile(r"derivative|conjugat|any\s+form\s+of\s+the\s+word|other\s+tenses|verb\s+form|root\s+word|stem\s+of", re.I),
     "rules count other word forms, which we do not match"),
    (re.compile(r"once\s+per\s+(?:sentence|minute|segment|answer|response)|only\s+count(?:ed)?\s+once", re.I),
     "rules cap repeats per unit, which we do not model"),
    (re.compile(r"consecutive|in\s+(?:a\s+)?row|back[-\s]to[-\s]back", re.I),
     "rules require consecutive mentions, which we do not model"),
    (re.compile(r"case[-\s]sensitive", re.I),
     "rules are case-sensitive; we match case-insensitively"),
    (re.compile(r"written\s+(?:form|text)|in\s+writing|on\s+screen|chyron|teleprompter|caption", re.I),
     "rules count written or on-screen text, which we do not observe"),
    (re.compile(r"other\s+speakers?|anyone\s+(?:else|on\s+stage)|any\s+participant|guest\s+or\s+host|moderator",
                re.I),
     "rules count speakers beyond the one we transcribe"),
    (re.compile(r"sign\s+language|translat", re.I),
     "rules involve translation or signing, which we do not observe"),
]

# "at least 3 times", "3 or more times", "three times"
_RULES_THRESHOLD_RE = re.compile(
    r"(?:at\s+least|a\s+minimum\s+of|minimum\s+of|)\s*(\d+)\s*(?:\+|\s+or\s+more)?\s*(?:separate\s+|distinct\s+)?times",
    re.I,
)


def _rules_text(market: TermMarket) -> str:
    return f"{market.rules_primary}\n{market.rules_secondary}".strip()


def threshold_in_rules(text: str) -> int | None:
    """Largest explicit "N times" count stated in the rules, if any."""
    found = [int(m.group(1)) for m in _RULES_THRESHOLD_RE.finditer(text)]
    return max(found) if found else None


def screen_market(market: TermMarket) -> str | None:
    """Return a reason to exclude ``market``, or None if it matches our rules."""
    if not market.variants:
        return "no term variants could be parsed from the title"

    text = _rules_text(market)
    if not text:
        return "market has no rules text to verify matching against"

    for pattern, reason in _SUSPECT_PATTERNS:
        if pattern.search(text):
            return reason

    stated = threshold_in_rules(text)
    if stated is not None and stated != market.threshold:
        return (
            f"threshold mismatch: title parsed {market.threshold}, "
            f"rules state {stated} times"
        )
    return None


def screen_all(markets: list[TermMarket]) -> tuple[list[TermMarket], list[TermMarket]]:
    """Partition markets into (tradable, flagged). Sets ``flagged_reason``."""
    tradable, flagged = [], []
    for m in markets:
        reason = screen_market(m)
        m.flagged_reason = reason
        (flagged if reason else tradable).append(m)
    return tradable, flagged
