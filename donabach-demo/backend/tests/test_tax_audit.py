"""Update 4, section 2: the tax audit. A household that sells a known amount of stock with a known cost basis in one year pays
the tax a hand calculation says, to the cent, including the 3.8% investment income tax and Illinois; and every strategy is
valued at the end by the same tax-engine calculation instead of a flat rate."""

from __future__ import annotations

import numpy as np
import pytest
from app.planner.baseline import RIA_BASELINE
from app.schemas import Accounts, Household
from app.sim import markets
from app.sim import simulate as sim
from app.sim.simulate import ModelOptions, Policy, build_inputs, run_detail
from app.tax.engine import TaxInputs, compute_return, liquidation_taxes
from tests.conftest import make_demo_household

# 2026 married-filing-jointly figures, typed in again here from IRS Rev. Proc. 2025-32 so that the hand calculation does not
# read the engine's own tables.
BRACKETS = [(24_800, 0.10), (100_800, 0.12), (211_400, 0.22), (403_550, 0.24), (512_450, 0.32), (768_700, 0.35), (float("inf"), 0.37)]
STANDARD = 32_200
ZERO_TOP, FIFTEEN_TOP = 98_900, 613_700


def hand_tax(wages, qualified, long_term_gain, children=0):
    """Federal and Illinois tax on wages, qualified dividends and a long-term gain, worked out by hand (the order of a Schedule D
    tax worksheet: ordinary income fills the brackets, the preferential income stacks on top of it)."""
    agi = wages + qualified + long_term_gain
    taxable = max(0.0, agi - STANDARD)
    preferential = min(taxable, qualified + long_term_gain)
    ordinary = taxable - preferential
    ordinary_tax, lower = 0.0, 0.0
    for top, rate in BRACKETS:
        if ordinary > lower:
            ordinary_tax += (min(ordinary, top) - lower) * rate
        lower = top
    bottom, top = ordinary, ordinary + preferential
    at15 = max(0.0, min(top, FIFTEEN_TOP) - max(bottom, ZERO_TOP))
    at20 = max(0.0, top - max(bottom, FIFTEEN_TOP))
    capital_gains_tax = 0.15 * at15 + 0.20 * at20
    niit = 0.038 * min(qualified + long_term_gain, max(0.0, agi - 250_000))
    credit = max(0.0, 2_200 * children - 50 * np.ceil(max(0.0, agi - 400_000) / 1_000))
    federal = ordinary_tax + capital_gains_tax + niit - min(credit, ordinary_tax + capital_gains_tax)
    exemptions = 0.0 if agi > 500_000 else 2_925 * (2 + children)
    illinois = 0.0495 * max(0.0, agi - exemptions)
    return federal, illinois, niit


def test_hand_calculation_of_selling_a_million_dollars_of_stock_with_a_400k_basis():
    """$1,000,000 of stock bought for $400,000, sold in a year with $150,000 of wages and $5,000 of qualified dividends."""
    before = hand_tax(150_000, 5_000, 0)
    after = hand_tax(150_000, 5_000, 600_000)
    # worked on paper: AGI 755,000, taxable 722,800; ordinary taxable 117,800 -> 2,480 + 9,120 + 3,740 = 15,340;
    # gains: 495,900 at 15% + 109,100 at 20% = 74,385 + 21,820 = 96,205; NIIT 3.8% of (755,000 - 250,000) = 19,190;
    # federal 130,735; Illinois 4.95% of 755,000 (no exemption above 500,000) = 37,372.50
    assert after[0] == pytest.approx(130_735.0) and after[1] == pytest.approx(37_372.50) and after[2] == pytest.approx(19_190.0)
    # the same year without the sale: ordinary tax 15,340 + 750 on the dividends = 16,090; Illinois (155,000 - 5,850) * 4.95%
    assert before[0] == pytest.approx(16_090.0) and before[1] == pytest.approx(7_382.925)
    added_by_hand = sum(after[:2]) - sum(before[:2])
    assert added_by_hand == pytest.approx(144_634.575)

    def engine(gain):
        return compute_return(TaxInputs(wages=150_000, qualified_dividends=5_000, ordinary_dividends=5_000, net_capital_gain=gain))

    r = engine(600_000)
    assert r.federal_total == pytest.approx(130_735.0) and r.illinois_tax == pytest.approx(37_372.50) and r.niit == pytest.approx(19_190.0)
    assert r.grand_total - engine(0).grand_total == pytest.approx(added_by_hand)


@pytest.mark.parametrize("gain", [20_000, 150_000, 600_000, 2_000_000])
def test_the_engine_agrees_with_the_hand_calculation_at_several_sizes(gain):
    r = compute_return(TaxInputs(wages=120_000, qualified_dividends=8_000, ordinary_dividends=8_000, net_capital_gain=gain))
    federal, illinois, niit = hand_tax(120_000, 8_000, gain)
    assert (r.federal_total, r.illinois_tax, r.niit) == pytest.approx((federal, illinois, niit))


# An advisor who holds only stock, charges nothing and harvests nothing: the only sale in the run is the one the test asks for.
STOCK_ONLY = Policy(
    stock_share=1.0, glide_start_age=None, glide_drop=0.0, donabach_location=False, flat_fee=0.0, tax_loss_harvesting=False,
    bracket_withdrawals=False, lot_method="fifo", short_term_ordinary=True,
)


def _household(value, basis):
    return make_demo_household(
        accounts=Accounts(brokerage_value=value, brokerage_basis=basis, pretax_balance=0.0, roth_balance=0.0, cash=0.0),
    )


def test_the_simulator_adds_the_tax_the_hand_calculation_says_when_the_advisor_sells_everything_in_one_year():
    value, basis = 1_000_000.0, 400_000.0
    base = _household(value, basis)
    inputs = build_inputs(base, deterministic=True)
    r_e = float(inputs.rets[0, 0, 0])
    grown = value * (1.0 + r_e)
    # the year's goal is the whole position: the advisor sells all of it (the reinvested dividends are in the basis too)
    seller = base.model_copy(update={"goals": base.goals.model_copy(update={"home_purchase_in_years": 0, "home_down_payment": grown})})
    with_sale = run_detail(build_inputs(seller, deterministic=True), STOCK_ONLY).log
    without = run_detail(inputs, STOCK_ONLY).log
    gain = with_sale["net_gain"][0]
    dividends = markets.DIVIDEND_YIELD * value
    assert gain == pytest.approx(value * (1.0 + r_e) - basis - dividends)  # the cost basis went up by the dividends reinvested
    assert without["net_gain"][0] == pytest.approx(0.0)
    wages = with_sale["wages_taxable"][0]
    assert wages == pytest.approx(without["wages_taxable"][0])
    interest = with_sale["interest"][0]
    assert interest == 0.0  # no bonds were held
    h_before = hand_tax(wages, dividends, 0.0, children=1)
    h_after = hand_tax(wages, dividends, gain, children=1)
    assert with_sale["fed_tax"][0] == pytest.approx(h_after[0]) and with_sale["il_tax"][0] == pytest.approx(h_after[1])
    assert without["fed_tax"][0] == pytest.approx(h_before[0]) and without["il_tax"][0] == pytest.approx(h_before[1])
    added = with_sale["total_tax"][0] - without["total_tax"][0]
    assert added == pytest.approx(sum(h_after[:2]) - sum(h_before[:2]))
    assert added > 0.2 * gain  # long-term rates, the 3.8% tax and Illinois together are a good fifth of the gain


def _liquidation(**kw):
    args = dict(
        unrealized=0.0, deferred_gain=0.0, deferred_gain_short=0.0, deferred_withdrawals=0.0, pretax=0.0, carryforward=0.0,
        social_security=0.0, interest=0.0, dividends=0.0, aged_spouses=0.0, kids=0.0, deps=0.0,
    )
    args.update(kw)
    return liquidation_taxes(**args)


def test_the_valuation_realizes_gains_evenly_over_five_years_with_the_engines_own_tax():
    gain = 1_000_000.0
    pretax_tax, gains_tax = _liquidation(unrealized=gain)
    each = gain / 5
    federal, illinois, _ = hand_tax(0.0, 0.0, each)
    nothing = hand_tax(0.0, 0.0, 0.0)
    assert pretax_tax == 0.0
    assert gains_tax == pytest.approx(5 * (sum(federal_il for federal_il in (federal, illinois)) - sum(nothing[:2])))
    # with no other income the standard deduction and the 0% bracket take a part of every year's gain: under the flat 15% ...
    assert gains_tax / gain < 0.15
    # ... and with a large pre-tax balance and Social Security beside it the same gain costs more than 15% (20% bracket, 3.8%, Illinois)
    assert _liquidation(unrealized=gain, pretax=4_000_000.0, social_security=60_000.0)[1] / gain > 0.15


def test_the_valuation_stacks_gains_on_the_pre_tax_withdrawals_and_social_security():
    alone = _liquidation(unrealized=500_000.0)[1]
    on_top = _liquidation(unrealized=500_000.0, pretax=2_000_000.0, social_security=50_000.0)[1]
    assert on_top > alone  # the gains sit in higher brackets and the net investment income tax reaches them


def test_a_loss_carryforward_offsets_the_gains_it_is_valued_against():
    gain, carry = 400_000.0, 400_000.0
    assert _liquidation(unrealized=gain, carryforward=carry)[1] < 3_000 * 5  # only the $3,000 a year of ordinary income is left
    assert _liquidation(unrealized=gain, carryforward=0.0)[1] > _liquidation(unrealized=gain, carryforward=carry)[1]


def test_gains_realized_in_the_last_year_are_taxed_by_the_engine_not_a_flat_rate():
    taxed = _liquidation(deferred_gain=300_000.0)[1]
    assert taxed == pytest.approx(compute_return(TaxInputs(net_capital_gain=300_000.0)).grand_total)
    assert taxed != pytest.approx(0.15 * 300_000.0)


def test_pre_tax_withdrawals_made_to_pay_the_last_years_tax_are_taxed_too():
    plain = _liquidation(pretax=100_000.0)[0]
    withdrawn = _liquidation(pretax=100_000.0, deferred_withdrawals=40_000.0)[0]
    # they land in the first year on top of that year's 1/20th of the balance
    stacked = compute_return(TaxInputs(retirement_distributions=5_000.0 + 40_000.0)).grand_total
    year_alone = compute_return(TaxInputs(retirement_distributions=5_000.0)).grand_total
    assert withdrawn - plain == pytest.approx(stacked - year_alone)


def test_valuation_option_flat_reproduces_the_old_formula_and_the_engine_one_differs():
    h = make_demo_household(accounts=Accounts(brokerage_value=900_000, brokerage_basis=200_000, pretax_balance=500_000, roth_balance=50_000, cash=10_000))
    flat = sim.initial_after_tax_wealth(h, ModelOptions(valuation="flat"))
    engine = sim.initial_after_tax_wealth(h)
    assert flat != pytest.approx(engine)
    pretax = 500_000.0
    old_rate = float(sim.pretax_withdrawal_rate(pretax, h.social_security.annual_benefit, 0.0))
    assert flat == pytest.approx(900_000 + 10_000 - 0.15 * 700_000 + 50_000 + pretax - pretax * old_rate)


def test_every_strategy_gets_the_same_valuation_the_batch_and_the_year_log_agree():
    h = make_demo_household()
    futures = build_inputs(h, n_paths=30, seed=3)
    batch = sim.run_batch(futures, [RIA_BASELINE])
    detail = run_detail(build_inputs(h, deterministic=True), RIA_BASELINE)
    assert np.isfinite(batch.wealth).all() and batch.wealth.min() > 0
    assert detail.log["wealth"][-1] == pytest.approx(detail.wealth[0, 0])
    assert detail.pretax_owed[0, 0] >= 0.0
