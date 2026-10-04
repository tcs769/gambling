"""Kalshi trading fees.

Kalshi's fee schedule (https://kalshi.com/docs/kalshi-fee-schedule.pdf):

    taker fees = round_up(0.07 x C x P x (1-P))
    maker fees = round_up(0.0175 x C x P x (1-P))

where ``P`` is the contract price in dollars and ``C`` the contract count.
The fee peaks at 1.75c/contract at a 50c price and shrinks toward both extremes.

We cross the spread (buy at the ask, sell at the bid), so every fill we plan is
a taker fill; ``taker_fee_cents`` is what the strategy charges itself. We round
up to the next whole cent, which is the long-standing documented behaviour and
is the conservative direction: overstating the fee can only make us trade less.
"""

from __future__ import annotations

import math

TAKER_RATE = 0.07
MAKER_RATE = 0.0175


def _fee_cents(rate: float, price_cents: int, contracts: int) -> int:
    if contracts <= 0:
        return 0
    if not 0 <= price_cents <= 100:
        raise ValueError(f"price_cents out of range: {price_cents}")
    # P*(1-P) in dollars is price_cents*(100-price_cents)/10000; converting the
    # dollar fee back to cents multiplies by 100.
    exact_cents = rate * contracts * price_cents * (100 - price_cents) / 100.0
    # Guard against binary float error tipping an exact cent up a whole cent.
    return int(math.ceil(round(exact_cents, 9)))


def taker_fee_cents(price_cents: int, contracts: int = 1) -> int:
    """Fee in whole cents for a taker fill of ``contracts`` at ``price_cents``."""
    return _fee_cents(TAKER_RATE, price_cents, contracts)


def maker_fee_cents(price_cents: int, contracts: int = 1) -> int:
    """Fee in whole cents for a maker fill of ``contracts`` at ``price_cents``."""
    return _fee_cents(MAKER_RATE, price_cents, contracts)
