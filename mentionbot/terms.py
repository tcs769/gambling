"""Parse Kalshi mention-market titles into terms, variants and thresholds.

Mention markets name the phrase to be said, sometimes with accepted variants
separated by " / ", and sometimes with a count threshold in parentheses:

    "Tariff / Tariffs"            -> variants ["Tariff", "Tariffs"], threshold 1
    "Witch hunt (3+ times)"       -> variants ["Witch hunt"],        threshold 3
    "Border / Southern border (2+ times)"
                                  -> 2 variants,                     threshold 2
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# "(3+ times)", "(3 times)", "(x3)", "3+ times" with or without the parentheses.
_THRESHOLD_RE = re.compile(
    r"\(?\s*(?:x\s*(?P<x>\d+)|(?P<n>\d+)\s*\+?\s*times?)\s*\)?\s*$",
    re.IGNORECASE,
)
_VARIANT_SPLIT = re.compile(r"\s+/\s+|\s+\|\s+")
# Leading "Will X say" / "Say" scaffolding some titles carry.
_LEAD_RE = re.compile(r"^\s*(?:will\s+.+?\s+say|says?|mentions?)\s*[:\-]?\s*", re.IGNORECASE)
_QUOTES = "\"'“”‘’"
_SEPARATORS = "/| 	"


def parse_threshold(text: str) -> tuple[str, int]:
    """Split a trailing count qualifier off a title.

    Returns ``(remaining_text, threshold)``; the default threshold is 1.
    """
    m = _THRESHOLD_RE.search(text)
    if not m:
        return text.strip(), 1
    raw = m.group("x") or m.group("n")
    try:
        threshold = max(1, int(raw))
    except (TypeError, ValueError):
        return text.strip(), 1
    return text[: m.start()].strip(), threshold


def parse_variants(text: str) -> list[str]:
    """Split a term string into its accepted variants, de-duplicated in order."""
    out: list[str] = []
    seen: set[str] = set()
    for part in _VARIANT_SPLIT.split(text):
        # Strip quotes and any separator left over from a repeated or
        # unspaced delimiter ("Tariff /  / Trade").
        cleaned = part.strip().strip(_QUOTES).strip(_SEPARATORS).strip(_QUOTES).strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


@dataclass
class TermMarket:
    """One Kalshi market: a term, its variants, and the count needed for Yes."""

    ticker: str
    title: str
    variants: list[str]
    threshold: int
    rules_primary: str = ""
    rules_secondary: str = ""
    opening_price: int | None = None
    # Set by the rules screen; excluded from trading until the user approves.
    flagged_reason: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.variants[0] if self.variants else self.title

    @property
    def tradable(self) -> bool:
        return self.flagged_reason is None and bool(self.variants)


def _term_source(market: dict) -> str:
    """Pick the field that carries the term text.

    ``yes_sub_title`` is the term on Kalshi mention markets; fall back through
    ``subtitle`` and ``title`` for other shapes.
    """
    for key in ("yes_sub_title", "subtitle", "title"):
        value = (market.get(key) or "").strip()
        if value:
            return value
    return ""


def term_market_from_api(market: dict) -> TermMarket:
    """Build a `TermMarket` from a Kalshi ``/markets`` entry."""
    source = _term_source(market)
    body, threshold = parse_threshold(_LEAD_RE.sub("", source).rstrip("?").strip())
    variants = parse_variants(body)

    # Prefer an explicit opening price; fall back to last price, then the mid.
    opening = market.get("open_interest_price") or market.get("last_price")
    if opening in (None, 0):
        bid, ask = market.get("yes_bid"), market.get("yes_ask")
        if bid is not None and ask is not None and (bid or ask):
            opening = round((bid + ask) / 2)
    return TermMarket(
        ticker=market.get("ticker", ""),
        title=market.get("title", "") or source,
        variants=variants,
        threshold=threshold,
        rules_primary=market.get("rules_primary") or "",
        rules_secondary=market.get("rules_secondary") or "",
        opening_price=int(opening) if opening not in (None, "") else None,
    )
