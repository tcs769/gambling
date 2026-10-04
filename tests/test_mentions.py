"""Mention-matching tests on sample text."""

import pytest

from mentionbot.mentions import TermCounter, Word, build_variant_pattern, normalize_word


def words(sentence: str, confidence: float = 0.99) -> list[Word]:
    out, t = [], 0
    for tok in sentence.split():
        out.append(Word(text=tok, confidence=confidence, start_ms=t, end_ms=t + 300))
        t += 320
    return out


def count(sentence: str, variants, threshold=1, min_conf=0.85, confidence=0.99) -> int:
    c = TermCounter(variants=list(variants), threshold=threshold, min_confidence=min_conf)
    c.add_segment(words(sentence, confidence))
    return c.count


# -- basic whole-word matching -------------------------------------------
def test_simple_match_is_case_insensitive():
    assert count("We will impose a TARIFF today", ["tariff"]) == 1
    assert count("Tariff policy", ["Tariff"]) == 1


def test_counts_each_occurrence():
    assert count("tariff and tariff and tariff", ["tariff"]) == 3


def test_no_match_inside_longer_word():
    # "tariffing" and "subtariff" must not count as "tariff".
    assert count("tariffing the subtariff rates", ["tariff"]) == 0


def test_no_partial_prefix_match():
    assert count("car carpet cartography", ["cart"]) == 0


# -- inflections ----------------------------------------------------------
@pytest.mark.parametrize(
    "sentence",
    [
        "the tariff is high",        # bare
        "the tariffs are high",      # plural s
        "the tariff's effect",       # possessive 's
        "the tariffs' effect",       # plural possessive s'
        "the tariff’s effect",  # curly possessive
    ],
)
def test_plural_and_possessive_forms_count(sentence):
    assert count(sentence, ["tariff"]) == 1


def test_es_plural():
    assert count("the taxes went up", ["tax"]) == 1
    assert count("one tax", ["tax"]) == 1


def test_variant_already_plural_still_matches_bare_and_possessive():
    assert count("the tariffs' effect", ["tariffs"]) == 1
    assert count("the tariffs are high", ["tariffs"]) == 1


# -- punctuation ----------------------------------------------------------
def test_trailing_punctuation_does_not_block_match():
    assert count("What about the tariff?", ["tariff"]) == 1
    assert count("Tariff, inflation, and jobs.", ["tariff"]) == 1


def test_normalize_word_keeps_apostrophes():
    assert normalize_word("tariff's") == "tariff's"
    assert normalize_word('"tariff."') == "tariff"


# -- multi-word variants --------------------------------------------------
def test_multiword_variant():
    assert count("it is a witch hunt out there", ["witch hunt"]) == 1
    assert count("it is a witch   hunt", ["witch hunt"]) == 1
    assert count("the witch hunts continue", ["witch hunt"]) == 1


def test_multiword_requires_adjacency():
    assert count("a witch is on the hunt", ["witch hunt"]) == 0


def test_overlapping_variants_count_once():
    # "border" also appears inside "southern border"; the longer, earlier match wins.
    c = TermCounter(variants=["border", "southern border"], threshold=1)
    c.add_segment(words("we secured the southern border today"))
    assert c.count == 1
    assert c.hits[0].variant == "southern border"


def test_distinct_variants_each_count():
    assert count("tariff and then tariffs again", ["tariff", "tariffs"]) == 2


# -- confidence gating ----------------------------------------------------
def test_low_confidence_word_is_not_counted():
    assert count("the tariff is high", ["tariff"], min_conf=0.85, confidence=0.5) == 0


def test_confidence_at_threshold_counts():
    assert count("the tariff is high", ["tariff"], min_conf=0.85, confidence=0.85) == 1


def test_multiword_blocked_if_any_word_is_low_confidence():
    ws = [
        Word("it", 0.99, 0, 100),
        Word("is", 0.99, 100, 200),
        Word("a", 0.99, 200, 300),
        Word("witch", 0.99, 300, 400),
        Word("hunt", 0.40, 400, 500),  # second half mis-heard
    ]
    c = TermCounter(variants=["witch hunt"], min_confidence=0.85)
    c.add_segment(ws)
    assert c.count == 0


def test_low_confidence_elsewhere_does_not_block():
    ws = [
        Word("umm", 0.10, 0, 100),
        Word("tariff", 0.99, 100, 200),
    ]
    c = TermCounter(variants=["tariff"], min_confidence=0.85)
    c.add_segment(ws)
    assert c.count == 1


# -- thresholds and accumulation -----------------------------------------
def test_threshold_resolution_across_segments():
    c = TermCounter(variants=["tariff"], threshold=3)
    c.add_segment(words("tariff one"))
    assert not c.resolved_yes
    c.add_segment(words("tariff two"))
    assert not c.resolved_yes
    c.add_segment(words("tariff three"))
    assert c.resolved_yes
    assert c.count == 3


def test_default_threshold_resolves_on_first_mention():
    c = TermCounter(variants=["tariff"])
    assert not c.resolved_yes
    c.add_segment(words("a tariff"))
    assert c.resolved_yes


def test_hits_carry_timestamps_and_confidence():
    c = TermCounter(variants=["tariff"])
    c.add_segment([Word("tariff", 0.91, 1500, 1900)])
    hit = c.hits[0]
    assert (hit.start_ms, hit.end_ms) == (1500, 1900)
    assert hit.min_confidence == pytest.approx(0.91)


def test_empty_segment_is_safe():
    c = TermCounter(variants=["tariff"])
    assert c.add_segment([]) == []
    assert c.count == 0


def test_rejects_variant_with_no_words():
    with pytest.raises(ValueError):
        build_variant_pattern("   ")
