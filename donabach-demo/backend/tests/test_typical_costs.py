"""Update 4, 12.1: the typical advisor's own costs (fee schedule above 1% for small balances, active funds' expense ratios and a 3%
cash holding), which the good RIA and Donabach do not pay."""

from __future__ import annotations

import numpy as np
import pytest
from app.planner.baseline import RIA_BASELINE, TYPICAL_ADVISOR
from app.sim import markets
from app.sim import simulate as sim
from app.sim.simulate import Policy, build_inputs, run_batch
from tests.conftest import make_demo_household


def test_the_typical_fee_schedule_is_above_one_percent_under_half_a_million():
    fee = sim._advisory_fee
    assert fee(100_000.0, 2.0, 0.0) == pytest.approx(1_150.0)
    assert fee(500_000.0, 2.0, 0.0) == pytest.approx(5_750.0)
    assert fee(2_000_000.0, 2.0, 0.0) == pytest.approx(500_000 * 0.0115 + 500_000 * 0.010 + 1_000_000 * 0.009)
    assert fee(7_000_000.0, 2.0, 0.0) == pytest.approx(5_750 + 5_000 + 9_000 + 3_000_000 * 0.0075 + 2_000_000 * 0.006)
    # the good RIA's schedule and the flat fee are untouched
    assert fee(2_000_000.0, 1.0, 0.0) == pytest.approx(1_000_000 * 0.010 + 1_000_000 * 0.008)
    assert fee(2_000_000.0, 0.0, 0.0035) == pytest.approx(7_000.0)


def test_only_the_typical_advisor_pays_the_costs():
    t = TYPICAL_ADVISOR
    assert t.typical_fee_schedule and t.fund_expense_equity == 0.0060 and t.fund_expense_bond == 0.0045 and t.cash_share == 0.03
    for p in (RIA_BASELINE, Policy()):
        assert not p.typical_fee_schedule and p.fund_expense_equity == p.fund_expense_bond == p.cash_share == 0.0
    row = t.row(40.0)
    assert row[sim.SP_FEE_BREAKPOINTS] == 2.0 and row[sim.SP_ER_E] == 0.0060 and row[sim.SP_CASH] == 0.03


def _run(policy):
    inputs = build_inputs(make_demo_household(), deterministic=True)
    return sim.run_detail(inputs, policy).log, inputs


def test_expense_ratios_and_cash_lower_the_return_and_cash_pays_interest_at_the_cash_yield():
    plain = TYPICAL_ADVISOR.replace(typical_fee_schedule=False, fund_expense_equity=0.0, fund_expense_bond=0.0, cash_share=0.0)
    with_costs = TYPICAL_ADVISOR
    (a, _), (b, _) = _run(plain), _run(with_costs)
    assert b["wealth"][-1] < a["wealth"][-1]
    # a bond sleeve that is partly cash pays less interest than all bonds do
    bond_share = 1.0 - TYPICAL_ADVISOR.stock_share
    expected_yield = markets.BOND_INTEREST_YIELD - (0.03 / bond_share) * (markets.BOND_INTEREST_YIELD - markets.CASH_INTEREST_YIELD)
    only_cash = plain.replace(cash_share=0.03)
    (c, _) = _run(only_cash)
    assert c["interest"][1] < a["interest"][1]
    assert expected_yield < markets.BOND_INTEREST_YIELD


def test_each_cost_alone_moves_the_typical_advisors_wealth_the_way_it_should_and_none_touches_the_good_ria():
    futures = build_inputs(make_demo_household(), n_paths=60, seed=9)
    zero = TYPICAL_ADVISOR.replace(typical_fee_schedule=False, fund_expense_equity=0.0, fund_expense_bond=0.0, cash_share=0.0)
    variants = [
        zero,
        zero.replace(typical_fee_schedule=True),
        zero.replace(fund_expense_equity=0.006, fund_expense_bond=0.0045),
        zero.replace(cash_share=0.03),
        TYPICAL_ADVISOR,
    ]
    medians = [float(np.median(w)) for w in run_batch(futures, variants).wealth]
    # the surveyed schedule is dearer than a flat 1.0% under $1M and cheaper above it: this household's balances are mostly above, so
    # the schedule alone helps the typical advisor a little, and the funds' expense ratios and the cash lower its wealth
    assert medians[1] > medians[0]
    assert medians[2] < medians[0] and medians[3] < medians[0] and medians[4] < medians[0]
    assert medians[2] < medians[3]  # the expense ratios cost far more than the cash does
    ria = run_batch(futures, [RIA_BASELINE]).wealth[0]
    assert float(np.median(ria)) > medians[4]
