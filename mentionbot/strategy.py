"""The trading rule.

All prices are integer cents. Every edge is quoted *net of the taker fee* we
would pay on the fill, because we always cross the spread.

    enter Yes  when  jev_p - yes_ask - fee(yes_ask)        >= entry_gap
    enter No   when  (100 - jev_p) - no_ask - fee(no_ask)  >= entry_gap
    exit Yes   when  jev_p - yes_bid - fee(yes_bid)        <= exit_gap
    exit No    when  (100 - jev_p) - no_bid - fee(no_bid)  <= exit_gap

Once our own transcript count reaches a market's threshold we treat it as
settled: fair value is pinned to 100, a Yes position is held to settlement, and
any No position is sold at the bid. Yes is never bought above
``max_price_after_mention`` once we have heard the term at all - if the
transcriber mis-heard, that cap is what limits the damage.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .kalshi.book import OrderBook
from .kalshi.fees import taker_fee_cents
from .portfolio import Position
from .terms import TermMarket


@dataclass(frozen=True)
class Action:
    """An order the strategy wants to place."""

    ticker: str
    kind: str  # "enter" | "exit"
    side: str  # "yes" | "no"
    action: str  # "buy" | "sell"
    count: int
    limit_cents: int
    edge_cents: int
    reason: str


@dataclass(frozen=True)
class Quote:
    """What the strategy saw when it decided, for the dashboard and logs."""

    fair_cents: int | None = None
    yes_bid: int | None = None
    yes_ask: int | None = None
    no_bid: int | None = None
    no_ask: int | None = None
    entry_edge_yes: int | None = None
    entry_edge_no: int | None = None
    exit_edge: int | None = None


def max_affordable(
    price_cents: int, budget_cents: int, want: int, available: int | None = None
) -> int:
    """Largest contract count at ``price_cents`` that fits ``budget_cents``.

    Fees are part of the cost, so they are part of the budget test.
    """
    n = min(want, available if available is not None else want)
    while n > 0:
        if price_cents * n + taker_fee_cents(price_cents, n) <= budget_cents:
            return n
        n -= 1
    return 0


def entry_size(
    settings: Settings,
    position: Position,
    spend_cents: int,
    price_cents: int,
    available: int | None = None,
) -> int:
    """Contracts to buy, after the per-market and per-event caps."""
    room = settings.max_contracts_per_market - position.count
    if room <= 0:
        return 0
    want = min(settings.contracts_per_entry, room)
    budget = settings.max_cents_per_event - spend_cents
    if budget <= 0:
        return 0
    return max_affordable(price_cents, budget, want, available)


def evaluate(
    *,
    market: TermMarket,
    book: OrderBook,
    position: Position,
    settings: Settings,
    jev_p: int | None,
    resolved_yes: bool,
    mention_detected: bool,
    spend_cents: int,
    entries_allowed: bool,
) -> tuple[Action | None, Quote]:
    """Decide what to do in one market this cycle.

    Returns the action to take (or None) plus the quote it was based on.
    Exits are evaluated before entries and are never gated by
    ``entries_allowed``.
    """
    yes_bid, yes_ask = book.best_yes_bid, book.yes_ask
    no_bid, no_ask = book.best_no_bid, book.no_ask

    # Our own count overrides Jev once the market is decided.
    fair = 100 if resolved_yes else jev_p
    quote = Quote(fair, yes_bid, yes_ask, no_bid, no_ask)

    # -- settled markets --------------------------------------------------
    if resolved_yes and not position.is_flat:
        if position.side == "yes":
            # Hold to settlement: it pays 100.
            return None, quote
        if no_bid is not None:
            return (
                Action(
                    ticker=market.ticker,
                    kind="exit",
                    side="no",
                    action="sell",
                    count=position.count,
                    limit_cents=no_bid,
                    edge_cents=0,
                    reason="term already said; closing No position",
                ),
                quote,
            )
        return None, quote

    if fair is None:
        return None, quote  # no fair value yet: nothing to compare against

    # -- exits ------------------------------------------------------------
    if not position.is_flat:
        if position.side == "yes" and yes_bid is not None:
            edge = fair - yes_bid - taker_fee_cents(yes_bid, position.count)
            quote = Quote(fair, yes_bid, yes_ask, no_bid, no_ask, exit_edge=edge)
            if edge <= settings.exit_gap:
                return (
                    Action(
                        ticker=market.ticker,
                        kind="exit",
                        side="yes",
                        action="sell",
                        count=position.count,
                        limit_cents=yes_bid,
                        edge_cents=edge,
                        reason=f"Yes edge {edge}c <= exit_gap {settings.exit_gap}c",
                    ),
                    quote,
                )
        elif position.side == "no" and no_bid is not None:
            edge = (100 - fair) - no_bid - taker_fee_cents(no_bid, position.count)
            quote = Quote(fair, yes_bid, yes_ask, no_bid, no_ask, exit_edge=edge)
            if edge <= settings.exit_gap:
                return (
                    Action(
                        ticker=market.ticker,
                        kind="exit",
                        side="no",
                        action="sell",
                        count=position.count,
                        limit_cents=no_bid,
                        edge_cents=edge,
                        reason=f"No edge {edge}c <= exit_gap {settings.exit_gap}c",
                    ),
                    quote,
                )
        # Holding and not exiting: one position per market, so never add.
        return None, quote

    # -- entries ----------------------------------------------------------
    edge_yes = (
        fair - yes_ask - taker_fee_cents(yes_ask, settings.contracts_per_entry)
        if yes_ask is not None
        else None
    )
    edge_no = (
        (100 - fair) - no_ask - taker_fee_cents(no_ask, settings.contracts_per_entry)
        if no_ask is not None
        else None
    )
    quote = Quote(fair, yes_bid, yes_ask, no_bid, no_ask, edge_yes, edge_no)

    if not entries_allowed or not market.tradable:
        return None, quote

    # Both sides can never clear a positive gap at once (the asks sum to >=100),
    # but if the book is crossed, take the better edge.
    candidates = []
    if edge_yes is not None and edge_yes >= settings.entry_gap:
        candidates.append(("yes", yes_ask, edge_yes))
    if edge_no is not None and edge_no >= settings.entry_gap:
        candidates.append(("no", no_ask, edge_no))
    if not candidates:
        return None, quote
    side, price, edge = max(candidates, key=lambda c: c[2])

    # Transcription-error guard: never chase Yes after we think we heard it.
    if side == "yes" and mention_detected and price > settings.max_price_after_mention:
        return None, quote

    available = book.size_at_yes_ask() if side == "yes" else book.size_at_no_ask()
    count = entry_size(settings, position, spend_cents, price, available)
    if count < 1:
        return None, quote

    return (
        Action(
            ticker=market.ticker,
            kind="enter",
            side=side,
            action="buy",
            count=count,
            limit_cents=price,
            edge_cents=edge,
            reason=f"{side} edge {edge}c >= entry_gap {settings.entry_gap}c",
        ),
        quote,
    )


def flatten_action(
    market_ticker: str, position: Position, book: OrderBook
) -> Action | None:
    """Sell the whole position at the bid - used by the kill switch."""
    if position.is_flat:
        return None
    bid = book.best_yes_bid if position.side == "yes" else book.best_no_bid
    if bid is None:
        return None
    return Action(
        ticker=market_ticker,
        kind="exit",
        side=position.side or "yes",
        action="sell",
        count=position.count,
        limit_cents=bid,
        edge_cents=0,
        reason="kill switch: flatten at bid",
    )
