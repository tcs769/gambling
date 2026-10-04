"""Entry/exit, side selection, fee netting and caps."""


from mentionbot.config import Settings
from mentionbot.kalshi.book import OrderBook
from mentionbot.kalshi.fees import taker_fee_cents
from mentionbot.portfolio import Position
from mentionbot.strategy import entry_size, evaluate, flatten_action, max_affordable
from mentionbot.terms import TermMarket


def settings(**kw) -> Settings:
    s = Settings()
    for k, v in kw.items():
        setattr(s, k, v)
    s.validate()
    return s


def book(yes_bid=None, no_bid=None, size=100) -> OrderBook:
    b = OrderBook("T")
    b.apply_snapshot(
        [[yes_bid, size]] if yes_bid else [],
        [[no_bid, size]] if no_bid else [],
        now=1_000_000.0,
    )
    return b


def market(**kw) -> TermMarket:
    base = dict(ticker="T", title="Tariff", variants=["tariff"], threshold=1)
    base.update(kw)
    return TermMarket(**base)


def run(**kw):
    params = dict(
        market=market(),
        book=book(yes_bid=40, no_bid=55),
        position=Position("T"),
        settings=settings(),
        jev_p=50,
        resolved_yes=False,
        mention_detected=False,
        spend_cents=0,
        entries_allowed=True,
    )
    params.update(kw)
    return evaluate(**params)


# -- ask derivation feeding the rule --------------------------------------
def test_quote_uses_derived_asks():
    _, q = run()
    assert (q.yes_bid, q.yes_ask) == (40, 45)  # 100 - no_bid 55
    assert (q.no_bid, q.no_ask) == (55, 60)    # 100 - yes_bid 40


# -- entries ---------------------------------------------------------------
def test_buys_yes_when_jev_far_above_ask():
    # yes_ask 45, fee@45 = 1 -> edge = 80 - 45 - 1 = 34 >= 15
    action, q = run(jev_p=80)
    assert action is not None
    assert (action.kind, action.side, action.action) == ("enter", "yes", "buy")
    assert action.limit_cents == 45
    assert action.edge_cents == 80 - 45 - taker_fee_cents(45, 1)


def test_buys_no_when_jev_far_below():
    # no_ask 60, fee@60 = 2 -> edge = (100-20) - 60 - 2 = 18 >= 15
    action, _ = run(jev_p=20)
    assert action is not None
    assert (action.side, action.action, action.limit_cents) == ("no", "buy", 60)


def test_no_trade_inside_the_gap():
    assert run(jev_p=50)[0] is None


def test_fee_is_netted_out_of_the_entry_edge():
    """A raw gap of exactly entry_gap must NOT trade once the fee is charged."""
    # yes_ask 45, fee@45 = 2c. Raw gap 15 (jev 60) nets to 13 -> no trade.
    assert taker_fee_cents(45, 1) == 2
    assert run(jev_p=60)[0] is None
    assert run(jev_p=61)[0] is None   # net 14, still short
    assert run(jev_p=62)[0] is not None  # net 15, clears


def test_entry_blocked_when_entries_not_allowed():
    assert run(jev_p=90, entries_allowed=False)[0] is None


def test_entry_blocked_for_flagged_market():
    m = market()
    m.flagged_reason = "rules mention compound words"
    assert run(jev_p=90, market=m)[0] is None


def test_no_fair_value_means_no_trade():
    assert run(jev_p=None)[0] is None


def test_empty_book_means_no_trade():
    assert run(jev_p=90, book=book())[0] is None


def test_takes_the_better_side_if_both_clear():
    """A crossed book must not produce two orders; take the bigger edge."""
    crossed = book(yes_bid=80, no_bid=80)  # yes_ask 20, no_ask 20
    action, _ = run(jev_p=60, book=crossed)
    assert action is not None and action.side == "yes"


# -- one position per market ----------------------------------------------
def test_never_averages_in():
    held = Position("T", side="yes", count=1, cost_cents=30)
    # Edge is huge but we already hold Yes: no second entry.
    assert run(jev_p=95, position=held)[0] is None


# -- exits -----------------------------------------------------------------
def test_exits_yes_when_edge_collapses():
    held = Position("T", side="yes", count=2, cost_cents=60)
    # yes_bid 40, fee@40x2 = 4 -> edge = 44 - 40 - 4 = 0 <= 5
    action, _ = run(jev_p=44, position=held)
    assert action is not None
    assert (action.kind, action.side, action.action) == ("exit", "yes", "sell")
    assert (action.limit_cents, action.count) == (40, 2)


def test_holds_yes_while_edge_remains():
    held = Position("T", side="yes", count=1, cost_cents=30)
    assert run(jev_p=90, position=held)[0] is None


def test_exits_no_when_edge_collapses():
    held = Position("T", side="no", count=1, cost_cents=50)
    # no_bid 55, fee@55x1 = 2 -> edge = (100-45) - 55 - 2 = -2 <= 5
    action, _ = run(jev_p=45, position=held)
    assert action is not None
    assert (action.side, action.action, action.limit_cents) == ("no", "sell", 55)


def test_holds_no_while_edge_remains():
    held = Position("T", side="no", count=1, cost_cents=50)
    assert run(jev_p=10, position=held)[0] is None


def test_exit_allowed_even_when_entries_blocked():
    held = Position("T", side="yes", count=1, cost_cents=60)
    action, _ = run(jev_p=40, position=held, entries_allowed=False)
    assert action is not None and action.kind == "exit"


# -- resolved-Yes handling -------------------------------------------------
def test_resolved_yes_holds_yes_to_settlement():
    held = Position("T", side="yes", count=1, cost_cents=30)
    assert run(resolved_yes=True, position=held, jev_p=10)[0] is None


def test_resolved_yes_sells_no_position_at_bid():
    held = Position("T", side="no", count=3, cost_cents=150)
    action, _ = run(resolved_yes=True, position=held)
    assert action is not None
    assert (action.side, action.action, action.limit_cents, action.count) == ("no", "sell", 55, 3)


def test_resolved_yes_buys_yes_when_market_lags():
    # fair pinned to 100; yes_ask 45 -> edge 54, well clear.
    action, q = run(resolved_yes=True, mention_detected=True)
    assert q.fair_cents == 100
    assert action is not None and action.side == "yes" and action.limit_cents == 45


# A 97c Yes ask can only ever show a 2c edge against a fair value of 100, so
# the price cap can only bind when entry_gap is small. These tests lower it so
# the cap is genuinely the thing doing the blocking.
def test_max_price_after_mention_caps_yes_chasing():
    expensive = book(yes_bid=90, no_bid=3)  # yes_ask = 97
    s = settings(entry_gap=2, max_price_after_mention=95)
    # Edge clears the (lowered) gap, so only the price cap can stop this.
    assert run(resolved_yes=True, mention_detected=False, book=expensive, settings=s)[0] is not None
    action, _ = run(resolved_yes=True, mention_detected=True, book=expensive, settings=s)
    assert action is None, "must not pay 97c for Yes after a detected mention"


def test_cap_applies_below_threshold_too():
    """One mention heard on a 3x market still guards against a mis-hear."""
    expensive = book(yes_bid=90, no_bid=3)  # yes_ask = 97
    s = settings(entry_gap=2, max_price_after_mention=95)
    assert run(jev_p=100, mention_detected=True, book=expensive, settings=s)[0] is None


def test_cap_allows_price_at_the_limit():
    at_limit = book(yes_bid=90, no_bid=5)  # yes_ask = 95, exactly the cap
    s = settings(entry_gap=2, max_price_after_mention=95)
    action, _ = run(jev_p=100, mention_detected=True, book=at_limit, settings=s)
    assert action is not None and action.limit_cents == 95


def test_cap_does_not_apply_to_no_side():
    """The post-mention cap guards Yes chasing only; No entries are unaffected."""
    cheap_no = book(yes_bid=2, no_bid=90)  # no_ask = 98
    s = settings(entry_gap=1, max_price_after_mention=95)
    action, _ = run(jev_p=0, mention_detected=True, book=cheap_no, settings=s)
    assert action is not None and action.side == "no" and action.limit_cents == 98


# -- sizing and caps -------------------------------------------------------
def test_max_affordable_accounts_for_fees():
    # 10 contracts at 50c = 500c plus 10c fee > 500c budget.
    assert max_affordable(50, 500, 10) == 9
    assert max_affordable(50, 10_000, 10) == 10


def test_entry_size_respects_per_market_cap():
    s = settings(contracts_per_entry=5, max_contracts_per_market=5)
    held = Position("T", side="yes", count=4, cost_cents=200)
    assert entry_size(s, held, 0, 50) == 1


def test_entry_size_respects_event_dollar_cap():
    s = settings(contracts_per_entry=5, max_contracts_per_market=5, max_dollars_per_event=1.0)
    # 100c budget at 50c/contract, minus fees, leaves one contract.
    assert entry_size(s, Position("T"), 0, 50) == 1
    assert entry_size(s, Position("T"), 100, 50) == 0


def test_entry_size_capped_by_resting_size():
    s = settings(contracts_per_entry=5, max_contracts_per_market=5)
    assert entry_size(s, Position("T"), 0, 50, available=2) == 2


def test_event_cap_blocks_the_order_entirely():
    s = settings(max_dollars_per_event=0.10)  # 10 cents
    assert run(jev_p=90, settings=s)[0] is None


def test_order_is_capped_by_book_depth():
    thin = book(yes_bid=40, no_bid=55, size=1)
    s = settings(contracts_per_entry=5, max_contracts_per_market=5)
    action, _ = run(jev_p=90, book=thin, settings=s)
    assert action is not None and action.count == 1


# -- flatten ---------------------------------------------------------------
def test_flatten_sells_yes_at_bid():
    a = flatten_action("T", Position("T", side="yes", count=2, cost_cents=80), book(yes_bid=40, no_bid=55))
    assert (a.action, a.side, a.limit_cents, a.count) == ("sell", "yes", 40, 2)


def test_flatten_sells_no_at_bid():
    a = flatten_action("T", Position("T", side="no", count=1, cost_cents=50), book(yes_bid=40, no_bid=55))
    assert (a.action, a.side, a.limit_cents) == ("sell", "no", 55)


def test_flatten_noop_when_flat():
    assert flatten_action("T", Position("T"), book(yes_bid=40, no_bid=55)) is None


def test_flatten_noop_without_a_bid():
    assert flatten_action("T", Position("T", side="yes", count=1, cost_cents=40), book()) is None
