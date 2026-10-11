"""B7: the rollout search's decisions as training data for the policy and value models."""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from tests.conftest import make_demo_household
from tests.test_adaptive import perturbed_after, short_household
from tests.test_sim import menu_policy

import export_training_data as export_mod
from app.ml.interfaces import FEATURE_NAMES, STATE_FEATURE_NAMES, CONVERSION_BRACKETS, ActionChoice
from app.planner import decision_data as dd
from app.planner.strategies import PRIVATE_CREDIT_SHARES, STOCK_SHARES
from app.sim import adaptive as ad
from app.sim.simulate import NSTATE, TV_GOAL, build_inputs, run_batch

FAST = ad.AdaptiveSettings(k=8)


def _run(household=None, paths=3, seed=7, **kwargs):
    household = household or short_household()
    inputs = build_inputs(household, n_paths=paths, seed=seed)
    policy = menu_policy("60|fill22_every|10|on|on|pretax|borrow")
    result = ad.run_adaptive(inputs, policy, FAST, record_candidates=True, record_states=True, **kwargs)
    return household, inputs, policy, result


# --- State features ---------------------------------------------------------------------------------


def test_the_state_features_are_complete_finite_and_in_the_documented_order():
    _, inputs, _, result = _run()
    features = dd.state_feature_array(inputs, result.states)
    assert features.shape == (inputs.n_paths, inputs.n_years, len(STATE_FEATURE_NAMES))
    assert np.all(np.isfinite(features))
    column = {name: features[:, :, i] for i, name in enumerate(STATE_FEATURE_NAMES)}
    ages = inputs.ages
    assert np.array_equal(column["age"][0], ages) and np.array_equal(column["year_index"][1], np.arange(inputs.n_years))
    assert np.array_equal(column["years_remaining"][0], inputs.n_years - 1 - np.arange(inputs.n_years))
    # the balance sheet is one whole: the three account shares add to one, the equity share is a share
    assert np.allclose(column["pretax_share"] + column["roth_share"] + column["taxable_share"], 1.0)
    assert column["equity_share"].min() >= 0 and column["equity_share"].max() <= 1.0 + 1e-9
    assert np.allclose(column["wages_vs_expected"] * column["wages_expected_this_year"], column["wages_this_year"], atol=1e-6) or (column["wages_expected_this_year"] == 0).any()
    # goals and markets come straight from the household's schedule and the path's returns
    goal = inputs.tv[:, TV_GOAL]
    assert np.array_equal(column["goal_amount_this_year"][0], goal) and np.array_equal(column["goal_due_this_year"][0], (goal > 0).astype(float))
    assert np.array_equal(column["equity_return_this_year"], inputs.rets[:, :, 0])
    assert np.allclose(column["equity_growth_since_start"][:, 0], inputs.rets[:, 0, 0])
    assert np.allclose(1 + column["equity_growth_since_start"][:, 3], np.prod(1 + inputs.rets[:, :4, 0], axis=1))
    assert np.allclose(1 + column["equity_growth_last_three_years"][:, 5], np.prod(1 + inputs.rets[:, 3:6, 0], axis=1))
    assert column["total_wealth"].min() > 0 and column["loan"].min() >= 0 and column["loss_carryforward"].min() >= 0


def test_a_year_with_a_goal_ahead_reports_how_far_away_it_is():
    household = make_demo_household()
    inputs = build_inputs(household, n_paths=2, seed=3)
    policy = menu_policy("60|none|0|off|off")
    result = ad.run_adaptive(inputs, policy, ad.AdaptiveSettings(k=2, force_continuation=True), record_states=True)
    column = {name: dd.state_feature_array(inputs, result.states)[:, :, i] for i, name in enumerate(STATE_FEATURE_NAMES)}
    assert column["years_to_next_goal"][0, 0] == 3.0  # the home purchase, three years out
    assert column["goal_amount_next_three_years"][0, 0] == pytest.approx(120_000.0)
    assert column["goal_due_this_year"][0, 3] == 1.0
    assert column["years_to_next_goal"][0, 4] == 6.0  # college starts in year 10
    assert column["years_to_next_goal"][0, 20] == dd.NO_GOAL_YEARS and column["goal_amount_next_three_years"][0, 20] == 0.0
    assert column["retired"][0, 0] == 0.0 and column["years_to_retirement"][0, 0] == 62 - 38


def test_the_state_features_never_see_the_future():
    """A decision's features depend on the path only up to that year, so a model cannot train on leaked futures."""
    _, inputs, _, result = _run(paths=3)
    year = 4
    other = perturbed_after(inputs, year)
    policy = menu_policy("60|fill22_every|10|on|on|pretax|borrow")
    other_result = ad.run_adaptive(other, policy, FAST, record_candidates=True, record_states=True)
    a = dd.state_feature_array(inputs, result.states)[:, : year + 1]
    b = dd.state_feature_array(other, other_result.states)[:, : year + 1]
    assert np.array_equal(a, b)
    assert not np.array_equal(dd.state_feature_array(inputs, result.states)[:, -1], dd.state_feature_array(other, other_result.states)[:, -1])


def test_recording_states_does_not_change_the_run():
    household = short_household()
    inputs = build_inputs(household, n_paths=3, seed=7)
    policy = menu_policy("60|fill22_every|10|on|on|pretax|borrow")
    plain = ad.run_adaptive(inputs, policy, FAST)
    recorded = ad.run_adaptive(inputs, policy, FAST, record_candidates=True, record_states=True)
    assert np.array_equal(plain.wealth, recorded.wealth) and np.array_equal(plain.chosen, recorded.chosen)
    assert plain.states is None and recorded.states.shape == (3, inputs.n_years, NSTATE)


# --- The tables -------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tables():
    household, inputs, policy, result = _run(paths=3, seed=9)
    from app.planner.strategies import Strategy

    strategy = Strategy.from_choices({"stock_share": "60", "conversion": "fill22_every", "private_credit": "10", "direct_indexing": "on", "goal_bonds": "on", "k401": "pretax", "goal_funding": "borrow"})
    fixed = run_batch(inputs, [policy]).wealth[0]
    row, decisions, candidates = dd.decision_tables(household, 5, strategy, inputs, result, fixed)
    return household, inputs, result, fixed, row, decisions, candidates


def test_one_decision_row_per_path_and_year_with_state_actions_and_outcome(tables):
    household, inputs, result, fixed, row, decisions, _ = tables
    assert len(decisions) == inputs.n_paths * inputs.n_years
    assert list(decisions.columns[:3]) == ["household_id", "path", "year"]
    assert list(decisions.columns[3 : 3 + len(STATE_FEATURE_NAMES)]) == list(STATE_FEATURE_NAMES)
    for prefix in ("chosen_", "continuation_"):
        assert [f"{prefix}{c}" for c in dd.ACTION_COLUMNS] == [c for c in decisions.columns if c.startswith(prefix)]
    assert (decisions["household_id"] == 5).all()
    # the realized outcome is the horizon wealth of that path, repeated down its rows, next to what the fixed strategy made
    for p in range(inputs.n_paths):
        rows = decisions[decisions["path"] == p]
        assert (rows["realized_wealth_at_horizon"] == result.wealth[p]).all() and (rows["realized_wealth_fixed_strategy"] == fixed[p]).all()
        assert list(rows["year"]) == list(range(inputs.n_years))
    # chosen actions are on the menu; departures are flagged exactly where chosen differs from the continuation
    assert set(decisions["chosen_stock_share"]) <= set(STOCK_SHARES)
    assert set(decisions["chosen_conversion_bracket"]) <= set(CONVERSION_BRACKETS)
    assert set(decisions["chosen_private_credit"]) <= set(PRIVATE_CREDIT_SHARES)
    differs = np.array([[decisions[f"chosen_{c}"].iloc[i] != decisions[f"continuation_{c}"].iloc[i] for c in dd.ACTION_COLUMNS] for i in range(len(decisions))]).any(axis=1)
    assert np.array_equal(differs, decisions["departs"].to_numpy())
    assert (decisions["ce_chosen"] >= decisions["ce_continuation"] - 1e-6).all()
    assert np.allclose(decisions["ce_gain"], decisions["ce_chosen"] / decisions["ce_continuation"] - 1)
    assert set(row) >= set(FEATURE_NAMES) and row["household_id"] == 5 and row["label_stock_share"] == "60"


def test_the_candidate_table_has_every_candidate_the_search_fully_scored(tables):
    _, inputs, result, _, _, decisions, candidates = tables
    assert len(candidates) == int(result.n_candidates.sum())
    grouped = candidates.groupby(["path", "year"])
    assert (grouped.size().to_numpy() == result.n_candidates.reshape(-1)).all()
    assert (grouped["is_continuation"].sum() == 1).all() and (grouped["is_chosen"].sum() == 1).all()
    first = candidates[candidates["is_continuation"]]
    assert (first["candidate"] == 0).all() and np.allclose(first["ce_relative_to_continuation"], 0.0)
    assert (candidates["ce"] > 0).all() and (candidates["rank"] >= 1).all()
    best = candidates[candidates["rank"] == 1]
    ce_max = grouped["ce"].max()
    assert np.allclose(best.set_index(["path", "year"])["ce"], ce_max)
    # the candidate flagged as chosen is the action in the decision table, with the score the decision table carries
    chosen = candidates[candidates["is_chosen"]].set_index(["path", "year"]).sort_index()
    wide = decisions.set_index(["path", "year"]).sort_index()
    for c in dd.ACTION_COLUMNS:
        assert (chosen[c].to_numpy() == wide[f"chosen_{c}"].to_numpy()).all()
    assert np.allclose(chosen["ce"].to_numpy(), wide["ce_chosen"].to_numpy())


def test_the_exported_stock_share_is_the_menu_share_whatever_the_age():
    """Late in life the share held is the menu share less the glide; the export puts back what the glide took off."""
    household = make_demo_household()
    inputs = build_inputs(household, n_paths=2, seed=3)
    policy = menu_policy("60|none|0|off|off")
    offsets = dd.glide_offsets(policy, inputs)
    assert offsets[0] == 0.0 and offsets[-1] == pytest.approx(0.25) and np.all(np.diff(offsets) >= 0)
    # at 70 and after the strategy holds 60% - 25% = 35%; the planner's "60%" candidate that year is that same 35%
    result = ad.run_adaptive(inputs, policy, ad.AdaptiveSettings(k=8), record_candidates=True)
    for t in (0, 25, 35, 41):
        held = [float(x) for x in np.unique(result.cand_actions[:, t, :, list(ad.DIM_NAMES).index("stock_share")]) if x > 0]
        menu_shares = {round(h + offsets[t], 6) for h in held}
        assert menu_shares <= set(STOCK_SHARES), (t, held)
    assert dd.action_columns(np.array([0, 0, 0, 0, 0.0, 0.35]), 0.25)["stock_share"] == 0.6


def test_actions_convert_between_the_kernel_vector_and_the_model_facing_type():
    vec = np.array([0.0, 1.0, 1.0, 1.0, 0.10, 0.70])
    cols = dd.action_columns(vec)
    assert cols == {"stock_share": 0.7, "conversion_bracket": 0, "private_credit": 0.1, "k401_roth": 1.0, "goal_borrow": 1.0, "realize_gains": 1.0}
    choice = dd.action_choice(vec)
    assert choice == ActionChoice(stock_share=0.7, conversion_bracket=0, private_credit=0.1, k401="roth", goal_funding="borrow", realize_gains=True)
    from app.tax import params_2026 as P

    for top, bracket in ((P.TOP_OF_12, 12), (P.TOP_OF_22, 22), (P.TOP_OF_24, 24)):
        assert dd.action_choice(np.array([top, 0, 0, 0, 0.0, 0.5])).conversion_bracket == bracket


def test_the_export_is_deterministic_and_the_tables_round_trip_through_parquet(tmp_path):
    a = export_mod.export_decision_data(k=2, paths_per_household=2, seed=4, out_dir=tmp_path / "a", rollouts=8)
    b = export_mod.export_decision_data(k=2, paths_per_household=2, seed=4, rollouts=8)
    for name in ("households", "decisions", "candidates"):
        pd.testing.assert_frame_equal(getattr(a, name), getattr(b, name))
        pd.testing.assert_frame_equal(getattr(a, name), pd.read_parquet(tmp_path / "a" / f"{name}.parquet"))
    assert sorted(a.decisions["household_id"].unique()) == [0, 1] and len(a.households) == 2
    n_years = int(a.decisions.groupby(["household_id", "path"]).size().iloc[0])
    assert len(a.decisions) == sum(2 * y for y in a.decisions.groupby("household_id")["year"].max() + 1) and n_years > 20
    c = export_mod.export_decision_data(k=2, paths_per_household=2, seed=5, rollouts=8)
    assert not a.decisions["realized_wealth_at_horizon"].equals(c.decisions["realized_wealth_at_horizon"])


def test_the_cli_writes_the_three_tables(tmp_path, capsys):
    export_mod.main(["--decisions", "--k", "1", "--decision-paths", "2", "--rollouts", "8", "--seed", "2", "--decisions-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "decisions.parquet" in out and "candidates.parquet" in out
    for name in ("households", "decisions", "candidates"):
        assert len(pd.read_parquet(tmp_path / f"{name}.parquet")) > 0


def test_the_export_refuses_a_run_that_did_not_record_what_it_needs():
    household = short_household()
    inputs = build_inputs(household, n_paths=2, seed=1)
    policy = menu_policy("60|none|0|off|off")
    bare = ad.run_adaptive(inputs, policy, FAST)
    from app.planner.strategies import Strategy

    strategy = Strategy.from_choices({"stock_share": "60", "conversion": "none", "private_credit": "0", "direct_indexing": "off", "goal_bonds": "off", "k401": "pretax", "goal_funding": "sell"})
    with pytest.raises(ValueError, match="record_candidates"):
        dd.decision_tables(household, 0, strategy, inputs, bare, np.zeros(2))
    assert dataclasses.is_dataclass(dd.DecisionTables)


def test_a_household_that_cannot_fund_its_plan_is_flagged_and_can_be_left_out():
    """With every candidate scored at the $50,000 floor its scores say nothing, so the tables say so."""
    from app.schemas import Goals

    broke = make_demo_household(goals=Goals(home_purchase_in_years=None, college_starts_in_years=None, retirement_age=62, retirement_spending=900_000))
    fine = short_household()
    kept = dd.export_decisions([fine, broke], paths=2, seed=3, settings=FAST)
    assert list(kept.households["underfunded"]) == [False, True]
    flags = kept.decisions.groupby("household_id")["ce_at_floor"].mean()
    assert flags[1] > 0.9 and flags[0] < 0.5  # nearly every decision of the broke household sits at the floor (not the first year or two)
    broke_scores = kept.candidates[(kept.candidates["household_id"] == 1) & (kept.candidates["year"] > 12)]
    assert broke_scores["ce"].median() <= 50_000 * (1 + 1e-6)  # the scores that remain tell the planner nothing
    dropped = dd.export_decisions([fine, broke], paths=2, seed=3, settings=FAST, drop_underfunded=True)
    assert list(dropped.households["household_id"]) == [0] and set(dropped.decisions["household_id"]) == {0}
    # the household that is left is exactly what it was with the other one present
    pd.testing.assert_frame_equal(
        dropped.decisions.reset_index(drop=True), kept.decisions[kept.decisions["household_id"] == 0].reset_index(drop=True)
    )
