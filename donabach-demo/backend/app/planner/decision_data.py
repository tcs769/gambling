"""Training data for the policy and value models (spec B7): what the rollout search decided, and why.

The year-by-year planner searches each year with rollouts, the same idea as AlphaZero's search producing the
targets its networks learn from. For every household-year decision this module records

* the **state**: the household's features as the plan started (`household_features`) and the state of the plan
  at this decision (`STATE_FEATURE_NAMES`: balances by account and asset class, basis, loss carryforward, loan,
  this year's income against normal, goals, recent market returns), in real 2026 dollars;
* the **chosen action**, and the action the continuation (best fixed strategy) would have taken;
* the **score of every candidate** the search fully scored (certainty-equivalent after-tax wealth at the horizon,
  from its rollouts);
* the **realized outcome**: the after-tax wealth that path actually reached at the horizon.

A household that cannot fund its own plan (its median after-tax wealth at the horizon is below the $50,000 floor of the
objective) has every candidate scored at the floor, so its scores carry no information: its rows are flagged
(`underfunded`, `ce_at_floor`) and `export_decisions(drop_underfunded=True)` leaves such households out.

Three tables come out (see `backend/models/README.md` for the column-by-column format): `households`
(one row per household), `decisions` (one row per household-year-path decision: state, chosen and continuation
action, outcome) and `candidates` (one row per candidate scored in a decision). A policy model learns
decisions -> chosen action; a value model learns (state, candidate action) -> score.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app.ml.interfaces import CONVERSION_BRACKETS, FEATURE_NAMES, STATE_FEATURE_NAMES, ActionChoice, household_features
from app.planner.search import search
from app.planner.strategies import Strategy
from app.schemas import Household
from app.sim import adaptive as ad
from app.sim.simulate import (
    HC_RMD_START,
    SP_GLIDE_DROP,
    SP_GLIDE_START,
    S_BB,
    S_BBASIS,
    S_BE,
    S_BP,
    S_CF,
    S_GB,
    S_LOAN,
    S_PB,
    S_PE,
    S_PP,
    S_RB,
    S_RE,
    S_RP,
    S_UNFUNDED,
    TV_AGE,
    TV_AGED,
    TV_EXPWAGE,
    TV_GOAL,
    TV_NEARN,
    TV_NEED,
    TV_RETIRED,
    TV_SS,
    Policy,
    SimInputs,
    _stock_share,
    build_inputs,
    run_batch,
)
from app.tax import params_2026 as P

NO_GOAL_YEARS = 99.0  # "years to next goal" when none is left: always paired with goal_amount_next_three_years == 0
EVAL_SEED_OFFSET = 1_000_003

ACTION_COLUMNS = ("stock_share", "conversion_bracket", "private_credit", "k401_roth", "goal_borrow", "realize_gains")
_BRACKET_OF_TOP = {0.0: 0, round(P.TOP_OF_12, 1): 12, round(P.TOP_OF_22, 1): 22, round(P.TOP_OF_24, 1): 24}
_DIM = {name: i for i, name in enumerate(ad.DIM_NAMES)}


def glide_offsets(policy: Policy, inputs: SimInputs) -> np.ndarray:
    """How far the strategy's glide path has taken the stock share below its menu value in each year.

    The planner's stock-share action is the share held this year, glide included; the exported action is the menu
    share (50 to 100%) the glide starts from, so a model sees the same six menu choices at every age."""
    row = policy.row(inputs.current_age)
    return np.array([1.0 - _stock_share(float(age), 1.0, row[SP_GLIDE_START], row[SP_GLIDE_DROP]) for age in inputs.ages])


def action_columns(vec: np.ndarray, glide_offset: float = 0.0) -> dict[str, float]:
    """A decision vector (`ad.DIM_NAMES` order) as the exported action columns.

    `glide_offset` is the year's `glide_offsets` entry: it turns the stock share held this year back into the menu
    share (the planner's stock-share candidates are menu shares less the glide, so this is exact)."""
    conv = float(vec[_DIM["conversion"]])
    return {
        "stock_share": round(float(vec[_DIM["stock_share"]]) + glide_offset, 6),
        "conversion_bracket": _BRACKET_OF_TOP[round(conv, 1)],
        "private_credit": float(vec[_DIM["private_credit"]]),
        "k401_roth": float(vec[_DIM["k401"]] > 0.5),
        "goal_borrow": float(vec[_DIM["goal_funding"]] > 0.5),
        "realize_gains": float(vec[_DIM["realize_gains"]] > 0.5),
    }


def action_choice(vec: np.ndarray, glide_offset: float = 0.0) -> ActionChoice:
    """A decision vector as the model-facing `ActionChoice`."""
    cols = action_columns(vec, glide_offset)
    assert cols["conversion_bracket"] in CONVERSION_BRACKETS
    return ActionChoice(
        stock_share=cols["stock_share"],
        conversion_bracket=int(cols["conversion_bracket"]),
        private_credit=cols["private_credit"],
        k401="roth" if cols["k401_roth"] else "pretax",
        goal_funding="borrow" if cols["goal_borrow"] else "sell",
        realize_gains=bool(cols["realize_gains"]),
    )


def _ratio(numerator: np.ndarray, denominator: np.ndarray, default: float = 0.0) -> np.ndarray:
    out = np.full(np.broadcast(numerator, denominator).shape, default, dtype=np.float64)
    np.divide(numerator, denominator, out=out, where=np.asarray(denominator) > 0)
    return out


def state_feature_array(inputs: SimInputs, states: np.ndarray) -> np.ndarray:
    """The state features of every decision: shape (paths, years, len(STATE_FEATURE_NAMES)), in that order.

    `states` is the state vector each decision was taken in (`AdaptiveResult.states`): after that year's returns,
    before the year's action. Everything is computed from it and from what the household could know by then.
    """
    n_paths, n_years = inputs.n_paths, inputs.n_years
    tv = inputs.tv
    t = np.arange(n_years)
    columns: dict[str, np.ndarray] = {}

    def per_year(values: np.ndarray) -> np.ndarray:
        return np.broadcast_to(values, (n_paths, n_years)).astype(np.float64)

    st = states
    pe, pb, pp = st[:, :, S_PE], st[:, :, S_PB], st[:, :, S_PP]
    re_, rb, rp = st[:, :, S_RE], st[:, :, S_RB], st[:, :, S_RP]
    be, basis, bb, bp, gb = st[:, :, S_BE], st[:, :, S_BBASIS], st[:, :, S_BB], st[:, :, S_BP], st[:, :, S_GB]
    total = pe + pb + pp + re_ + rb + rp + be + bb + bp + gb
    brokerage = be + bb + bp

    retired = tv[:, TV_RETIRED] > 0
    to_retire = np.zeros(n_years)
    for year in range(n_years):
        ahead = np.flatnonzero(retired[year:])
        to_retire[year] = 0.0 if retired[year] else (float(ahead[0]) if ahead.size else float(n_years - year))
    goal = tv[:, TV_GOAL]
    next_three = np.array([goal[y + 1 : y + 4].sum() for y in range(n_years)])
    to_goal = np.array([(np.flatnonzero(goal[y + 1 :] > 0)[0] + 1.0) if (goal[y + 1 :] > 0).any() else NO_GOAL_YEARS for y in range(n_years)])
    expected = tv[:, TV_EXPWAGE]
    wages = inputs.wages
    room = P.LIMIT_401K_EMPLOYEE * np.maximum(tv[:, TV_NEARN], 1.0)

    equity = inputs.rets[:, :, 0]
    growth = np.cumprod(1.0 + equity, axis=1)
    three_back = np.concatenate([np.ones((n_paths, 3)), growth], axis=1)[:, :n_years]  # growth three years earlier

    columns["age"] = per_year(tv[:, TV_AGE])
    columns["year_index"] = per_year(t)
    columns["years_remaining"] = per_year(n_years - 1 - t)
    columns["retired"] = per_year(retired.astype(np.float64))
    columns["years_to_retirement"] = per_year(to_retire)
    columns["aged_spouses"] = per_year(tv[:, TV_AGED])
    columns["rmds_required"] = per_year((tv[:, TV_AGE] >= inputs.hhc[HC_RMD_START]).astype(np.float64))
    columns["pretax_equity"], columns["pretax_bonds"], columns["pretax_private_credit"] = pe, pb, pp
    columns["roth_equity"], columns["roth_bonds"], columns["roth_private_credit"] = re_, rb, rp
    columns["brokerage_equity"], columns["brokerage_basis"] = be, basis
    columns["brokerage_bonds_and_cash"], columns["brokerage_private_credit"], columns["goal_bucket"] = bb, bp, gb
    columns["total_wealth"] = total
    columns["pretax_share"] = _ratio(pe + pb + pp, total)
    columns["roth_share"] = _ratio(re_ + rb + rp, total)
    columns["taxable_share"] = _ratio(brokerage + gb, total)
    columns["equity_share"] = _ratio(pe + re_ + be, total)
    columns["private_credit_share"] = _ratio(pp + rp + bp, total)
    columns["brokerage_unrealized_gain_share"] = _ratio(np.maximum(0.0, be - basis), be)
    columns["loss_carryforward"] = st[:, :, S_CF]
    columns["loan"] = st[:, :, S_LOAN]
    columns["loan_to_brokerage"] = _ratio(st[:, :, S_LOAN], brokerage)
    columns["unfunded_so_far"] = st[:, :, S_UNFUNDED]
    columns["wages_this_year"] = wages
    columns["wages_expected_this_year"] = per_year(expected)
    columns["wages_vs_expected"] = _ratio(wages, per_year(expected), default=1.0)
    columns["k401_contribution_room_used"] = _ratio(inputs.k401, per_year(room))
    columns["social_security_this_year"] = per_year(tv[:, TV_SS])
    columns["spending_need_from_portfolio"] = per_year(tv[:, TV_NEED])
    columns["goal_due_this_year"] = per_year((goal > 0).astype(np.float64))
    columns["goal_amount_this_year"] = per_year(goal)
    columns["goal_amount_next_three_years"] = per_year(next_three)
    columns["years_to_next_goal"] = per_year(to_goal)
    columns["equity_return_this_year"] = equity
    columns["bond_return_this_year"] = inputs.rets[:, :, 1]
    columns["equity_growth_last_three_years"] = growth / three_back - 1.0
    columns["equity_growth_since_start"] = growth - 1.0

    out = np.stack([columns[name] for name in STATE_FEATURE_NAMES], axis=2)
    assert np.all(np.isfinite(out))
    return out


@dataclass
class DecisionTables:
    households: pd.DataFrame
    decisions: pd.DataFrame
    candidates: pd.DataFrame

    def write(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.households.to_parquet(directory / "households.parquet", index=False)
        self.decisions.to_parquet(directory / "decisions.parquet", index=False)
        self.candidates.to_parquet(directory / "candidates.parquet", index=False)


def decision_tables(
    household: Household,
    household_id: int,
    strategy: Strategy,
    inputs: SimInputs,
    result: ad.AdaptiveResult,
    fixed_wealth: np.ndarray,
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """The three tables' rows for one household's adaptive run (`result` recorded with candidates and states)."""
    if result.cand_actions is None or result.states is None:
        raise ValueError("the run must be recorded with record_candidates=True and record_states=True")
    n_paths, n_years = inputs.n_paths, inputs.n_years
    features = state_feature_array(inputs, result.states)
    gamma = result.settings.risk_aversion
    offsets = glide_offsets(strategy.policy(), inputs)
    offset_of_row = np.tile(offsets, n_paths)

    static = household_features(household)
    floor = result.settings.floor
    household_row = {
        "household_id": household_id,
        **static,
        **{f"label_{k}": v for k, v in strategy.choices().items()},
        "n_paths": n_paths,
        "underfunded": bool(np.median(fixed_wealth) < floor),
    }

    paths = np.repeat(np.arange(n_paths), n_years)
    years = np.tile(np.arange(n_years), n_paths)
    flat = features.reshape(n_paths * n_years, -1)
    frame = pd.DataFrame(flat, columns=list(STATE_FEATURE_NAMES))
    ids = pd.DataFrame({"household_id": household_id, "path": paths, "year": years})

    chosen = result.chosen.reshape(-1, ad.ND)
    cont = result.continuation.reshape(-1, ad.ND)
    chosen_cols = pd.DataFrame([action_columns(v, o) for v, o in zip(chosen, offset_of_row, strict=True)]).add_prefix("chosen_")
    cont_cols = pd.DataFrame([action_columns(v, o) for v, o in zip(cont, offset_of_row, strict=True)]).add_prefix("continuation_")
    n_cand = result.n_candidates.reshape(-1)
    ce_chosen = result.ce_chosen.reshape(-1)
    ce_cont = result.ce_continuation.reshape(-1)
    realized = np.repeat(result.wealth, n_years)
    outcome = pd.DataFrame(
        {
            "departs": (chosen != cont).any(axis=1),
            "n_candidates": n_cand,
            "ce_chosen": ce_chosen,
            "ce_continuation": ce_cont,
            "ce_gain": ce_chosen / ce_cont - 1.0,
            "ce_at_floor": ce_cont <= floor * (1.0 + 1e-6),
            "changes_proposed": result.proposed.reshape(-1),
            "changes_confirmed": result.kept.reshape(-1),
            "realized_wealth_at_horizon": realized,
            "realized_wealth_fixed_strategy": np.repeat(fixed_wealth, n_years),
            "risk_aversion": gamma,
        }
    )
    decisions = pd.concat([ids, frame, chosen_cols, cont_cols, outcome], axis=1)

    rows = []
    for p in range(n_paths):
        for t in range(n_years):
            n = int(result.n_candidates[p, t])
            ce = result.cand_ce[p, t, :n]
            order = np.argsort(-ce, kind="stable")
            rank = np.empty(n, dtype=np.int64)
            rank[order] = np.arange(1, n + 1)
            chosen_vec = result.chosen[p, t]
            for c in range(n):
                vec = result.cand_actions[p, t, c]
                rows.append(
                    {
                        "household_id": household_id,
                        "path": p,
                        "year": t,
                        "candidate": c,
                        **action_columns(vec, offsets[t]),
                        "ce": float(ce[c]),
                        "ce_relative_to_continuation": float(ce[c] / ce[0] - 1.0),
                        "rank": int(rank[c]),
                        "is_chosen": bool(np.array_equal(vec, chosen_vec)),
                        "is_continuation": c == 0,
                    }
                )
    return household_row, decisions, pd.DataFrame(rows)


def export_decisions(
    households: list[Household],
    paths: int = 4,
    seed: int = 1,
    settings: ad.AdaptiveSettings | None = None,
    search_paths: int = 150,
    progress: bool = False,
    drop_underfunded: bool = False,
) -> DecisionTables:
    """Run the year-by-year planner on each household and collect the training tables.

    Each household is planned as the app plans it: the best fixed strategy is found on `search_paths` futures,
    and the adaptive planner then runs on `paths` fresh futures it has not seen, recording every candidate and the
    state of every decision. `seed` seeds the futures; the result is deterministic. Household ids count every household
    drawn, including any left out with `drop_underfunded`.
    """
    settings = settings or ad.AdaptiveSettings()
    household_rows, decision_frames, candidate_frames = [], [], []
    started = time.perf_counter()
    for i, household in enumerate(households):
        household_seed = seed * 1_000_003 + i
        strategy = search(build_inputs(household, n_paths=search_paths, seed=household_seed), risk_aversion=settings.risk_aversion).best.strategy
        evaluation = build_inputs(household, n_paths=paths, seed=household_seed + EVAL_SEED_OFFSET)
        result = ad.run_adaptive(evaluation, strategy.policy(), settings, record_candidates=True, record_states=True)
        fixed = run_batch(evaluation, [strategy.policy()]).wealth[0]
        row, decisions, candidates = decision_tables(household, i, strategy, evaluation, result, fixed)
        if drop_underfunded and row["underfunded"]:
            continue
        household_rows.append(row)
        decision_frames.append(decisions)
        candidate_frames.append(candidates)
        if progress and (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(households)} households ({(time.perf_counter() - started) / (i + 1):.1f}s each)", flush=True)
    return DecisionTables(
        households=pd.DataFrame(household_rows),
        decisions=pd.concat(decision_frames, ignore_index=True),
        candidates=pd.concat(candidate_frames, ignore_index=True),
    )


__all__ = [
    "ACTION_COLUMNS",
    "DecisionTables",
    "FEATURE_NAMES",
    "STATE_FEATURE_NAMES",
    "action_choice",
    "action_columns",
    "decision_tables",
    "export_decisions",
    "glide_offsets",
    "state_feature_array",
]
