"""Order book state for one market.

Kalshi's book is quoted as *bids on both sides*: the ``yes`` list holds bids to
buy Yes and the ``no`` list holds bids to buy No. There is no explicit ask side.
Because a Yes and a No contract together always settle for exactly 100c, an
offer to sell Yes at X is identical to a bid to buy No at 100-X. So:

    yes_ask = 100 - best_no_bid
    no_ask  = 100 - best_yes_bid

Both lists are ``[[price_cents, size], ...]``; the best bid on a side is the
*highest* price on that side.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class OrderBook:
    """Live book for a single market, maintained from snapshot + deltas."""

    ticker: str
    # price_cents -> resting size, for each side's bids
    yes_bids: dict[int, int] = field(default_factory=dict)
    no_bids: dict[int, int] = field(default_factory=dict)
    updated_at: float = 0.0
    seq: int | None = None

    # -- maintenance -----------------------------------------------------
    def apply_snapshot(
        self,
        yes: list[list[int]] | None,
        no: list[list[int]] | None,
        *,
        seq: int | None = None,
        now: float | None = None,
    ) -> None:
        """Replace the whole book from an ``orderbook_snapshot`` message."""
        self.yes_bids = {int(p): int(s) for p, s in (yes or []) if int(s) > 0}
        self.no_bids = {int(p): int(s) for p, s in (no or []) if int(s) > 0}
        self.seq = seq
        self.updated_at = time.time() if now is None else now

    def apply_delta(
        self,
        price: int,
        delta: int,
        side: str,
        *,
        seq: int | None = None,
        now: float | None = None,
    ) -> None:
        """Apply one ``orderbook_delta`` message.

        ``delta`` is a signed change to the resting size at ``price``.
        """
        side = side.lower()
        if side not in ("yes", "no"):
            raise ValueError(f"unknown book side: {side!r}")
        book = self.yes_bids if side == "yes" else self.no_bids
        new_size = book.get(int(price), 0) + int(delta)
        if new_size > 0:
            book[int(price)] = new_size
        else:
            book.pop(int(price), None)
        self.seq = seq
        self.updated_at = time.time() if now is None else now

    # -- derived quotes --------------------------------------------------
    @property
    def best_yes_bid(self) -> int | None:
        """Highest price anyone will pay for Yes."""
        return max(self.yes_bids) if self.yes_bids else None

    @property
    def best_no_bid(self) -> int | None:
        """Highest price anyone will pay for No."""
        return max(self.no_bids) if self.no_bids else None

    @property
    def yes_ask(self) -> int | None:
        """Cheapest price we can buy Yes at, derived from the No bid."""
        best_no = self.best_no_bid
        return None if best_no is None else 100 - best_no

    @property
    def no_ask(self) -> int | None:
        """Cheapest price we can buy No at, derived from the Yes bid."""
        best_yes = self.best_yes_bid
        return None if best_yes is None else 100 - best_yes

    def size_at_yes_ask(self) -> int:
        best_no = self.best_no_bid
        return self.no_bids.get(best_no, 0) if best_no is not None else 0

    def size_at_no_ask(self) -> int:
        best_yes = self.best_yes_bid
        return self.yes_bids.get(best_yes, 0) if best_yes is not None else 0

    def is_stale(self, stale_after_s: float, now: float | None = None) -> bool:
        """True if the book has never loaded or is older than ``stale_after_s``."""
        if not self.updated_at:
            return True
        return ((time.time() if now is None else now) - self.updated_at) > stale_after_s
