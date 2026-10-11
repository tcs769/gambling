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


# --- The adaptive planner in the study (spec B5) -----------------------------------------------------


def test_the_household_row_carries_the_four_way_comparison_and_the_value_of_judgment():
    from app.study.household_study import household_row

    item = generate(seed=10, per_type=1)[0]
    plain = household_row(item, 0, 60, 60, 3.0)
    assert "judgment_median" not in plain  # without --adaptive-paths the study is exactly what it was
    row = household_row(item, 0, 60, 60, 3.0, adaptive_paths=8)
    for key in ("typical_advisor", "good_ria", "best_fixed", "adaptive"):
        for name in ("median", "ce", "p10", "taxes", "shortfall"):
            assert np.isfinite(row[f"fw_{key}_{name}"])
    years = row["years"]
    assert row["judgment_median"] == pytest.approx((row["fw_adaptive_median"] / row["fw_best_fixed_median"]) ** (1 / years) - 1)
    assert row["judgment_risk_adjusted"] == pytest.approx((row["fw_adaptive_ce"] / row["fw_best_fixed_ce"]) ** (1 / years) - 1)
    assert row["fw_adaptive_adv_median_vs_good_ria"] == pytest.approx((row["fw_adaptive_median"] / row["fw_good_ria_median"]) ** (1 / years) - 1)
    assert 0.0 <= row["departure_share"] <= 1.0 and set(f"departure_{n}" for n in ("conversion", "private_credit", "stock_share")) <= set(row)
    assert row["adaptive_paths"] == 8 and row["adaptive_seconds"] > 0
    assert all(row[k] == plain[k] for k in plain if isinstance(plain[k], str))  # the fixed-planner columns are the same households


def test_the_study_report_gains_the_adaptive_sections_and_can_resume_from_a_checkpoint(tmp_path):
    from app.study.household_study import run, summarize

    checkpoint = tmp_path / "partial.csv"
    full = run(per_type=1, n_eval=50, adaptive_paths=6, checkpoint=checkpoint)
    assert len(full) == 6 and full["judgment_median"].notna().all()
    text = summarize(full, 50, 3.0)
    assert "## The adaptive planner: four strategies, by type" in text and "## The value of judgment over time, by type" in text
    assert text.count("| Adaptive planner |") == 6 and "**All 6 households**" in text
    # a checkpoint holding the first three households is picked up and the rest are computed to the same answer
    full.head(3).to_csv(checkpoint, index=False)
    resumed = run(per_type=1, n_eval=50, adaptive_paths=6, checkpoint=checkpoint)
    import pandas as pd

    timing = ["adaptive_seconds"]  # wall-clock time is the one column that is not a function of the inputs
    pd.testing.assert_frame_equal(full.drop(columns=timing), resumed.drop(columns=timing), check_exact=False, rtol=1e-9)
    # a checkpoint from a run without the adaptive columns is not reused for an adaptive run
    plain_checkpoint = tmp_path / "plain.csv"
    run(per_type=1, n_eval=50).head(2).to_csv(plain_checkpoint, index=False)
    fresh = run(per_type=1, n_eval=50, adaptive_paths=6, checkpoint=plain_checkpoint)
    assert fresh["judgment_median"].notna().all() and len(fresh) == 6
    assert "adaptive_paths" not in summarize(run(per_type=1, n_eval=50), 50, 3.0)


def test_the_single_household_evaluation_is_consistent_and_writes_a_report():
    from app.study import adaptive_evaluation as ev

    result = ev.run(n_paths=40, rollouts=(), extra_seeds=(1,))
    fw = result.main
    assert set(fw.wealth) == {"typical_advisor", "good_ria", "best_fixed", "adaptive"} and all(len(w) == 40 for w in fw.wealth.values())
    j = fw.judgment
    assert j.plan_median == np.median(fw.wealth["adaptive"]) and j.baseline_median == np.median(fw.wealth["best_fixed"])
    assert fw.advantage("best_fixed", "typical_advisor").median > fw.advantage("good_ria", "typical_advisor").median - 0.05  # sanity: ordering is plausible
    assert set(result.decomposition) == {"tax timing only", "allocation only", "all six decisions"}
    labels = [row[0] for row in result.steps]
    assert labels[0] == "RIA baseline" and len(labels) == 7 and result.steps[0][3] == 0.0 and result.steps[0][4] == 0.0
    assert result.steps[-1][1] == pytest.approx(np.median(fw.wealth["best_fixed"]))  # the last step is the best fixed strategy itself
    assert len(result.by_futures) == 2 and result.by_futures[0][1] == fw.judgment
    text = ev.report(result)
    for needle in ("## The four strategies", "## Where the best fixed strategy's advantage over the good RIA comes from", "## What judgment over time adds", "### Where it comes from", "### Other futures", "Adaptive planner"):
        assert needle in text


def test_the_decision_quality_measurement_judges_choices_on_futures_the_search_never_used():
    from tests.test_adaptive import short_household
    from tests.test_sim import menu_policy

    from app.sim.simulate import build_inputs
    from app.study import decision_quality as dq

    household = short_household()
    inputs = build_inputs(household, n_paths=4, seed=5)
    policy = menu_policy("60|fill22_every|10|on|on|pretax|borrow")
    measurements = [
        dq.measure(dq.BY_NAME[name], inputs, policy, 4, 32, 0.25) for name in ("plain", "default")
    ]
    for m in measurements:
        assert m.gains.shape == (4, inputs.n_years) and np.all(np.isfinite(m.gains))
        assert 0.0 <= m.departures <= 1.0 and 0.0 <= m.harmful_share <= 1.0 and 0.0 <= m.helpful_share <= 1.0
        assert set(m.by_dimension) == {"conversion", "realize_gains", "goal_funding", "k401", "private_credit", "stock_share"}
        assert m.seconds_per_100_paths > 0
    text = dq.report(measurements, 4, 32, 0.25, "a strategy")
    assert text.count("\n| K=32") == 2 and "## Where the gains and losses come from" in text and "## Reading this" in text
    assert "shadow mode" in text and "re-scored on 32 fresh futures" in text and "applied to whole paths" not in text
    from app.study import metrics

    advantage = metrics.compare(np.array([1e6, 2e6, 3e6]), np.array([1e6, 1.9e6, 3e6]), 42)
    realized = [dq.Realized(dq.BY_NAME["plain"], advantage, 0.1, 3.0)]
    with_realized = dq.report(measurements, 4, 32, 0.25, "a strategy", realized, 4)
    assert "## The same designs applied to whole paths" in with_realized and "| 10.0% |" in with_realized
