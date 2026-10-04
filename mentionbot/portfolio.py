"""Position, fill and P&L tracking, reconciled against Kalshi's portfolio API.

All money is integer cents. A Kalshi position is one-sided per market: holding
Yes and No at once is just a hedged pair, so we keep at most one side.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .kalshi.book import OrderBook
from .kalshi.fees import taker_fee_cents


@dataclass
class Position:
    """Our holding in one market."""

    ticker: str
    side: str | None = None  # "yes" | "no" | None when flat
    count: int = 0
    cost_cents: int = 0  # total paid for the open contracts, fees included
    realized_cents: int = 0
    fees_cents: int = 0

    @property
    def is_flat(self) -> bool:
        return self.count <= 0 or self.side is None

    @property
    def avg_price_cents(self) -> float:
        return self.cost_cents / self.count if self.count else 0.0

    def unrealized_cents(self, book: OrderBook) -> int:
        """Mark to the bid we could actually hit right now."""
        if self.is_flat:
            return 0
        bid = book.best_yes_bid if self.side == "yes" else book.best_no_bid
        if bid is None:
            return 0
        return int(bid * self.count - self.cost_cents)

    def settled_value_cents(self, resolves_yes: bool) -> int:
        """Value at settlement, for a market we believe is already decided."""
        if self.is_flat:
            return 0
        wins = (self.side == "yes") == resolves_yes
        return int((100 * self.count if wins else 0) - self.cost_cents)


@dataclass
class Portfolio:
    """Positions across the event, plus event-wide spend and P&L."""

    positions: dict[str, Position] = field(default_factory=dict)
    seen_fill_ids: set[str] = field(default_factory=set)
    gross_spend_cents: int = 0  # cumulative buy notional, for the event cap
    updated_at: float = 0.0

    def position(self, ticker: str) -> Position:
        return self.positions.setdefault(ticker, Position(ticker))

    # -- fills -----------------------------------------------------------
    def apply_fill(
        self,
        *,
        ticker: str,
        side: str,
        action: str,
        count: int,
        price_cents: int,
        fill_id: str | None = None,
        fee_cents: int | None = None,
    ) -> bool:
        """Apply one fill. Returns False if it was a duplicate we already had."""
        if fill_id is not None:
            if fill_id in self.seen_fill_ids:
                return False
            self.seen_fill_ids.add(fill_id)

        pos = self.position(ticker)
        fee = taker_fee_cents(price_cents, count) if fee_cents is None else fee_cents
        pos.fees_cents += fee

        if action == "buy":
            if pos.is_flat:
                pos.side = side
                pos.count = count
                pos.cost_cents = price_cents * count + fee
            elif pos.side == side:
                pos.count += count
                pos.cost_cents += price_cents * count + fee
            else:
                # Buying the other side closes exposure: a Yes and a No together
                # are worth exactly 100c, so the pair realises 100 - both costs.
                closed = min(count, pos.count)
                basis = int(round(pos.avg_price_cents * closed))
                pos.realized_cents += 100 * closed - basis - price_cents * closed - fee
                pos.count -= closed
                pos.cost_cents -= basis
                if pos.count == 0:
                    pos.side = None
                    pos.cost_cents = 0
            self.gross_spend_cents += price_cents * count + fee
        elif action == "sell":
            closed = min(count, pos.count)
            if closed:
                basis = int(round(pos.avg_price_cents * closed))
                pos.realized_cents += price_cents * closed - basis - fee
                pos.count -= closed
                pos.cost_cents -= basis
                if pos.count == 0:
                    pos.side = None
                    pos.cost_cents = 0
        else:
            raise ValueError(f"unknown fill action: {action!r}")

        self.updated_at = time.time()
        return True

    # -- reconciliation --------------------------------------------------
    def reconcile_positions(self, api_positions: list[dict]) -> list[str]:
        """Align local counts with Kalshi's. Returns tickers that disagreed.

        Kalshi reports a signed ``position``: positive is Yes, negative is No.
        Kalshi is the source of truth; we adopt its count and keep our cost
        basis per contract where we have one.
        """
        drifted: list[str] = []
        for entry in api_positions:
            ticker = entry.get("ticker")
            if not ticker:
                continue
            signed = int(entry.get("position") or 0)
            side = "yes" if signed > 0 else ("no" if signed < 0 else None)
            count = abs(signed)
            pos = self.position(ticker)
            if pos.count != count or pos.side != side:
                drifted.append(ticker)
                per_contract = pos.avg_price_cents or 0.0
                pos.side = side
                pos.count = count
                pos.cost_cents = int(round(per_contract * count)) if count else 0
            realized = entry.get("realized_pnl")
            if realized is not None:
                pos.realized_cents = int(realized)
        self.updated_at = time.time()
        return drifted

    # -- aggregates ------------------------------------------------------
    def realized_cents(self) -> int:
        return sum(p.realized_cents for p in self.positions.values())

    def unrealized_cents(self, books: dict[str, OrderBook]) -> int:
        total = 0
        for ticker, pos in self.positions.items():
            book = books.get(ticker)
            if book is not None:
                total += pos.unrealized_cents(book)
        return total

    def total_pnl_cents(self, books: dict[str, OrderBook]) -> int:
        return self.realized_cents() + self.unrealized_cents(books)

    def open_exposure_cents(self) -> int:
        return sum(p.cost_cents for p in self.positions.values() if not p.is_flat)
