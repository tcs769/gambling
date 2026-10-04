"""Position tracking, P&L and reconciliation."""

from mentionbot.kalshi.book import OrderBook
from mentionbot.kalshi.fees import taker_fee_cents
from mentionbot.portfolio import Portfolio, Position


def book(yes_bid=40, no_bid=55) -> OrderBook:
    b = OrderBook("T")
    b.apply_snapshot([[yes_bid, 10]], [[no_bid, 10]], now=1000.0)
    return b


def test_buy_sets_side_count_and_cost_including_fees():
    p = Portfolio()
    p.apply_fill(ticker="T", side="yes", action="buy", count=2, price_cents=40, fill_id="f1")
    pos = p.position("T")
    assert (pos.side, pos.count) == ("yes", 2)
    assert pos.cost_cents == 80 + taker_fee_cents(40, 2)


def test_duplicate_fill_id_is_ignored():
    p = Portfolio()
    assert p.apply_fill(ticker="T", side="yes", action="buy", count=1, price_cents=40, fill_id="f1")
    assert not p.apply_fill(ticker="T", side="yes", action="buy", count=1, price_cents=40, fill_id="f1")
    assert p.position("T").count == 1


def test_sell_realizes_pnl_net_of_both_fees():
    p = Portfolio()
    p.apply_fill(ticker="T", side="yes", action="buy", count=1, price_cents=40, fill_id="f1")
    p.apply_fill(ticker="T", side="yes", action="sell", count=1, price_cents=60, fill_id="f2")
    expected = 60 - (40 + taker_fee_cents(40, 1)) - taker_fee_cents(60, 1)
    assert p.position("T").is_flat
    assert p.realized_cents() == expected


def test_partial_sell_keeps_the_rest_open():
    p = Portfolio()
    p.apply_fill(ticker="T", side="yes", action="buy", count=4, price_cents=50, fill_id="f1")
    p.apply_fill(ticker="T", side="yes", action="sell", count=1, price_cents=60, fill_id="f2")
    pos = p.position("T")
    assert pos.count == 3 and pos.side == "yes"


def test_buying_the_other_side_closes_exposure():
    """Yes + No together are worth exactly 100c, so the pair closes out."""
    p = Portfolio()
    p.apply_fill(ticker="T", side="yes", action="buy", count=1, price_cents=40, fill_id="f1")
    p.apply_fill(ticker="T", side="no", action="buy", count=1, price_cents=45, fill_id="f2")
    assert p.position("T").is_flat
    # 100 - 40 - fee - 45 - fee
    assert p.realized_cents() == 100 - (40 + taker_fee_cents(40, 1)) - 45 - taker_fee_cents(45, 1)


def test_gross_spend_accumulates_for_the_event_cap():
    p = Portfolio()
    p.apply_fill(ticker="A", side="yes", action="buy", count=1, price_cents=40, fill_id="f1")
    p.apply_fill(ticker="B", side="no", action="buy", count=2, price_cents=30, fill_id="f2")
    assert p.gross_spend_cents == (40 + taker_fee_cents(40, 1)) + (60 + taker_fee_cents(30, 2))


def test_sells_do_not_add_to_gross_spend():
    p = Portfolio()
    p.apply_fill(ticker="T", side="yes", action="buy", count=1, price_cents=40, fill_id="f1")
    before = p.gross_spend_cents
    p.apply_fill(ticker="T", side="yes", action="sell", count=1, price_cents=60, fill_id="f2")
    assert p.gross_spend_cents == before


# -- marking ----------------------------------------------------------------
def test_unrealized_marks_yes_to_the_yes_bid():
    pos = Position("T", side="yes", count=2, cost_cents=80)
    assert pos.unrealized_cents(book(yes_bid=50)) == 50 * 2 - 80


def test_unrealized_marks_no_to_the_no_bid():
    pos = Position("T", side="no", count=1, cost_cents=50)
    assert pos.unrealized_cents(book(no_bid=55)) == 5


def test_flat_position_has_no_unrealized():
    assert Position("T").unrealized_cents(book()) == 0


def test_no_bid_means_no_mark():
    empty = OrderBook("T")
    empty.apply_snapshot([], [], now=1000.0)
    assert Position("T", side="yes", count=1, cost_cents=40).unrealized_cents(empty) == 0


def test_settled_value_pays_a_winning_side():
    pos = Position("T", side="yes", count=2, cost_cents=80)
    assert pos.settled_value_cents(resolves_yes=True) == 200 - 80
    assert pos.settled_value_cents(resolves_yes=False) == -80


def test_total_pnl_combines_realized_and_unrealized():
    p = Portfolio()
    p.apply_fill(ticker="T", side="yes", action="buy", count=1, price_cents=40, fill_id="f1")
    books = {"T": book(yes_bid=70)}
    assert p.total_pnl_cents(books) == p.realized_cents() + p.unrealized_cents(books)


# -- reconciliation ----------------------------------------------------------
def test_reconcile_adopts_the_api_count():
    p = Portfolio()
    p.apply_fill(ticker="T", side="yes", action="buy", count=1, price_cents=40, fill_id="f1")
    drifted = p.reconcile_positions([{"ticker": "T", "position": 3}])
    assert drifted == ["T"]
    assert p.position("T").count == 3 and p.position("T").side == "yes"


def test_reconcile_reads_a_negative_position_as_no():
    p = Portfolio()
    p.reconcile_positions([{"ticker": "T", "position": -2}])
    pos = p.position("T")
    assert pos.side == "no" and pos.count == 2


def test_reconcile_flattens_on_a_zero_position():
    p = Portfolio()
    p.apply_fill(ticker="T", side="yes", action="buy", count=2, price_cents=40, fill_id="f1")
    p.reconcile_positions([{"ticker": "T", "position": 0}])
    assert p.position("T").is_flat


def test_reconcile_reports_no_drift_when_aligned():
    p = Portfolio()
    p.apply_fill(ticker="T", side="yes", action="buy", count=2, price_cents=40, fill_id="f1")
    assert p.reconcile_positions([{"ticker": "T", "position": 2}]) == []


def test_reconcile_preserves_cost_basis_per_contract():
    p = Portfolio()
    p.apply_fill(ticker="T", side="yes", action="buy", count=2, price_cents=40, fill_id="f1")
    per_contract = p.position("T").avg_price_cents
    p.reconcile_positions([{"ticker": "T", "position": 4}])
    assert p.position("T").avg_price_cents == per_contract
