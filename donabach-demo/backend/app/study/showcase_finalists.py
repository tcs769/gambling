"""The full evaluation of the showcase search's best profiles: the planner's own search (direct indexing run after its transition tax), the
advantage over the standard advisor, which strategies the plan uses and why the others are not used, and the job-loss behaviour.

    python -m app.study.showcase_finalists full IN.jsonl OUT.jsonl TOP     (full plan for the TOP profiles of the quick scores in IN)
    python -m app.study.showcase_finalists detail IN.jsonl OUT.json N       (flip tests, risk-adjusted figures, job loss for the best N)
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import numpy as np

from app.planner.baseline import RIA_BASELINE
from app.planner.plan import EVAL_SEED_OFFSET, VALIDATION_PATHS, VALIDATION_SEED_OFFSET
import app.planner.search as search_module
from app.planner.search import FORCED_SALE_LIMIT, search_matched
from app.planner.strategies import Strategy, menu
from app.schemas import JobLoss
from app.sim.simulate import build_inputs, run_batch, run_detail
from app.study import metrics
from app.study.showcase_search import SEED, Profile, from_json, plausibility, to_json, transition

def _run_batch_allowing_none(inputs, policies, *a, **k):
    """The search asks for the direct-indexing strategies of its menu first; a menu without any (the non-direct-indexing half of this
    study) gives it an empty list, which the kernel cannot take: answer with an empty result."""
    if len(policies) == 0:
        z = np.zeros((0, inputs.n_paths))
        return run_batch.__globals__["BatchResult"](wealth=z, taxes_paid=z, pretax_owed=z, unfunded=z, forced_years=z)
    return run_batch(inputs, policies, *a, **k)


search_module.run_batch = _run_batch_allowing_none  # the harness's own search only; the kernel and its assumptions are untouched

JOB_LOSS = JobLoss(year=1, years=1, keep=0.0)
LM = menu(style="liability_matched")
MENU_OFF = [s for s in LM if not s.direct_indexing]
MENU_ON = [s for s in LM if s.direct_indexing]


def _inputs(h, n, offset, job_loss=None):
    kw = {"job_loss": job_loss} if job_loss else {}
    return build_inputs(h, n_paths=n, seed=SEED + offset, **kw)


def plan(p: Profile, job_loss=None) -> dict:
    """The planner's choice for the household (direct indexing after its transition tax) and how it scores on 2,000 futures it never saw."""
    h = p.household()
    hd, tax = transition(h)
    years = h.horizon_years
    found = {}
    for key, household, strategies in (("off", h, MENU_OFF), ("on", hd, MENU_ON)):
        if key == "on" and tax < 0:
            continue
        f = _inputs(household, 400, 0, job_loss)
        v = _inputs(household, VALIDATION_PATHS, VALIDATION_SEED_OFFSET, job_loss)
        found[key] = search_matched(f, v, strategies)[1]
    e_h = _inputs(h, 2000, EVAL_SEED_OFFSET, job_loss)
    e_d = _inputs(hd, 2000, EVAL_SEED_OFFSET, job_loss)
    b_off = run_batch(e_h, [found["off"].strategy.policy(), RIA_BASELINE])
    b_on = run_batch(e_d, [found["on"].strategy.policy()])
    advisor = b_off.wealth[1]
    options = [
        ("off", found["off"], b_off.wealth[0], float(np.mean(b_off.forced_years[0] > 0)), float(np.mean(b_off.unfunded[0] > 0))),
        ("on", found["on"], b_on.wealth[0], float(np.mean(b_on.forced_years[0] > 0)), float(np.mean(b_on.unfunded[0] > 0))),
    ]
    adv_ruin = float(np.mean(b_off.unfunded[1] > 0))

    def feasible(o):
        return o[3] <= max(FORCED_SALE_LIMIT, 0.0) + 0.006 and o[4] <= adv_ruin + 0.003  # the planner's limits, with the slack of 2,000 futures

    pool = [o for o in options if feasible(o)] or options[:1]
    best = max(pool, key=lambda o: float(np.median(o[2])))
    use_di = best[0] == "on"
    wealth = best[2]
    cmp = metrics.compare(wealth, advisor, years, 3.0, with_range=True)
    return {
        "profile": to_json(p), "strategy": best[1].strategy.key, "label": best[1].strategy.short_label(), "di": use_di, "transition_tax": tax,
        "median": float(np.median(wealth)), "advisor_median": float(np.median(advisor)),
        "advantage": cmp.median, "advantage_dollars": float(np.median(wealth) - np.median(advisor)),
        "advantage_range": list(cmp.median_range), "risk_adjusted": cmp.risk_adjusted, "risk_adjusted_range": list(cmp.risk_adjusted_range),
        "ruin": best[4], "advisor_ruin": adv_ruin, "forced_sale": best[3], "p10": float(np.percentile(wealth, 10)),
        "advisor_p10": float(np.percentile(advisor, 10)), "years": years,
        "median_without_di": float(np.median(b_off.wealth[0])), "median_with_di": float(np.median(b_on.wealth[0])),
        "feasible": bool(best[1].feasible),
    }


def usage(p: Profile, strategy: Strategy, use_di: bool, job_loss=None) -> list[tuple[str, bool]]:
    """The engine's strategies and whether the plan actually uses each, from the year-by-year log of the plan on the expected path."""
    h = p.household()
    hd, _ = transition(h)
    household = hd if use_di else h
    kw = {"job_loss": job_loss} if job_loss else {}
    log = run_detail(build_inputs(household, deterministic=True, **kw), strategy.policy()).log
    s = lambda k: float(np.sum(log[k]))  # noqa: E731
    return [
        ("Lower, flat fee", True),
        ("Asset location", True),
        ("Highest-cost lots first", True),
        ("Tax-aware withdrawal order", True),
        ("Gains realized in the 0% bracket", s("gain_harvest") > 1.0),
        ("Spending reserve with the rest in stocks", strategy.reserve_years > 0),
        ("Private credit", strategy.private_credit > 0),
        ("Roth conversions", s("conv") > 1.0),
        ("Stock-by-stock loss harvesting (direct indexing)", strategy.direct_indexing),
        ("Roth 401(k) contributions", s("k401_roth") > 1.0),
        ("Borrowing against the taxable account for goals", s("borrowed") > 1.0),
        ("Gifts of appreciated shares", s("gift_stock") > 1.0),
    ]


def flips(p: Profile, strategy: Strategy, use_di: bool) -> dict[str, dict]:
    """What switching each unused (or applicable) strategy on would do to median wealth at 80, on the same futures."""
    h = p.household()
    hd, tax = transition(h)
    years = h.horizon_years
    e_h = _inputs(h, 2000, EVAL_SEED_OFFSET)
    e_d = _inputs(hd, 2000, EVAL_SEED_OFFSET)

    def med(s: Strategy, di: bool) -> float:
        b = run_batch(e_d if di else e_h, [s.policy()])
        return float(np.median(b.wealth[0]))

    base = med(strategy, use_di)
    out: dict[str, dict] = {}

    def record(name: str, variants: list[tuple[Strategy, bool]]):
        best = max((med(s, di) for s, di in variants), default=base)
        out[name] = {"delta": best - base, "per_year": (best / base) ** (1 / years) - 1 if best > 0 and base > 0 else 0.0}

    if strategy.k401 == "pretax":
        record("Roth 401(k) contributions", [(dataclasses.replace(strategy, k401=k), use_di) for k in ("roth", "roth_low")])
    if strategy.goal_funding == "sell" and (h.goals.home_purchase_in_years is not None or h.goals.college_starts_in_years is not None):
        record("Borrowing against the taxable account for goals", [(dataclasses.replace(strategy, goal_funding="borrow"), use_di)])
    if strategy.private_credit == 0:
        record("Private credit", [(dataclasses.replace(strategy, private_credit=0.15), use_di)])
    if strategy.conversion == "none":
        record("Roth conversions", [(dataclasses.replace(strategy, conversion="fill22_every"), use_di)])
    if not strategy.direct_indexing:
        record("Stock-by-stock loss harvesting (direct indexing)", [(dataclasses.replace(strategy, direct_indexing=True), True)])
    else:
        out["_without_direct_indexing"] = {"delta": med(dataclasses.replace(strategy, direct_indexing=False), False) - base}
    return out


def job_loss_effect(p: Profile, strategy: Strategy, use_di: bool) -> dict:
    """Whether a job loss next year visibly changes the plan's moves: the Roth conversion in that year with the plan held."""
    h = p.household()
    hd, _ = transition(h)
    household = hd if use_di else h
    base = run_detail(build_inputs(household, deterministic=True), strategy.policy()).log
    lost = run_detail(build_inputs(household, deterministic=True, job_loss=JOB_LOSS), strategy.policy()).log
    age = int(base["age"][1])
    return {
        "age": age, "conversion_before": float(base["conv"][1]), "conversion_after": float(lost["conv"][1]),
        "visible": abs(float(lost["conv"][1]) - float(base["conv"][1])) >= 10_000.0,
        "zero_bracket_gains_at_that_age": float(lost["gain_harvest"][1]),
    }


def cmd_full(args: list[str]) -> None:
    src, out, top = Path(args[0]), Path(args[1]), int(args[2])
    rows = [json.loads(line) for line in src.read_text().splitlines() if line.strip()]
    rows.sort(key=lambda r: -r["rate"])
    done = {json.dumps(json.loads(line)["profile"], sort_keys=True) for line in out.read_text().splitlines()} if out.exists() else set()
    with out.open("a") as f:
        for i, r in enumerate(rows[:top]):
            if json.dumps(r["profile"], sort_keys=True) in done:
                continue
            try:
                result = plan(from_json(r["profile"]))
            except Exception as exc:
                print("skip", exc, file=sys.stderr)
                continue
            result["quick_rate"] = r["rate"]
            f.write(json.dumps(result) + "\n")
            f.flush()
            print(f"{i + 1}/{top}: {result['advantage']:.3%} (quick {r['rate']:.3%}) di={result['di']}", flush=True)


def cmd_detail(args: list[str]) -> None:
    src, out, n = Path(args[0]), Path(args[1]), int(args[2])
    rows = [json.loads(line) for line in src.read_text().splitlines() if line.strip()]
    rows.sort(key=lambda r: -r["advantage"])
    result = []
    for r in rows[:n]:
        p = from_json(r["profile"])
        strategy = next(s for s in LM if s.key == r["strategy"])
        used = usage(p, strategy, r["di"])
        r["usage"] = used
        r["flips"] = flips(p, strategy, r["di"])
        r["job_loss"] = job_loss_effect(p, strategy, r["di"])
        r["checks"] = {k: [ok, d, s] for k, (ok, d, s) in plausibility(p).items()}
        result.append(r)
        print(f"{len(result)}/{n} done: {r['advantage']:.3%} uses {sum(1 for _, u in used if u)}", flush=True)
    out.write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    {"full": cmd_full, "detail": cmd_detail}[sys.argv[1]](sys.argv[2:])
