"""The two reports built for the tax-lot change and the showcase choice: what lots change, and the short list of households."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from app import showcase
from app.planner.strategies import Strategy
from app.study import showcase_pick as pick
from app.study import tax_lots

# --- What tax lots change -----------------------------------------------------------------------------------


def test_the_stages_differ_only_in_the_lot_rules():
    assert [(s.donabach, s.baseline, s.short_term) for s in tax_lots.STAGES] == [
        ("average", "average", False), ("hifo", "average", False), ("hifo", "fifo", False), ("hifo", "fifo", True),
    ]
    original = Strategy.policy
    with tax_lots.lot_rules("fifo", False):
        policy = Strategy(0.8, "none", 0.0, False, False).policy()
        assert policy.lot_method == "fifo" and not policy.short_term_ordinary
    assert Strategy.policy is original  # restored
    assert Strategy(0.8, "none", 0.0, False, False).policy().lot_method == "hifo"


def test_the_lot_report_has_a_row_per_stage_and_the_first_is_what_the_engine_gave_before_lots():
    results = tax_lots.run(seeds=(2026,), n_eval=200, styles=("equity_first",))
    text = tax_lots.render(results, seeds=(2026,))
    stages = results["equity_first"]
    assert len(stages) == 4
    for stage, _ in stages:
        assert stage.name in text
    first = stages[0][1]["app_seed_run"]["baselines"]["good_ria"]["held_out"]
    last = stages[-1][1]["app_seed_run"]["baselines"]["good_ria"]["held_out"]
    # lots help this household a little: Donabach's tax bill falls with highest-cost-first and the advisor's rises with first-in-first-out
    assert last["median"] > first["median"] - 0.001
    assert "All four steps together move the median advantage" in text


def test_comparing_two_studies_counts_the_households_whose_plan_changed(tmp_path):
    before = pd.DataFrame(
        {
            "type": ["diversified", "diversified", "big_gains"], "index": [0, 1, 0], "strategy": ["a", "b", "c"],
            "adv_median_vs_good_ria": [0.010, 0.012, 0.014], "adv_risk_adjusted_vs_good_ria": [0.002, 0.003, 0.004],
        }
    )
    after = before.assign(strategy=["a", "x", "c"], adv_median_vs_good_ria=[0.011, 0.013, 0.018])
    before.to_csv(tmp_path / "before.csv", index=False)
    after.to_csv(tmp_path / "after.csv", index=False)
    text = tax_lots.compare_studies(tmp_path / "before.csv", tmp_path / "after.csv")
    assert "| Diversified, modest unrealized gains | +1.10% | +1.20% | +0.10 points" in text
    assert "1 of 2" in text and "| **All 300 households** |" in text and "1 of 3" in text


# --- The short list -----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def study():
    frame = pick.load_study(pick.DEFAULT_CSV)
    return frame, pick.reconstruct(frame)


def test_the_study_s_households_can_be_rebuilt_from_the_generator(study):
    frame, built = study
    assert len(frame) == 300 and len(built) == 300
    row = frame.iloc[7]
    assert built[(row["type"], int(row["index"]))].household.total_wages == pytest.approx(row["wages"], abs=1.0)


def test_the_screens_use_only_the_household_and_never_a_result_of_the_plan(study):
    frame, built = study
    passed, removed = pick.screen(frame, built)
    assert 0 < len(passed) < len(frame) and len(removed) == len(pick.SCREENS)
    for _, row in passed.iterrows():
        h = built[(row["type"], int(row["index"]))].household
        assert 35 <= h.primary_age <= 60 and 90_000 <= h.total_wages <= 750_000 and row["basis_ratio"] >= 0.15
        assert h.accounts.brokerage_value <= 0.70 * h.liquid_wealth and row["plan_shortfall"] <= 0.05
    # a household that fails a screen is removed whatever its advantage
    worst = frame.sort_values("adv_median_vs_good_ria", ascending=False).head(60)
    assert set(map(tuple, worst[["type", "index"]].values)) - set(map(tuple, passed[["type", "index"]].values))


def test_the_listed_households_are_re_measured_ranked_named_and_installable(study, tmp_path):
    frame, built = study
    passed, _ = pick.screen(frame, built)
    candidates = pick.remeasure(passed, built, count=3)
    assert [c.rank for c in candidates] == [1, 2, 3]
    in_the_study = [c.row["adv_median_vs_good_ria"] for c in candidates]
    assert in_the_study == sorted(in_the_study, reverse=True)  # ranked as the study ranked them
    assert in_the_study[0] == passed["adv_median_vs_good_ria"].max()
    assert candidates[0].fixture.household.people[0].name.endswith(candidates[0].name)  # the earners have names
    text = pick.render(frame, passed, [("a screen", 1)], candidates)
    assert "| 1 | The" in text and "How the list was made" in text and "2,000 fresh futures" in text
    paths = pick.write_fixtures(candidates, tmp_path)
    fixture = showcase.load_fixture(paths[0])
    assert fixture.household == candidates[0].fixture.household and fixture.tagline and fixture.id == candidates[0].name.lower()
    assert json.loads(paths[0].read_text())["name"].startswith("The ")
    showcase.reset()


def test_the_list_keeps_the_study_s_order_whatever_the_fresh_futures_say(study, monkeypatch):
    # The fresh futures are for scoring, never for choosing: a list ranked on them would be picked on the number it shows.
    frame, built = study
    passed, _ = pick.screen(frame, built)
    fresh = iter([0.010, 0.030, 0.020])  # the fresh futures would rank the three the other way round
    real = showcase.analyze

    def analyze(prepared, enabled=None):
        out = real(prepared, enabled)
        return out.model_copy(update={"advantage": out.advantage.model_copy(update={"median_rate": next(fresh)})})

    monkeypatch.setattr(showcase, "analyze", analyze)
    candidates = pick.remeasure(passed, built, count=3)
    assert [c.analysis.advantage.median_rate for c in candidates] == [0.010, 0.030, 0.020]  # not re-sorted
    in_the_study = [c.row["adv_median_vs_good_ria"] for c in candidates]
    assert in_the_study == sorted(in_the_study, reverse=True) and [c.rank for c in candidates] == [1, 2, 3]
    assert [c.name for c in candidates] == [n[0] for n in pick.NAMES[:3]]
    showcase.reset()
