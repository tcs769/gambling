"""Update 4, section 4: the maximum gap two ways (unconstrained and risk-matched), the study's own rules."""

from __future__ import annotations

import numpy as np
import pandas as pd
from app.planner.baseline import RIA_BASELINE
from app.planner.strategies import STYLES, menu
from app.sim.simulate import build_inputs, run_batch
from app.study import max_gap
from tests.conftest import make_demo_household


def test_the_full_menu_is_every_style_without_duplicates():
    full = max_gap.full_menu()
    assert len({s.key for s in full}) == len(full)
    union = {s.key for style in STYLES for s in menu(style=style)}
    assert {s.key for s in full} == union
    assert len(full) < sum(len(menu(style=style)) for style in STYLES)  # the equity-first menu is inside the liability-matched one


def test_the_two_picks_obey_their_rules_on_a_small_menu():
    household = make_demo_household()
    subset = [s for s in menu(style="liability_matched") if s.conversion in ("none", "fill22_every") and s.private_credit in (0.0, 0.15)
              and not s.direct_indexing and s.k401 == "pretax" and s.goal_funding == "sell"]
    picks = max_gap.picks(household, subset)
    futures = build_inputs(household, n_paths=max_gap.SEARCH_PATHS, seed=max_gap.SEED)
    batch = run_batch(futures, [s.policy() for s in subset] + [RIA_BASELINE])
    medians = np.median(batch.wealth[: len(subset)], axis=1)
    best = subset[int(np.argmax(medians))]
    assert picks["unconstrained"] == best  # the highest median of all of them
    matched = picks["risk_matched"]
    if matched is not None:
        i = subset.index(matched)
        assert np.mean(batch.unfunded[i] > 0) <= np.mean(batch.unfunded[-1] > 0) + 1e-12
        assert np.percentile(batch.wealth[i], 10) >= np.percentile(batch.wealth[-1], 10)
        assert medians[i] <= medians[subset.index(best)] + 1e-9


def test_measure_reports_both_advantages_and_the_risk_numbers():
    household = make_demo_household()
    strategy = menu(style="equity_first")[0]
    out = max_gap.measure(household, strategy)
    assert out["found"] and out["strategy"] == strategy.short_label()
    for key in ("median_vs_ria", "risk_adjusted_vs_ria", "median_vs_typical", "ruin", "ria_ruin", "p10", "ria_p10", "forced_sale"):
        assert np.isfinite(out[key])
    assert max_gap.measure(household, None) == {"found": False}


def test_the_summary_puts_the_rules_side_by_side():
    rows = []
    for rule, advantage in (("unconstrained", 0.025), ("risk_matched", 0.018)):
        rows.append({"type": "showcase", "household": "Tanaka", "rule": rule, "found": True, "strategy": "6-year reserve", "median_vs_ria": advantage,
                     "risk_adjusted_vs_ria": 0.006, "ruin": 0.02, "ria_ruin": 0.04, "p10": 400_000.0, "ria_p10": 280_000.0, "forced_sale": 0.02})
    rows.append({"type": "diversified", "household": "diversified-0", "rule": "risk_matched", "found": False})
    text = max_gap.summarize(pd.DataFrame(rows))
    assert "unconstrained" in text and "risk-matched" in text and "2.50%" in text and "1.80%" in text
    assert "No strategy met the risk-matched limits for 1 household(s): diversified-0" in text
