"""M5: ML contracts, adapters (never fake a prediction), feature vector, training-data export."""

from __future__ import annotations

import math
import pickle

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from tests import stubs
from tests.conftest import make_demo_household

import export_training_data as export_mod
from app.ml import adapters
from app.ml.adapters import ModelContractError, NotConnected, load_forecaster, load_recommender
from app.ml.interfaces import (
    FEATURE_NAMES,
    ChoiceRecommendation,
    Factor,
    IncomeForecast,
    IncomeForecaster,
    Recommendation,
    StrategyRecommender,
    feature_vector,
    household_features,
)
from app.planner import guided
from app.planner.strategies import CHOICE_OPTIONS, CHOICES, Strategy, menu
from app.schemas import Accounts, Goals

# --- Features ------------------------------------------------------------------------------


def test_feature_vector_is_named_ordered_and_finite():
    f = household_features(make_demo_household())
    assert tuple(f) == FEATURE_NAMES and len(set(FEATURE_NAMES)) == len(FEATURE_NAMES)
    assert all(math.isfinite(v) for v in f.values())
    assert feature_vector(make_demo_household()) == list(f.values())


def test_feature_values_for_the_demo_household():
    f = household_features(make_demo_household())
    assert f["age"] == 38 and f["spouse_age"] == 37 and f["n_earners"] == 2
    assert f["wages_total"] == 250_000 and f["wages_secondary_share"] == pytest.approx(0.44)
    assert f["liquid_wealth"] == 620_000 and f["liquid_wealth_to_wages"] == pytest.approx(2.48)
    assert f["pretax_share"] + f["roth_share"] + f["taxable_share"] == pytest.approx(1.0)
    assert f["years_to_retirement"] == 24 and f["years_to_home"] == 3 and f["years_to_college"] == 10
    assert f["years_to_social_security"] == 29 and f["n_children"] == 1 and f["youngest_child_age"] == 8
    assert f["brokerage_unrealized_gain_share"] == pytest.approx(40_000 / 150_000)
    assert f["agi_now"] == pytest.approx(206_300) and f["marginal_federal_rate_now"] == 0.22
    assert f["pretax_deferrals"] == 49_000


def test_features_for_a_household_with_no_goals_children_or_spouse():
    hh = make_demo_household(
        people=[make_demo_household().people[0]],
        children_ages=[],
        goals=Goals(home_purchase_in_years=None, college_starts_in_years=None),
        snapshot=None,
    )
    f = household_features(hh)
    assert f["has_home_goal"] == 0 and f["years_to_home"] == 99 and f["home_down_payment_to_wages"] == 0
    assert f["has_college_goal"] == 0 and f["n_children"] == 0 and f["youngest_child_age"] == -1
    assert f["spouse_age"] == 0 and f["n_earners"] == 1 and f["wages_secondary_share"] == 0
    assert all(math.isfinite(v) for v in f.values())


def test_features_survive_zero_balances():
    hh = make_demo_household(
        accounts=Accounts(brokerage_value=0, brokerage_basis=0, pretax_balance=0, roth_balance=0, cash=0)
    )
    f = household_features(hh)
    assert f["brokerage_unrealized_gain_share"] == 0 and all(math.isfinite(v) for v in f.values())


# --- Contracts -----------------------------------------------------------------------------


def _entry(choice="stock_share", option="90", probability=0.5, **kw):
    return ChoiceRecommendation(choice=choice, option=option, probability=probability, **kw)


def test_recommendation_requires_exactly_one_entry_per_choice():
    full = [_entry(c, CHOICE_OPTIONS[c][0]) for c in CHOICES]
    assert Recommendation(choices=full).option("conversion") == "none"
    with pytest.raises(ValidationError):
        Recommendation(choices=full[:-1])
    with pytest.raises(ValidationError):
        Recommendation(choices=full + [full[0]])


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(choice="stock_share", option="95"),
        dict(choice="conversion", option="fill99"),
        dict(choice="risk_tolerance", option="high"),
        dict(choice="stock_share", option="90", probability=1.2),
        dict(choice="stock_share", option="90", probability=-0.1),
    ],
)
def test_invalid_choices_are_rejected(kwargs):
    kwargs.setdefault("probability", 0.5)
    with pytest.raises(ValidationError):
        ChoiceRecommendation(**kwargs)


def test_distribution_options_are_checked_too():
    from app.ml.interfaces import OptionProbability

    with pytest.raises(ValidationError):
        _entry(distribution=[OptionProbability(option="95", probability=1.0)])


def test_factor_bounds():
    Factor(feature="age", direction="up", weight=0.0)
    for bad in (dict(direction="sideways", weight=0.5), dict(direction="up", weight=1.5)):
        with pytest.raises(ValidationError):
            Factor(feature="age", **bad)


def test_income_forecast_validation():
    ok = dict(ages=[38, 39], p10=[1, 1], p25=[2, 2], p50=[3, 3], p75=[4, 4], p90=[5, 5])
    assert IncomeForecast(**ok).ages == [38, 39]
    with pytest.raises(ValidationError):
        IncomeForecast(**{**ok, "p10": [1]})  # misaligned
    with pytest.raises(ValidationError):
        IncomeForecast(**{**ok, "p25": [9, 9]})  # p25 above p50


def test_stub_models_satisfy_the_protocols():
    assert isinstance(stubs.StubRecommender(), StrategyRecommender)
    assert isinstance(stubs.StubForecaster(), IncomeForecaster)
    assert not isinstance(stubs.NoMethod(), StrategyRecommender)


# --- Adapters ------------------------------------------------------------------------------


def _drop(directory, name, obj):
    path = directory / name
    path.write_bytes(pickle.dumps(obj))
    return path


def test_no_model_files_means_not_connected_never_a_fallback(tmp_path):
    rec = load_recommender(tmp_path)
    fore = load_forecaster(tmp_path)
    for result, model in ((rec, "recommender"), (fore, "forecaster")):
        assert isinstance(result, NotConnected)
        assert result.connected is False and result.model == model
        assert "No model file" in result.reason and str(tmp_path) in result.expected_path
        assert not hasattr(result, "recommend") and not hasattr(result, "forecast")


def test_the_repo_ships_without_models():
    assert isinstance(load_recommender(), NotConnected)
    assert isinstance(load_forecaster(), NotConnected)


def test_a_dropped_in_recommender_is_loaded_and_validated(tmp_path):
    _drop(tmp_path, "recommender.pkl", stubs.StubRecommender())
    model = load_recommender(tmp_path)
    assert not isinstance(model, NotConnected)
    rec = model.recommend(make_demo_household())
    assert isinstance(rec, Recommendation) and rec.option("stock_share") == "90"


def test_dict_outputs_are_validated_into_the_contract(tmp_path):
    _drop(tmp_path, "recommender.pkl", stubs.DictRecommender())
    rec = load_recommender(tmp_path).recommend(make_demo_household())
    assert isinstance(rec, Recommendation) and rec.top_factors[0].direction == "down"


def test_contract_violations_raise(tmp_path):
    _drop(tmp_path, "recommender.pkl", stubs.BadOptionRecommender())
    with pytest.raises(ModelContractError, match="invalid Recommendation"):
        load_recommender(tmp_path).recommend(make_demo_household())


def test_a_dropped_in_forecaster_is_loaded_and_checked(tmp_path):
    _drop(tmp_path, "forecaster.pkl", stubs.StubForecaster())
    forecast = load_forecaster(tmp_path).forecast(make_demo_household(), 5)
    assert len(forecast.ages) == 5 and forecast.p50[0] == 250_000


def test_forecaster_must_return_the_requested_number_of_years(tmp_path):
    _drop(tmp_path, "forecaster.pkl", stubs.WrongLengthForecaster())
    with pytest.raises(ModelContractError, match="requested"):
        load_forecaster(tmp_path).forecast(make_demo_household(), 5)


def test_objects_without_the_method_and_corrupt_files_are_not_connected(tmp_path):
    _drop(tmp_path, "recommender.pkl", stubs.NoMethod())
    result = load_recommender(tmp_path)
    assert isinstance(result, NotConnected) and "no recommend() method" in result.reason
    (tmp_path / "forecaster.pkl").write_bytes(b"this is not a pickle")
    broken = load_forecaster(tmp_path)
    assert isinstance(broken, NotConnected) and "Could not load" in broken.reason


def test_models_are_reloaded_when_the_file_changes(tmp_path):
    _drop(tmp_path, "recommender.pkl", stubs.StubRecommender())
    first = load_recommender(tmp_path)
    assert load_recommender(tmp_path) is first  # cached while the file is unchanged
    picks = {"stock_share": "70", "conversion": "fill22_low", "private_credit": "0",
             "direct_indexing": "off", "goal_bonds": "on", "k401": "pretax"}
    _drop(tmp_path, "recommender.pkl", stubs.StubRecommender(picks))
    assert load_recommender(tmp_path).recommend(make_demo_household()).option("stock_share") == "70"
    (tmp_path / "recommender.pkl").unlink()
    assert isinstance(load_recommender(tmp_path), NotConnected)


def test_models_directory_can_be_overridden(tmp_path, monkeypatch):
    _drop(tmp_path, "forecaster.pkl", stubs.StubForecaster())
    monkeypatch.setenv(adapters.MODELS_DIR_ENV, str(tmp_path))
    assert not isinstance(load_forecaster(), NotConnected)
    assert adapters.models_dir() == tmp_path


# --- Guided planning -----------------------------------------------------------------------


def _rec(**picks):
    return stubs.StubRecommender(picks or None, with_distribution=True).recommend(make_demo_household())


def test_the_recommendation_maps_to_a_strategy():
    assert guided.strategy_from_recommendation(_rec()) == Strategy(0.90, "none", 0.10, True, False)


def test_distance_counts_option_steps():
    a = Strategy(0.90, "none", 0.10, True, False)
    assert guided.distance(a, a) == 0
    assert guided.distance(a, Strategy(0.80, "none", 0.10, True, False)) == 1
    assert guided.distance(a, Strategy(0.70, "none", 0.10, True, False)) == 2
    assert guided.distance(a, Strategy(0.90, "fill22_low", 0.10, True, False)) == 3
    assert guided.distance(a, Strategy(1.00, "none", 0.05, True, True)) == 3
    assert guided.distance(a, Strategy(0.90, "none", 0.0, True, False)) == 2  # 10% -> 5% -> 0%


def test_candidates_are_the_top_strategy_and_its_five_nearest_alternatives():
    top, alternatives = guided.candidates(_rec())
    assert top == Strategy(0.90, "none", 0.10, True, False)
    assert len(alternatives) == 5 and len(set(alternatives)) == 5 and top not in alternatives
    assert all(guided.distance(top, s) == 1 for s in alternatives)  # six neighbors exist; five are taken


def test_ties_between_equally_near_alternatives_follow_the_models_probabilities():
    rec = stubs.StubRecommender(with_distribution=True).recommend(make_demo_household())
    # Make 'goal bonds on' very likely and 'direct indexing off' very unlikely.
    for entry in rec.choices:
        if entry.choice == "goal_bonds":
            for d in entry.distribution:
                d.probability = 0.9 if d.option == "on" else 0.1
        if entry.choice == "direct_indexing":
            for d in entry.distribution:
                d.probability = 0.99 if d.option == "on" else 0.01
    top, alternatives = guided.candidates(rec)
    assert Strategy(0.90, "none", 0.10, True, True) in alternatives
    assert Strategy(0.90, "none", 0.10, False, False) not in alternatives  # the least likely neighbor


def test_joint_probability_multiplies_the_per_choice_probabilities():
    rec = _rec()
    top = guided.strategy_from_recommendation(rec)
    assert guided.joint_probability(rec, top) == pytest.approx(0.6 ** len(CHOICES))
    others = len(CHOICE_OPTIONS["stock_share"]) - 1  # the stub spreads the remaining 0.4 over the other options
    assert guided.joint_probability(rec, Strategy(0.80, "none", 0.10, True, False)) == pytest.approx(
        0.6 ** (len(CHOICES) - 1) * (0.4 / others)
    )


# --- Training-data export ------------------------------------------------------------------


def test_sampled_households_respect_the_ranges():
    rng = np.random.default_rng(0)
    for _ in range(300):
        h = export_mod.sample_household(rng)
        assert 25 <= h.primary_age <= 60 and h.goals.retirement_age > h.primary_age
        assert 60_000 * 0.999 <= h.total_wages <= 600_000 * 1.001
        assert h.accounts.brokerage_basis <= h.accounts.brokerage_value + 1e-6
        assert all(a <= 17 for a in h.children_ages)
        assert all(math.isfinite(v) for v in household_features(h).values())


def test_ranges_are_configurable():
    rng = np.random.default_rng(1)
    ranges = export_mod.SamplingRanges(age=(40, 45), household_income=(100_000.0, 110_000.0), two_earner_probability=0.0)
    for _ in range(50):
        h = export_mod.sample_household(rng, ranges)
        assert 40 <= h.primary_age <= 45 and len(h.people) == 1
        assert 100_000 * 0.999 <= h.total_wages <= 110_000 * 1.001


def test_export_writes_features_labels_and_scores_to_parquet(tmp_path):
    out = tmp_path / "nested" / "training.parquet"
    frame = export_mod.export(k=6, paths=40, seed=3, out=out)
    assert len(frame) == 6
    assert list(frame.columns[: len(FEATURE_NAMES)]) == list(FEATURE_NAMES)
    labels = [f"label_{c}" for c in CHOICES]
    assert set(labels) <= set(frame.columns)
    for choice in CHOICES:
        assert set(frame[f"label_{choice}"]) <= set(CHOICE_OPTIONS[choice])
    assert (frame["best_score"] >= 0).all() and (frame["score_gap_to_second"] >= 0).all()
    assert (frame["n_paths"] == 40).all()
    again = pd.read_parquet(out)
    pd.testing.assert_frame_equal(frame, again)


def test_export_labels_are_the_searchs_best_strategy():
    from app.planner.search import search
    from app.sim.simulate import build_inputs

    frame = export_mod.export(k=1, paths=40, seed=11)
    rng = np.random.default_rng(11)
    household = export_mod.sample_household(rng)
    futures = build_inputs(household, n_paths=40, seed=int(rng.integers(1, 2**31 - 1)))
    best = search(futures).best.strategy
    assert {c: frame.loc[0, f"label_{c}"] for c in CHOICES} == best.choices()


def test_export_is_reproducible():
    a = export_mod.export(k=3, paths=30, seed=5)
    b = export_mod.export(k=3, paths=30, seed=5)
    pd.testing.assert_frame_equal(a, b)


def test_every_menu_strategy_is_a_valid_label():
    assert {Strategy.from_choices(s.choices()) for s in menu()} == set(menu())
