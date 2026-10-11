"""The sentences the adaptive plan shows: computed from the run's numbers, never causes the engine did not establish."""

from __future__ import annotations

import numpy as np

from app.api_models import AlternativeView
from app.planner import adaptive_plan as ap
from app.sim import adaptive as ad
from app.tax import params_2026 as P


def vec(conversion=P.TOP_OF_24, realize=0.0, borrow=0.0, roth=0.0, pc=0.15, stock=0.5):
    return np.array([conversion, realize, borrow, roth, pc, stock])


FACTS = {
    "market_return": 0.055, "wages": 250_000.0, "expected_wages": 250_000.0, "conversion": 0.0, "gains_realized": 0.0,
    "borrowed": 0.0, "pretax_balance": 1_000_000.0, "pretax_vs_fixed": 0.0, "wealth_vs_fixed": 0.0,
    "taxable_before_conversion": 300_000.0, "room_taxable": 0.0,
}


def alternative(label_vec, gap, goal_due=False, differs_in=("stock_share",)):
    return AlternativeView(action=ap.action_view(label_vec, goal_due), ce=1_000_000.0 - gap, ce_gap=gap, differs_in=list(differs_in))


def why(chosen, fixed, **kw):
    args = dict(
        facts=FACTS, goal_label=None, ce_gain=12_345.0, fresh_gain=9_876.0, alternatives=[], proposed=1, kept=1, confirm_k=64,
    )
    args.update(kw)
    departures = ap.differing(chosen, fixed)
    return ap._why(chosen, fixed, departures, args["facts"], args["goal_label"], args["ce_gain"], args["fresh_gain"], args["alternatives"], args["proposed"], args["kept"], args["confirm_k"])


def test_a_year_that_changes_nothing_says_so_and_what_the_search_proposed():
    same = vec()
    assert why(same, same, proposed=0, kept=0).startswith("No change from the fixed strategy: 50% stocks, fill 24% bracket, 15% private credit.")
    assert "Nothing the search tried beat it by a convincing margin." in why(same, same, proposed=0, kept=0)
    none_held = why(same, same, proposed=2, kept=0)
    assert "proposed 2 changes, but none of them held up when re-tested on 64 fresh futures" in none_held
    assert "proposed 1 change, but only 0" not in why(same, same, proposed=1, kept=0)  # one change is singular and "none of them"
    alt = [alternative(vec(stock=1.0), -51_000.0)]
    text = why(same, same, proposed=1, kept=0, alternatives=alt)
    assert "Closest alternative: 100% stocks" in text and "$51k more, but not convincingly" in text
    assert "scored about the same" in why(same, same, proposed=0, kept=0, alternatives=[alternative(vec(stock=0.6), 3.0)])


def test_a_departure_names_what_changed_and_gives_the_scores_not_a_cause():
    fixed, chosen = vec(conversion=0.0), vec(conversion=P.TOP_OF_22)
    facts = {**FACTS, "conversion": 60_000.0, "market_return": -0.25, "pretax_vs_fixed": -0.22, "room_taxable": 1.0, "taxable_before_conversion": 31_000.0}
    text = why(chosen, fixed, facts=facts, alternatives=[alternative(vec(conversion=P.TOP_OF_12), 4_000.0, differs_in=("conversion",))])
    assert text.startswith("Converted $60k to Roth, filling the 22% bracket.")
    assert "What the planner saw: the market fell 25% this year; the pre-tax balance is 22% below the fixed strategy's path; taxable income before the conversion was $31k, leaving room in the lower brackets." in text
    assert "The rollouts scored this $12k higher than the fixed strategy's action" in text
    assert "Re-tested on 64 fresh futures it still came out $9,876 ahead." in text
    assert "Closest alternative: 50% stocks, fill 12% bracket, 15% private credit, $4,000 less." in text
    assert "because" not in text.lower()  # the planner chose by the scores; facts are context, not causes


def test_every_decision_has_a_sentence_and_the_unusual_year_facts_are_only_mentioned_when_unusual():
    fixed = vec(conversion=0.0, realize=0.0, borrow=0.0, roth=0.0, pc=0.0, stock=0.5)
    cases = {
        "conversion": (vec(conversion=P.TOP_OF_24, pc=0.0), "Converted"),
        "realize_gains": (vec(conversion=0.0, realize=1.0, pc=0.0), "Realized"),
        "goal_funding": (vec(conversion=0.0, borrow=1.0, pc=0.0), "Borrowed"),
        "k401": (vec(conversion=0.0, roth=1.0, pc=0.0), "Roth side"),
        "private_credit": (vec(conversion=0.0, pc=0.10), "Private credit 10% (usual: 0%)"),
        "stock_share": (vec(conversion=0.0, pc=0.0, stock=0.8), "80% stocks (usual: 50%)"),
    }
    for name, (chosen, phrase) in cases.items():
        text = why(chosen, fixed, goal_label="home purchase", facts={**FACTS, "conversion": 50_000.0, "gains_realized": 20_000.0, "borrowed": 100_000.0})
        assert ap.differing(chosen, fixed) == [name] and phrase in text, (name, text)
    calm = why(vec(conversion=P.TOP_OF_24, pc=0.0), fixed, facts={**FACTS, "conversion": 50_000.0})
    assert "What the planner saw" not in calm  # a calm year has nothing unusual to report
    loss = why(vec(conversion=P.TOP_OF_24, pc=0.0), fixed, facts={**FACTS, "conversion": 50_000.0, "wages": 100_000.0})
    assert "income is 60% below normal" in loss


def test_action_labels_read_like_the_fixed_strategys_own_and_borrowing_shows_only_when_a_goal_is_due():
    assert ap.action_view(vec(), False).label == "50% stocks, fill 24% bracket, 15% private credit"
    assert ap.action_view(vec(conversion=0.0, pc=0.0, stock=0.7), False).label == "70% stocks, no conversion"
    assert ap.action_view(vec(borrow=1.0), True).label.endswith("borrow for the goal")
    assert ap.action_view(vec(borrow=0.0), True).label.endswith("sell for the goal")
    assert "borrow" not in ap.action_view(vec(borrow=1.0), False).label
    view = ap.action_view(vec(roth=1.0, realize=1.0), False)
    assert view.k401 == "roth" and view.realize_gains and "Roth 401(k)" in view.label and "realize gains at 0%" in view.label
    assert view.goal_funding is None and ap.action_view(vec(), True).goal_funding == "sell"
    assert ap.differing(vec(), vec(stock=0.6)) == ["stock_share"] and ap.differing(vec(), vec()) == []
    assert [n for n in ad.DIM_NAMES] == ["conversion", "realize_gains", "goal_funding", "k401", "private_credit", "stock_share"]


def test_money_is_written_the_way_the_screens_write_it():
    assert [ap._money(x) for x in (0, 950, 12_500, 1_250_000, 2_000_000, -60_000, -950)] == ["$0", "$950", "$12k", "$1.25M", "$2M", "-$60k", "-$950"]
