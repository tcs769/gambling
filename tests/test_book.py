"""Order book maintenance and ask derivation."""

from mentionbot.kalshi.book import OrderBook


def book(yes=None, no=None, now=1000.0) -> OrderBook:
    b = OrderBook("T")
    b.apply_snapshot(yes or [], no or [], now=now)
    return b


# -- ask derivation --------------------------------------------------------
def test_asks_are_derived_from_the_opposite_side_bids():
    b = book(yes=[[40, 5]], no=[[55, 9]])
    assert b.best_yes_bid == 40
    assert b.best_no_bid == 55
    assert b.yes_ask == 45  # 100 - best no bid
    assert b.no_ask == 60   # 100 - best yes bid


def test_yes_and_no_quotes_are_complementary():
    b = book(yes=[[33, 1]], no=[[61, 1]])
    assert b.best_yes_bid + b.no_ask == 100
    assert b.yes_ask + b.best_no_bid == 100


def test_best_bid_is_the_highest_price_on_that_side():
    b = book(yes=[[10, 1], [44, 2], [30, 3]], no=[[20, 1], [51, 4]])
    assert (b.best_yes_bid, b.best_no_bid) == (44, 51)
    assert (b.yes_ask, b.no_ask) == (49, 56)


def test_empty_book_has_no_quotes():
    b = book()
    assert b.best_yes_bid is None and b.best_no_bid is None
    assert b.yes_ask is None and b.no_ask is None


def test_one_sided_book():
    b = book(yes=[[40, 5]])
    assert b.yes_ask is None   # nothing offered
    assert b.no_ask == 60      # but we can still buy No


# -- sizes ------------------------------------------------------------------
def test_size_at_the_derived_asks():
    b = book(yes=[[40, 7]], no=[[55, 3]])
    assert b.size_at_yes_ask() == 3  # resting No bids are what we lift
    assert b.size_at_no_ask() == 7


def test_size_is_zero_on_an_empty_side():
    assert book().size_at_yes_ask() == 0


# -- deltas -----------------------------------------------------------------
def test_delta_adds_a_level():
    b = book(yes=[[40, 5]], no=[[55, 5]])
    b.apply_delta(42, 3, "yes", now=1001.0)
    assert b.best_yes_bid == 42
    assert b.no_ask == 58


def test_delta_accumulates_then_removes_a_level():
    b = book(yes=[[40, 5]], no=[[55, 5]])
    b.apply_delta(40, 2, "yes", now=1001.0)
    assert b.yes_bids[40] == 7
    b.apply_delta(40, -7, "yes", now=1002.0)
    assert 40 not in b.yes_bids
    assert b.best_yes_bid is None


def test_negative_overshoot_clears_the_level():
    b = book(yes=[[40, 5]])
    b.apply_delta(40, -99, "yes", now=1001.0)
    assert b.yes_bids == {}


def test_snapshot_replaces_prior_state():
    b = book(yes=[[40, 5]], no=[[55, 5]])
    b.apply_snapshot([[10, 1]], [[20, 1]], now=1001.0)
    assert b.yes_bids == {10: 1} and b.no_bids == {20: 1}


def test_snapshot_drops_zero_sized_levels():
    b = book(yes=[[40, 0], [41, 2]])
    assert b.yes_bids == {41: 2}


def test_unknown_side_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        book().apply_delta(40, 1, "maybe")


# -- staleness ---------------------------------------------------------------
def test_never_updated_book_is_stale():
    assert OrderBook("T").is_stale(10.0)


def test_staleness_follows_the_clock():
    b = book(yes=[[40, 1]], now=1000.0)
    assert not b.is_stale(10.0, now=1009.0)
    assert b.is_stale(10.0, now=1011.0)


def test_delta_refreshes_the_clock():
    b = book(yes=[[40, 1]], now=1000.0)
    b.apply_delta(41, 1, "yes", now=1020.0)
    assert not b.is_stale(10.0, now=1025.0)
