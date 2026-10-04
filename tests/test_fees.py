"""Kalshi fee schedule."""

import math

import pytest

from mentionbot.kalshi.fees import MAKER_RATE, TAKER_RATE, maker_fee_cents, taker_fee_cents


def test_peak_fee_at_fifty_cents():
    """0.07 x 1 x 0.5 x 0.5 = $0.0175 -> 2c once rounded up."""
    assert taker_fee_cents(50, 1) == 2


@pytest.mark.parametrize("price", range(1, 100))
def test_matches_published_formula(price):
    expected = math.ceil(TAKER_RATE * 1 * (price / 100) * (1 - price / 100) * 100)
    assert taker_fee_cents(price, 1) == expected


def test_fee_shrinks_toward_the_extremes():
    assert taker_fee_cents(50) >= taker_fee_cents(25) >= taker_fee_cents(5)
    assert taker_fee_cents(50) >= taker_fee_cents(75) >= taker_fee_cents(95)


def test_scales_with_contract_count():
    # 10 contracts at 50c: 0.07 x 10 x 0.25 = $0.175 -> 18c.
    assert taker_fee_cents(50, 10) == 18


def test_maker_is_a_quarter_of_taker_rate():
    assert pytest.approx(TAKER_RATE / 4) == MAKER_RATE
    assert maker_fee_cents(50, 100) == math.ceil(0.0175 * 100 * 0.25 * 100)


def test_zero_or_negative_count_is_free():
    assert taker_fee_cents(50, 0) == 0
    assert taker_fee_cents(50, -3) == 0


def test_boundary_prices_are_free():
    assert taker_fee_cents(0, 10) == 0
    assert taker_fee_cents(100, 10) == 0


def test_rejects_out_of_range_price():
    with pytest.raises(ValueError):
        taker_fee_cents(101, 1)
    with pytest.raises(ValueError):
        taker_fee_cents(-1, 1)


def test_float_error_does_not_inflate_an_exact_cent():
    """A fee landing exactly on a cent must not round up to the next one."""
    # 0.07 * 4 * 0.5 * 0.5 = 0.07 dollars = exactly 7c.
    assert taker_fee_cents(50, 4) == 7
