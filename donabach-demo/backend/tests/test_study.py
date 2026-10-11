"""The household-type study (spec A10): the generators draw what they say they draw."""

from __future__ import annotations

import numpy as np
import pytest

from app.study import households as hh
from app.study.households import generate, projected_pretax_at_70


@pytest.fixture(scope="module")
def study():
    return generate(seed=10, per_type=12)


def of_type(study, key):
    return [s for s in study if s.type == key]


def test_six_types_with_the_same_number_of_households(study):
    assert list(hh.TYPES) == ["diversified", "concentrated", "big_gains", "early_retirement", "large_purchase", "high_earner"]
    assert len(study) == 6 * 12
    for key in hh.TYPES:
        assert len(of_type(study, key)) == 12
    assert [s.index for s in of_type(study, "big_gains")] == list(range(12))


def test_the_study_is_reproducible_from_its_seed_and_differs_across_seeds():
    a, b, c = generate(seed=4, per_type=3), generate(seed=4, per_type=3), generate(seed=5, per_type=3)
    assert [s.household for s in a] == [s.household for s in b]
    assert [s.household for s in a] != [s.household for s in c]


def test_every_household_is_valid_and_fictional(study):
    for s in study:
        h = s.household
        assert h.goals.retirement_age > h.primary_age and h.horizon_years >= 10
        assert all(p.name == "" for p in h.people)  # nobody is named: these are not real households
        assert h.accounts.brokerage_basis <= h.accounts.brokerage_value + 1e-6


def test_concentrated_households_hold_a_low_basis_stock_of_at_least_40_percent(study):
    for s in of_type(study, "concentrated"):
        a = s.household.accounts
        investable = s.household.liquid_wealth
        assert "single stock" in s.note
        share = float(s.note.split("single stock ")[1].split("%")[0]) / 100
        basis = float(s.note.split(" at ")[1].split("%")[0]) / 100
        assert share >= 0.40 - 1e-9 and share * investable <= a.brokerage_value + 1e-6
        assert basis <= 0.25 + 1e-9  # low basis
        assert a.brokerage_basis / a.brokerage_value < 0.45  # the whole account is mostly gain


def test_big_gains_households_have_a_brokerage_basis_under_40_percent(study):
    for s in of_type(study, "big_gains"):
        a = s.household.accounts
        assert a.brokerage_basis < 0.40 * a.brokerage_value and a.brokerage_value > 0.25 * s.household.liquid_wealth


def test_early_retirees_retire_young_with_years_before_social_security(study):
    for s in of_type(study, "early_retirement"):
        h = s.household
        assert 55 <= h.primary_age <= 58 and 56 <= h.goals.retirement_age <= 61
        assert h.social_security.start_age - h.goals.retirement_age >= 5  # several low-income years


def test_large_purchases_come_within_three_years_and_take_a_quarter_of_investable_assets(study):
    for s in of_type(study, "large_purchase"):
        h = s.household
        assert h.goals.home_purchase_in_years is not None and 1 <= h.goals.home_purchase_in_years <= 3
        assert h.goals.home_down_payment >= 0.25 * h.liquid_wealth - 1e-6


def test_high_earners_are_projected_at_three_million_or_more_of_pretax_at_70(study):
    for s in of_type(study, "high_earner"):
        assert s.household.total_wages >= 400_000
        assert projected_pretax_at_70(s.household) >= 3_000_000.0


def test_no_household_plans_to_spend_more_than_a_sustainable_withdrawal(study):
    from app.planner.baseline import RIA_BASELINE
    from app.sim.simulate import build_inputs, run_detail

    for s in study[::7]:
        h = s.household
        log = run_detail(build_inputs(h, deterministic=True), RIA_BASELINE).log
        t = h.goals.retirement_age - h.primary_age - 1
        wealth = log["pretax"][t] + log["roth"][t] + log["brokerage"][t] + log["bucket"][t]
        assert h.goals.retirement_spending <= hh.SUSTAINABLE_WITHDRAWAL_RATE * wealth * (1 + 1e-9)
    assert hh.SUSTAINABLE_WITHDRAWAL_RATE == pytest.approx(0.045)


def test_the_cap_only_ever_lowers_spending():
    rng = np.random.default_rng(0)
    for _ in range(10):
        raw = hh.diversified(rng).household
        capped = hh.cap_retirement_spending(raw)
        assert capped.goals.retirement_spending <= raw.goals.retirement_spending
        assert capped.accounts == raw.accounts and capped.people == raw.people
