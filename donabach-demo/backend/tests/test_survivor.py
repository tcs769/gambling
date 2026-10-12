"""Update 4, 12.2: the survivor phase. Mortality from the SSA table, a surviving spouse who files as a single taxpayer, spends a share
of what the couple did and draws the larger benefit, and a horizon that can run on to 90 while the batch also reports wealth at 80."""

from __future__ import annotations

import numpy as np
import pytest
from app.planner.baseline import RIA_BASELINE
from app.sim import mortality
from app.sim import simulate as sim
from app.sim.simulate import ModelOptions, build_inputs, run_batch, run_detail, survivor_flags
from app.tax import params_2026 as P
from app.tax.engine import TaxInputs, bracket_top, compute_return, marginal_rate, ordinary_tax, standard_deduction
from tests.conftest import make_demo_household


def _life_expectancy(q, age):
    s, total = 1.0, 0.0
    for x in range(age, len(q)):
        s_next = s * (1.0 - q[x])
        total += (s + s_next) / 2
        s = s_next
    return total


def test_the_mortality_table_is_ssas_and_its_life_expectancies_are_what_ssa_publishes():
    assert len(mortality.MALE_Q) == len(mortality.FEMALE_Q) == 120
    assert mortality.MALE_Q[65] == pytest.approx(0.016455) and mortality.FEMALE_Q[65] == pytest.approx(0.010188)
    assert _life_expectancy(mortality.MALE_Q, 65) == pytest.approx(18.12, abs=0.01)
    assert _life_expectancy(mortality.FEMALE_Q, 65) == pytest.approx(20.66, abs=0.01)
    assert (mortality.UNISEX_Q == pytest.approx(0.5 * (mortality.MALE_Q + mortality.FEMALE_Q))).all()


def test_death_years_follow_the_table():
    uniforms = np.random.default_rng(3).random((60_000, 2))
    deaths = mortality.death_years([65, 60], 40, uniforms)
    survive_15 = np.prod(1.0 - mortality.UNISEX_Q[65:80])
    assert (deaths[:, 0] >= 15).mean() == pytest.approx(survive_15, abs=0.01)
    assert deaths.shape == uniforms.shape


def test_the_survivor_flags_start_after_the_first_death_and_never_before_retirement():
    household = make_demo_household()  # 38 and 37, retiring at 62
    flags = survivor_flags(household, 4_000, 42, seed=9)
    assert flags.shape == (4_000, 42) and set(np.unique(flags)) <= {0.0, 1.0}
    assert (np.diff(flags, axis=1) >= 0).all()  # once single, single
    retire = household.goals.retirement_age - household.primary_age
    assert flags[:, : retire + 1].sum() == 0  # the year of the first death (moved to retirement at the earliest) is still joint
    ever = flags[:, -1].mean()
    both_alive = np.prod(1.0 - mortality.UNISEX_Q[38:80]) * np.prod(1.0 - mortality.UNISEX_Q[37:79])
    assert ever == pytest.approx(1.0 - both_alive, abs=0.03)


# --- Single-filer tax ---------------------------------------------------------------------------------------


def test_the_single_tax_tables_by_hand():
    assert standard_deduction(0.0, 1.0) == 16_100 and standard_deduction(1.0, 1.0) == 16_100 + 2_050
    assert standard_deduction(2.0, 1.0) == 16_100 + 2_050  # one person: the second aged spouse is not there
    assert ordinary_tax(50_400.0, 1.0) == pytest.approx(0.10 * 12_400 + 0.12 * 38_000)
    assert marginal_rate(60_000.0, 1.0) == 0.22 and marginal_rate(60_000.0, 0.0) == 0.12
    assert bracket_top(P.TOP_OF_22, 1.0) == 105_700 and bracket_top(P.TOP_OF_22, 0.0) == P.TOP_OF_22
    assert bracket_top(P.TOP_OF_12, 1.0) == 50_400 and bracket_top(P.TOP_OF_24, 1.0) == 201_775


def test_a_survivor_pays_more_tax_on_the_same_income():
    income = dict(retirement_distributions=90_000, social_security=40_000, net_capital_gain=20_000, interest=3_000)
    joint = compute_return(TaxInputs(aged_spouses=1, **income))
    single = compute_return(TaxInputs(aged_spouses=1, single=True, **income))
    assert single.grand_total > joint.grand_total
    assert single.standard_deduction == 16_100 + 2_050
    # Social Security tiers are lower for a single filer: more of the benefit is taxed
    assert single.taxable_social_security >= joint.taxable_social_security
    # Illinois: one exemption instead of two
    assert joint.il_exemptions - single.il_exemptions == pytest.approx(P.IL_EXEMPTION_PER_PERSON)


# --- The kernel -----------------------------------------------------------------------------------------------


def _retired_household():
    h = make_demo_household()
    people = [p.model_copy(update={"age": p.age + 27, "wages": 0.0, "pretax_401k": 0.0}) for p in h.people]
    goals = h.goals.model_copy(update={"retirement_age": 60, "home_purchase_in_years": None, "college_starts_in_years": None})
    accounts = h.accounts.model_copy(update={"brokerage_value": 800_000, "brokerage_basis": 500_000, "pretax_balance": 900_000, "roth_balance": 100_000})
    return h.model_copy(update={"people": people, "goals": goals, "accounts": accounts, "children_ages": []})


def test_a_year_filed_single_uses_the_single_deduction_and_the_survivors_spending_and_benefit():
    household = _retired_household()
    inputs = build_inputs(household, deterministic=True)
    joint = run_detail(inputs, RIA_BASELINE).log
    inputs.wage_tax[:, :, 2] = 1.0  # single from the start
    single = run_detail(inputs, RIA_BASELINE).log
    t = 3
    assert joint["taxable_income"][t] == pytest.approx(joint["agi"][t] - standard_deduction(2.0, 0.0))
    assert single["taxable_income"][t] == pytest.approx(single["agi"][t] - standard_deduction(2.0, 1.0))
    ss = household.social_security.annual_benefit
    spending = household.goals.retirement_spending
    assert single["ss"][t] == pytest.approx(sim.SURVIVOR_SS_SHARE * ss)
    assert single["spend_need"][t] == pytest.approx(sim.SURVIVOR_SPENDING_SHARE * spending - sim.SURVIVOR_SS_SHARE * ss)


def test_the_survivor_option_changes_results_only_when_asked_and_the_horizon_can_run_to_ninety():
    household = make_demo_household()
    base = run_batch(build_inputs(household, n_paths=60, seed=4), [RIA_BASELINE])
    again = run_batch(build_inputs(household, n_paths=60, seed=4, options=ModelOptions(survivor=False)), [RIA_BASELINE])
    assert np.array_equal(base.wealth, again.wealth)
    assert np.allclose(base.wealth_at_80, base.wealth)  # at the default horizon the wealth at 80 is the wealth at the end
    survivor = run_batch(build_inputs(household, n_paths=60, seed=4, options=ModelOptions(survivor=True)), [RIA_BASELINE])
    assert not np.array_equal(survivor.wealth, base.wealth)
    ninety = run_batch(build_inputs(household, n_paths=60, seed=4, options=ModelOptions(survivor=True, horizon_age=90)), [RIA_BASELINE])
    assert ninety.wealth.shape == base.wealth.shape and np.isfinite(ninety.wealth).all()
    assert ninety.wealth_at_80.shape == base.wealth.shape and (ninety.wealth_at_80 > 0).all()
    assert not np.allclose(ninety.wealth_at_80, ninety.wealth)  # ten more years of returns, spending and tax
