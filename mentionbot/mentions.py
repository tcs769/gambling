"""Deterministic mention counting. No ML, no fuzzy matching.

A variant matches on a case-insensitive whole-word basis, and also matches its
plural and possessive inflections: ``s``, ``es``, ``'s`` and ``s'`` (curly
apostrophes included). Matching is anchored with lookarounds rather than ``\\b``
so that a trailing apostrophe ("the tariffs' effect") still counts.

Only words whose STT confidence is at or above ``min_word_confidence`` can take
part in a match: if any word overlapping a candidate match is below the bar, the
match is discarded. That keeps a mis-heard word from opening a position.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Punctuation stripped from word edges before matching. Apostrophes are kept:
# they carry the possessive forms we deliberately match.
_EDGE_PUNCT = ".,!?;:()[]{}<>\"“”—–-…"
# Plural / possessive tails, longest first so the alternation is greedy-correct.
_SUFFIX = r"(?:'s|’s|s'|s’|es|s)?"


@dataclass(frozen=True)
class Word:
    """One finalized word from the transcriber."""

    text: str
    confidence: float = 1.0
    start_ms: int = 0
    end_ms: int = 0


@dataclass
class MentionHit:
    """A confirmed, confidence-gated occurrence of a variant."""

    variant: str
    matched_text: str
    start_ms: int
    end_ms: int
    min_confidence: float


def normalize_word(text: str) -> str:
    """Strip edge punctuation, keeping internal and trailing apostrophes."""
    return text.strip().strip(_EDGE_PUNCT).strip()


def build_variant_pattern(variant: str) -> re.Pattern[str]:
    """Compile the whole-word + inflection matcher for one variant."""
    tokens = [normalize_word(t) for t in variant.split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        raise ValueError(f"variant has no matchable words: {variant!r}")
    core = r"\s+".join(re.escape(t) for t in tokens)
    # Lookarounds (not \b) so "tariffs'" and "tariff." both terminate cleanly.
    return re.compile(rf"(?<!\w){core}{_SUFFIX}(?!\w)", re.IGNORECASE)


@dataclass
class TermCounter:
    """Accumulates confidence-gated mention counts for one market's variants."""

    variants: list[str]
    threshold: int = 1
    min_confidence: float = 0.85
    count: int = 0
    hits: list[MentionHit] = field(default_factory=list)
    _patterns: list[tuple[str, re.Pattern[str]]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._patterns = [(v, build_variant_pattern(v)) for v in self.variants if v.strip()]

    @property
    def resolved_yes(self) -> bool:
        """True once the market is certain to settle Yes on our own count."""
        return self.count >= self.threshold

    def add_segment(self, words: list[Word]) -> list[MentionHit]:
        """Count mentions in one finalized segment. Returns the new hits."""
        new_hits = find_mentions(words, self._patterns, self.min_confidence)
        self.hits.extend(new_hits)
        self.count += len(new_hits)
        return new_hits


def find_mentions(
    words: list[Word],
    patterns: list[tuple[str, re.Pattern[str]]],
    min_confidence: float,
) -> list[MentionHit]:
    """Find all confidence-gated variant matches across a word sequence.

    Overlapping matches from different variants are resolved by taking the
    earliest, then the longest - so "Southern border" counts once, not twice.
    """
    if not words or not patterns:
        return []

    # Build a single searchable string and a char-offset -> word-index map.
    pieces: list[str] = []
    spans: list[tuple[int, int]] = []  # (start_char, end_char) per word
    cursor = 0
    for w in words:
        token = normalize_word(w.text)
        if not token:
            spans.append((cursor, cursor))
            continue
        if pieces:
            cursor += 1  # the joining space
        pieces.append(token)
        spans.append((cursor, cursor + len(token)))
        cursor += len(token)
    text = " ".join(pieces)
    if not text:
        return []

    candidates: list[tuple[int, int, str, str]] = []
    for variant, pattern in patterns:
        for m in pattern.finditer(text):
            candidates.append((m.start(), m.end(), variant, m.group(0)))

    # Earliest start wins; longer match wins a tie.
    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))

    hits: list[MentionHit] = []
    consumed_to = -1
    for start, end, variant, matched in candidates:
        if start < consumed_to:
            continue
        covered = [
            i
            for i, (ws, we) in enumerate(spans)
            if we > ws and ws < end and we > start
        ]
        if not covered:
            continue
        confidences = [words[i].confidence for i in covered]
        if min(confidences) < min_confidence:
            # A low-confidence word is in the match: do not count it, and do not
            # let it block a different variant that might match the same span.
            continue
        hits.append(
            MentionHit(
                variant=variant,
                matched_text=matched,
                start_ms=words[covered[0]].start_ms,
                end_ms=words[covered[-1]].end_ms,
                min_confidence=min(confidences),
            )
        )
        consumed_to = end
    return hits
