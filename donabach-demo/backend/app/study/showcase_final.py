"""The showcase household, searched with feasibility as a hard constraint and three separate sets of futures.

    search futures   the quick scores and the climb (`showcase_search.QUICK_OFFSET`), and the planner's own search and validation futures
    finalist futures 2,000 futures (CHOOSE_OFFSET) on which each household's strategy is chosen among those the planner scored, and on which the
                     households are ranked and the finalists picked
    final futures    3,000 futures (FINAL_OFFSET) that nothing above has seen; every number reported comes from them

    python -m app.study.showcase_final choose IN OUT TOP     (the finalist stage: strategy choice, hard constraints, life changes)
    python -m app.study.showcase_final final IN OUT N        (the final futures for the best N that meet every constraint)
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import numpy as np

import app.study.showcase_finalists as SF
from app.planner.baseline import RIA_BASELINE
from app.planner.plan import VALIDATION_PATHS, VALIDATION_SEED_OFFSET
from app.planner.search import FORCED_SALE_LIMIT, search_matched
from app.planner.strategies import Strategy
from app.portal.engine_view import JOB_LOSS, RAISE
from app.schemas import Household
from app.sim.simulate import build_inputs, run_batch, run_detail
from app.study import metrics
from app.study.showcase_search import (
    ADVISOR_CUSHION, ADVISOR_MAX_RUIN, SEED, Profile, from_json, plausibility, to_json, transition,
)

CHOOSE_OFFSET, CHOOSE_PATHS = 5_000_011, 2_000
FINAL_OFFSET, FINAL_PATHS = 7_000_021, 3_000
MIN_CONVERSION_CHANGE = 20_000.0  # a Roth conversion shown in the moves that changes by at least this much, in dollars, is a clearly visible change
MIN_K401_CHANGE = 5_000.0  # likewise a change in the 401(k) contribution the plan asks for


def _futures(h: Household, n: int, offset: int, job_loss=None):
    kw = {"job_loss": job_loss} if job_loss else {}
    return build_inputs(h, n_paths=n, seed=SEED + offset, **kw)


def _stats(batch, i: int) -> dict:
    return {"median": float(np.median(batch.wealth[i])), "forced": float(np.mean(batch.forced_years[i] > 0)), "ruin": float(np.mean(batch.unfunded[i] > 0))}


def candidates(p: Profile) -> tuple[Household, Household, float, list[tuple[Strategy, bool]]]:
    """Every strategy the planner scored on its own futures, for the household as it is and (direct indexing) after selling its funds and paying the tax."""
    h = p.household()
    hd, tax = transition(h)
    out: list[tuple[Strategy, bool]] = []
    for di, household, menu in (("off", h, SF.MENU_OFF), ("on", hd, SF.MENU_ON)):
        if di == "on" and tax < 0:
            continue
        f = _futures(household, 400, 0)
        v = _futures(household, VALIDATION_PATHS, VALIDATION_SEED_OFFSET)
        result, choice = search_matched(f, v, menu)
        seen = {id(choice.strategy)}
        out.append((choice.strategy, di == "on"))
        for s in result.strategies:
            if id(s) not in seen:
                seen.add(id(s))
                out.append((s, di == "on"))
    return h, hd, tax, out


def choose(p: Profile) -> dict | None:
    """The strategy with the highest median wealth on the finalist futures among those that meet the hard limits there; None if none does."""
    h, hd, tax, cands = candidates(p)
    years = h.horizon_years
    e_h = _futures(h, CHOOSE_PATHS, CHOOSE_OFFSET)
    e_d = _futures(hd, CHOOSE_PATHS, CHOOSE_OFFSET)
    base = run_batch(e_h, [RIA_BASELINE])
    advisor = float(np.median(base.wealth[0]))
    advisor_ruin = float(np.mean(base.unfunded[0] > 0))
    spending = h.goals.retirement_spending
    funded = advisor >= ADVISOR_CUSHION * spending and advisor_ruin <= ADVISOR_MAX_RUIN
    rows = []
    for di, inputs in ((False, e_h), (True, e_d)):
        group = [s for s, d in cands if d == di]
        if not group:
            continue
        batch = run_batch(inputs, [s.policy() for s in group])
        rows += [(group[i], di, _stats(batch, i)) for i in range(len(group))]
    ok = [r for r in rows if r[2]["forced"] <= FORCED_SALE_LIMIT and r[2]["ruin"] <= advisor_ruin]
    if not ok or not funded:
        return {"profile": to_json(p), "eligible": False, "funded": funded, "advisor": advisor, "advisor_ruin": advisor_ruin, "n_candidates": len(rows), "n_ok": len(ok)}
    strategy, di, st = max(ok, key=lambda r: r[2]["median"])
    wealth = run_batch(e_d if di else e_h, [strategy.policy()]).wealth[0]
    cmp = metrics.compare(wealth, base.wealth[0], years, 3.0, with_range=True)
    return {
        "profile": to_json(p), "eligible": True, "funded": True, "strategy": strategy.key, "label": strategy.short_label(), "di": di, "transition_tax": tax,
        "choose": {**st, "advisor": advisor, "advisor_ruin": advisor_ruin, "advantage": cmp.median, "dollars": st["median"] - advisor, "risk_adjusted": cmp.risk_adjusted},
        "n_candidates": len(rows), "n_ok": len(ok), "years": years,
    }


def _strategy(row: dict) -> Strategy:
    return next(s for s in SF.LM if s.key == row["strategy"])


# --- the life changes -----------------------------------------------------------------------------------------------------------------


def _edit(h: Household, **goals) -> Household:
    data = h.model_dump()
    data["goals"].update(goals)
    return Household.model_validate(data)


def life_changes(h: Household) -> dict[str, tuple[str, Household, object]]:
    """The precomputed changes that could be on camera: (label, the household afterwards, the job-loss spell to run it under)."""
    out: dict[str, tuple[str, Household, object]] = {"job_loss": ("Income: job loss next year", h, JOB_LOSS)}
    data = h.model_dump()
    for person in data["people"]:
        person["wages"] = round(person["wages"] * RAISE, 2)
    out["raise"] = ("Income: a raise", Household.model_validate(data), None)
    earlier = max(h.primary_age + 3, h.goals.retirement_age - 3)
    if earlier < h.goals.retirement_age:
        out["retire_earlier"] = (f"Retirement age: {earlier}", _edit(h, retirement_age=earlier), None)
    g = h.goals
    if g.home_purchase_in_years is not None and g.home_purchase_in_years > 1:
        sooner = max(1, g.home_purchase_in_years - 2)
        out["home_sooner"] = (f"Home purchase: within {sooner} years", _edit(h, home_purchase_in_years=sooner), None)
    return out


def _moves(household: Household, strategy: Strategy, di: bool, job_loss) -> dict:
    """What 'This year's moves' show for a plan: this year's and next year's Roth conversion and the 401(k) contribution asked for."""
    hh = transition(household)[0] if di else household
    kw = {"job_loss": job_loss} if job_loss else {}
    log = run_detail(build_inputs(hh, deterministic=True, **kw), strategy.policy()).log
    return {
        "conversion_now": float(log["conv"][0]), "conversion_next": float(log["conv"][1]) if len(log["conv"]) > 1 else 0.0,
        "k401": float(log["k401"][0]), "age": int(log["age"][0]),
    }


def visible_changes(p: Profile, strategy: Strategy, di: bool) -> dict:
    """For each life change, the moves before and after with the plan held, and whether a move changes clearly (amounts, in dollars)."""
    h = p.household()
    before = _moves(h, strategy, di, None)
    out = {}
    for key, (label, edited, spell) in life_changes(h).items():
        after = _moves(edited, strategy, di, spell)
        deltas = {
            "conversion_now": after["conversion_now"] - before["conversion_now"],
            "conversion_next": after["conversion_next"] - before["conversion_next"],
            "k401": after["k401"] - before["k401"],
        }
        size = max(abs(deltas["conversion_now"]), abs(deltas["conversion_next"]), 0.0)
        visible = size >= MIN_CONVERSION_CHANGE or abs(deltas["k401"]) >= MIN_K401_CHANGE
        out[key] = {"label": label, "before": before, "after": after, "visible": bool(visible), "size": max(size, abs(deltas["k401"]))}
    return out


def best_change(changes: dict) -> tuple[str, dict] | None:
    seen = [(k, v) for k, v in changes.items() if v["visible"]]
    return max(seen, key=lambda kv: kv[1]["size"]) if seen else None


# --- the final futures ----------------------------------------------------------------------------------------------------------------


def final_numbers(p: Profile, strategy: Strategy, di: bool) -> dict:
    h = p.household()
    hd, tax = transition(h)
    years = h.horizon_years
    e_h = _futures(h, FINAL_PATHS, FINAL_OFFSET)
    base = run_batch(e_h, [RIA_BASELINE])
    batch = run_batch(_futures(hd, FINAL_PATHS, FINAL_OFFSET) if di else e_h, [strategy.policy()])
    wealth, advisor = batch.wealth[0], base.wealth[0]
    cmp = metrics.compare(wealth, advisor, years, 3.0, with_range=True)
    spending = h.goals.retirement_spending
    st, ad = _stats(batch, 0), _stats(base, 0)
    return {
        "median": st["median"], "advisor": ad["median"], "advantage": cmp.median, "advantage_range": list(cmp.median_range),
        "dollars": st["median"] - ad["median"], "risk_adjusted": cmp.risk_adjusted, "risk_adjusted_range": list(cmp.risk_adjusted_range),
        "ruin": st["ruin"], "advisor_ruin": ad["ruin"], "forced": st["forced"], "p10": float(np.percentile(wealth, 10)),
        "advisor_p10": float(np.percentile(advisor, 10)), "years": years,
        "constraints": {
            "forced_at_most_2pct": st["forced"] <= FORCED_SALE_LIMIT, "ruin_not_above_advisor": st["ruin"] <= ad["ruin"],
            "advisor_funds_household": ad["median"] >= ADVISOR_CUSHION * spending and ad["ruin"] <= ADVISOR_MAX_RUIN,
        },
    }


def final_flips(p: Profile, strategy: Strategy, di: bool) -> dict:
    """What each unused strategy would add (or cost) in median wealth at 80, on the final futures."""
    h = p.household()
    hd, _ = transition(h)
    years = h.horizon_years
    e_h, e_d = _futures(h, FINAL_PATHS, FINAL_OFFSET), _futures(hd, FINAL_PATHS, FINAL_OFFSET)

    def med(s: Strategy, with_di: bool) -> float:
        return float(np.median(run_batch(e_d if with_di else e_h, [s.policy()]).wealth[0]))

    base = med(strategy, di)
    out: dict[str, float] = {}

    def record(name: str, variants: list[tuple[Strategy, bool]]):
        out[name] = max(med(s, d) for s, d in variants) - base

    if strategy.k401 == "pretax":
        record("Roth 401(k) contributions", [(dataclasses.replace(strategy, k401=k), di) for k in ("roth", "roth_low")])
    if strategy.goal_funding == "sell" and (h.goals.home_purchase_in_years is not None or h.goals.college_starts_in_years is not None):
        record("Borrowing against the taxable account for goals", [(dataclasses.replace(strategy, goal_funding="borrow"), di)])
    if strategy.private_credit == 0:
        record("Private credit", [(dataclasses.replace(strategy, private_credit=0.15), di)])
    if strategy.conversion == "none":
        record("Roth conversions", [(dataclasses.replace(strategy, conversion="fill22_every"), di)])
    if not strategy.direct_indexing:
        record("Stock-by-stock loss harvesting (direct indexing)", [(dataclasses.replace(strategy, direct_indexing=True), True)])
    del years
    return out


# --- command line ---------------------------------------------------------------------------------------------------------------------


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def cmd_choose(args: list[str]) -> None:
    src, out, top = Path(args[0]), Path(args[1]), int(args[2])
    shard, shards = (int(args[3]), int(args[4])) if len(args) > 4 else (0, 1)
    rows = _read(src)
    rows.sort(key=lambda r: -r["rate"])
    rows = rows[:top][shard::shards]
    top = len(rows)
    done = {json.dumps(r["profile"], sort_keys=True) for r in _read(out)} if out.exists() else set()
    with out.open("a") as f:
        for i, r in enumerate(rows):
            if json.dumps(r["profile"], sort_keys=True) in done:
                continue
            p = from_json(r["profile"])
            try:
                res = choose(p)
                if res and res["eligible"]:
                    res["usage"] = SF.usage(p, _strategy(res), res["di"])
                    res["changes"] = visible_changes(p, _strategy(res), res["di"])
                    res["best_change"] = (best_change(res["changes"]) or (None,))[0]
                    res["plausibility"] = {k: [v[0], v[1], v[2]] for k, v in plausibility(p).items()}
            except Exception as exc:
                print("skip", repr(exc)[:200], file=sys.stderr)
                continue
            res["quick_rate"] = r["rate"]
            f.write(json.dumps(res) + "\n")
            f.flush()
            tag = "ineligible" if not res["eligible"] else f"{res['choose']['advantage']:.3%} change={res['best_change']}"
            print(f"{i + 1}/{top}: {tag}", flush=True)


def cmd_final(args: list[str]) -> None:
    src, out, n = Path(args[0]), Path(args[1]), int(args[2])
    rows = [r for r in _read(src) if r["eligible"] and r["best_change"]]
    rows.sort(key=lambda r: -r["choose"]["advantage"])
    result = []
    for r in rows[:n]:
        p = from_json(r["profile"])
        s = _strategy(r)
        r["final"] = final_numbers(p, s, r["di"])
        r["final_flips"] = final_flips(p, s, r["di"])
        result.append(r)
        print(f"final {len(result)}/{min(n, len(rows))}: choose {r['choose']['advantage']:.3%} -> final {r['final']['advantage']:.3%}", flush=True)
    out.write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    {"choose": cmd_choose, "final": cmd_final}[sys.argv[1]](sys.argv[2:])
