"""Tests for the rules-text screen."""

import pytest

from mentionbot.rules_check import screen_all, screen_market, threshold_in_rules
from mentionbot.terms import TermMarket

PLAIN_RULES = (
    "If the speaker says the term 'tariff' during the event, then the market "
    "resolves to Yes. Plural and possessive forms count."
)


def market(**kw) -> TermMarket:
    base = dict(
        ticker="KXT-A",
        title="Tariff",
        variants=["tariff"],
        threshold=1,
        rules_primary=PLAIN_RULES,
    )
    base.update(kw)
    return TermMarket(**base)


def test_plain_rules_pass():
    assert screen_market(market()) is None


@pytest.mark.parametrize(
    "rules",
    [
        "The term counts even as part of a larger word.",
        "Compound words containing the term count.",
        "Hyphenated variations count toward the total.",
        "The term must be said exactly as written.",
        "Plurals do not count toward resolution.",
        "Possessives will not count.",
        "Any form of the word, including derivatives, counts.",
        "Mentions are only counted once per sentence.",
        "The term must be said three times consecutive.",
        "Matching is case-sensitive.",
        "Text shown on screen in the chyron also counts.",
        "Mentions by other speakers count as well.",
    ],
)
def test_divergent_matching_is_flagged(rules):
    assert screen_market(market(rules_primary=rules)) is not None


def test_missing_rules_text_is_flagged():
    assert "no rules text" in screen_market(market(rules_primary="", rules_secondary=""))


def test_unparseable_term_is_flagged():
    assert "no term variants" in screen_market(market(variants=[]))


def test_threshold_mismatch_is_flagged():
    m = market(threshold=1, rules_primary="Resolves Yes if said at least 3 times.")
    reason = screen_market(m)
    assert "threshold mismatch" in reason and "3" in reason


def test_matching_threshold_passes():
    m = market(threshold=3, rules_primary="Resolves Yes if the term is said at least 3 times.")
    assert screen_market(m) is None


def test_threshold_in_rules_extraction():
    assert threshold_in_rules("said at least 5 times") == 5
    assert threshold_in_rules("said 2 or more times") == 2
    assert threshold_in_rules("no count here") is None


def test_screen_all_partitions_and_sets_reason():
    good = market(ticker="GOOD")
    bad = market(ticker="BAD", rules_primary="Compound words count.")
    tradable, flagged = screen_all([good, bad])
    assert [m.ticker for m in tradable] == ["GOOD"]
    assert [m.ticker for m in flagged] == ["BAD"]
    assert good.flagged_reason is None and good.tradable
    assert bad.flagged_reason is not None and not bad.tradable
