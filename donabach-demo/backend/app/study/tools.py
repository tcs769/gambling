"""Update 4, section 7: the new planner tools, each measured on its own.

Social Security claiming age (7.4): the household's stated benefit is what it would draw from its stated start age. Claiming at another
age scales it by the statutory factor for a full retirement age of 67 (SSA: 70% at 62, 75% at 63, 80% at 64, 86.67% at 65, 93.33% at 66,
108% at 68, 116% at 69, 124% at 70). Donabach chooses the age (with the strategy, so the choice is coordinated with the conversions
and withdrawals); the advisors keep the stated age.

    python -m app.study.tools claiming
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


from app.planner.baseline import RIA_BASELINE
from app.planner.search import median_wealth, search
from app.planner.strategies import menu
from app.schemas import Household
from app.sim.simulate import ModelOptions, build_inputs, run_batch
from app.study.measure import sample_household
from app.study.metrics import compare

CLAIM_FACTOR = {62: 0.70, 63: 0.75, 64: 0.80, 65: 0.8667, 66: 0.9333, 67: 1.0, 68: 1.08, 69: 1.16, 70: 1.24}


def with_claim_age(household: Household, age: int) -> Household:
    ss = household.social_security
    benefit = ss.annual_benefit * CLAIM_FACTOR[age] / CLAIM_FACTOR[ss.start_age]
    return household.model_copy(update={"social_security": ss.model_copy(update={"annual_benefit": benefit, "start_age": age})})


def claiming_effect(household: Household, style: str = "equity_first", options: ModelOptions | None = None) -> list[dict]:
    """For each claiming age, the best strategy found on the search futures and its advantage over the good RIA (which keeps the
    stated age) on fresh futures. With `options.horizon_age` set, the run goes to that age and the advantage is read at 80 and at the
    end of the horizon (the choice is made on the wealth at the end of the horizon)."""
    options = options or ModelOptions()
    held_stated = build_inputs(household, n_paths=2_000, seed=2026 + 1_000_003, options=options)
    ria = run_batch(held_stated, [RIA_BASELINE])
    end_years = held_stated.n_years
    rows = []
    for age in sorted(CLAIM_FACTOR):
        h = with_claim_age(household, age)
        futures = build_inputs(h, n_paths=400, seed=2026, options=options)
        best = search(futures, strategies=menu(style=style), criterion=median_wealth).best
        held = build_inputs(h, n_paths=2_000, seed=2026 + 1_000_003, options=options)
        batch = run_batch(held, [best.strategy.policy()])
        c = compare(batch.wealth[0], ria.wealth[0], end_years, 3.0)
        c80 = compare(batch.wealth_at_80[0], ria.wealth_at_80[0], household.horizon_years, 3.0)
        rows.append({
            "age": age, "search_median": best.outcome.median, "median": c.median, "risk_adjusted": c.risk_adjusted,
            "median_at_80": c80.median, "risk_adjusted_at_80": c80.risk_adjusted, "plan": best.strategy.short_label(),
        })
    return rows


def main(argv: list[str]) -> None:
    if argv[:1] != ["claiming"]:
        raise SystemExit("usage: python -m app.study.tools claiming")
    tanaka = Household.model_validate(json.loads(Path("../fixtures/showcase.json").read_text())["household"])
    for name, hh in (("sample", sample_household()), ("tanaka", tanaka)):
        for label, options in (("to 80", ModelOptions()), ("to 90", ModelOptions(horizon_age=90))):
            rows = claiming_effect(hh, options=options)
            best = max(rows, key=lambda r: r["search_median"])
            print(f"{name}, run {label}: stated age {hh.social_security.start_age}; chosen on the search futures: {best['age']}")
            for r in rows:
                mark = " <- chosen" if r is best else ""
                print(f"  claim {r['age']}: at the end median adv {r['median']:.4%} ra {r['risk_adjusted']:.4%} | at 80 {r['median_at_80']:.4%} ra {r['risk_adjusted_at_80']:.4%}{mark}")
            stated = next(r for r in rows if r["age"] == hh.social_security.start_age)
            print(f"  gain from choosing the age: {best['median'] - stated['median']:+.4%} a year at the end of the run", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
