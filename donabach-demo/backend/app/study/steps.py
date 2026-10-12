"""Update 4: what each change did to the answer. The same households (the sample household and the showcase household) are planned and
measured under named sets of options of the engine, with the plan searched again under each set (the planner chooses with whatever the
engine now says) and measured on fresh futures: the held-out design of every other study.

    python -m app.study.steps survivor
    python -m app.study.steps flat_valuation
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from app.planner.baseline import RIA_BASELINE, TYPICAL_ADVISOR
from app.planner.search import search
from app.planner.strategies import menu
from app.schemas import Household
from app.sim.simulate import ModelOptions, build_inputs, run_batch
from app.study.measure import sample_household
from app.study.metrics import compare

VARIANTS: dict[str, list[tuple[str, ModelOptions]]] = {
    "survivor": [
        ("joint to 80 (before)", ModelOptions()),
        ("survivor, wealth at 80", ModelOptions(survivor=True)),
        ("survivor, to 90: wealth at 80", ModelOptions(survivor=True, horizon_age=90)),
        ("survivor, to 90: wealth at 90", ModelOptions(survivor=True, horizon_age=90)),
    ],
    "flat_valuation": [("flat 15% (before)", ModelOptions(valuation="flat")), ("tax engine over five years", ModelOptions())],
}


def households() -> list[tuple[str, Household]]:
    tanaka = Household.model_validate(json.loads(Path("../fixtures/showcase.json").read_text())["household"])
    return [("sample", sample_household()), ("tanaka", tanaka)]


def measure(name: str, household: Household, label: str, options: ModelOptions, at: str = "end", style: str = "equity_first") -> dict:
    futures = build_inputs(household, n_paths=400, seed=2026, options=options)
    chosen = search(futures, strategies=menu(style=style)).best.strategy
    held = build_inputs(household, n_paths=2_000, seed=2026 + 1_000_003, options=options)
    batch = run_batch(held, [chosen.policy(), RIA_BASELINE, TYPICAL_ADVISOR])
    wealth = batch.wealth_at_80 if label.endswith("wealth at 80") or "to 90: wealth at 80" in label else batch.wealth
    years = (80 if wealth is batch.wealth_at_80 else (options.horizon_age or 80)) - household.primary_age
    ria = compare(wealth[0], wealth[1], years, 3.0)
    typical = compare(wealth[0], wealth[2], years, 3.0)
    return {
        "household": name, "variant": label, "plan": chosen.short_label(),
        "median_vs_ria": ria.median, "ra_vs_ria": ria.risk_adjusted, "median_vs_typical": typical.median, "ra_vs_typical": typical.risk_adjusted,
        "plan_median": float(np.median(wealth[0])), "ria_median": float(np.median(wealth[1])), "ruin": float(np.mean(batch.unfunded[0] > 0)),
    }


def main(argv: list[str]) -> None:
    if not argv or argv[0] not in VARIANTS:
        raise SystemExit(f"usage: python -m app.study.steps {{{'|'.join(VARIANTS)}}}")
    for name, household in households():
        for label, options in VARIANTS[argv[0]]:
            r = measure(name, household, label, options)
            print(
                f"{name:7s} {label:34s} vs RIA {r['median_vs_ria']:.3%} (risk-adj {r['ra_vs_ria']:.3%}) | vs typical {r['median_vs_typical']:.3%} "
                f"(risk-adj {r['ra_vs_typical']:.3%}) | medians plan {r['plan_median']:,.0f} RIA {r['ria_median']:,.0f} | ruin {r['ruin']:.3%} | {r['plan']}",
                flush=True,
            )


if __name__ == "__main__":
    main(sys.argv[1:])
