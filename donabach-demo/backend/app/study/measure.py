"""Measure one household: which strategy the planner picks and the advantage it delivers.

    python -m app.study.measure --label "Step 0: engine as shipped" --out ../reports/progress/step_00.json

The strategy is chosen by the same search the app runs (default: 400 futures, seed 2026). The
advantage is then measured twice:

* `in_sample`: on the futures the search used (what the app showed before spec A7).
* `held_out`: on futures the search never saw (a different seed, `n_eval` paths). This is the
  honest number: choosing the best of many strategies on the same futures it is scored on is
  optimistic by an amount that grows with the size of the menu.

Both are annualized growth-rate differences (see `app.study.metrics`). Nothing here is tuned.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from app.planner.baseline import RIA_BASELINE
from app.planner.search import RISK_AVERSION, search
from app.schemas import Household
from app.sim.simulate import build_inputs, run_batch
from app.study.metrics import Advantage, compare

EVAL_SEED_OFFSET = 1_000_003  # held-out futures use seed + this offset
DEFAULT_SEEDS = (2026, 2027, 2028, 2029, 2030)


def git_revision() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=Path(__file__).parent
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover - a source export without git
        return "unknown"


def default_baselines() -> dict:
    """The good RIA, and the typical advisor where the engine has one (it was added in step A9)."""
    baselines = {"good_ria": RIA_BASELINE}
    try:
        from app.planner.baseline import TYPICAL_ADVISOR
    except ImportError:  # an older revision being re-measured
        return baselines
    baselines["typical_advisor"] = TYPICAL_ADVISOR
    return baselines


def sample_household() -> Household:
    """The demo household (the spec's fictional household), identical to what the app builds."""
    from tests.conftest import make_demo_household

    return make_demo_household()


def _summary(adv: Advantage) -> dict[str, float]:
    return {k: [float(x) for x in v] if isinstance(v, tuple) else float(v) for k, v in asdict(adv).items()}


def measure(
    household: Household,
    seed: int = 2026,
    n_search: int = 400,
    n_eval: int = 2000,
    risk_aversion: float = RISK_AVERSION,
    baselines: dict | None = None,
) -> dict:
    """Search on `n_search` futures, then score the winner on held-out futures."""
    baselines = baselines if baselines is not None else default_baselines()
    years = household.horizon_years
    started = time.perf_counter()
    futures = build_inputs(household, n_paths=n_search, seed=seed)
    result = search(futures, risk_aversion=risk_aversion) if risk_aversion != RISK_AVERSION else search(futures)
    chosen = result.best.strategy
    policies = [chosen.policy(), *baselines.values()]

    in_batch = run_batch(futures, policies)
    in_sample = in_batch.wealth
    held = build_inputs(household, n_paths=n_eval, seed=seed + EVAL_SEED_OFFSET)
    held_batch = run_batch(held, policies)
    held_wealth = held_batch.wealth

    out = {
        "seed": seed,
        "years": years,
        "strategy": chosen.choices(),
        "strategy_label": chosen.short_label(),
        "risk_aversion": risk_aversion,
        "n_search": n_search,
        "n_eval": n_eval,
        "elapsed_seconds": time.perf_counter() - started,
        "baselines": {},
    }
    for i, name in enumerate(baselines, start=1):
        out["baselines"][name] = {
            "in_sample": _summary(compare(in_sample[0], in_sample[i], years, risk_aversion)),
            "held_out": _summary(compare(held_wealth[0], held_wealth[i], years, risk_aversion, with_range=True)),
            # share of futures in which the plan / the baseline could not fund spending or a goal
            "shortfall": {
                "plan": float(np.mean(held_batch.unfunded[0] > 0)),
                "baseline": float(np.mean(held_batch.unfunded[i] > 0)),
            },
        }
    return out


def measure_seeds(household: Household, seeds=DEFAULT_SEEDS, **kwargs) -> dict:
    """`measure` for several seeds: the first is the app's own (2026); the rest show how stable it is."""
    runs = [measure(household, seed=s, **kwargs) for s in seeds]
    names = list(runs[0]["baselines"])
    summary: dict = {"app_seed_run": runs[0], "runs": runs, "mean": {}, "choices_by_seed": []}
    for name in names:
        summary["mean"][name] = {
            kind: {
                key: float(np.mean([r["baselines"][name][kind][key] for r in runs]))
                for key in ("median", "risk_adjusted")
            }
            for kind in ("in_sample", "held_out")
        }
        summary["mean"][name]["shortfall"] = {
            who: float(np.mean([r["baselines"][name]["shortfall"][who] for r in runs])) for who in ("plan", "baseline")
        }
    summary["choices_by_seed"] = [(r["seed"], r["strategy_label"]) for r in runs]
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", required=True, help="name of this step in the progress table")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=len(DEFAULT_SEEDS))
    parser.add_argument("--n-eval", type=int, default=2000)
    args = parser.parse_args(argv)
    household = sample_household()
    result = measure_seeds(household, seeds=DEFAULT_SEEDS[: args.seeds], n_eval=args.n_eval)
    result["label"] = args.label
    result["git"] = git_revision()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    app = result["app_seed_run"]
    print(f"{args.label}  [{result['git']}]  horizon {app['years']} years")
    print(f"  recommendation (seed 2026): {app['strategy_label']}")
    for name, by_kind in app["baselines"].items():
        held = by_kind["held_out"]
        ins = by_kind["in_sample"]
        print(
            f"  vs {name}: held-out median {held['median'] * 100:.2f}%/yr, risk-adjusted {held['risk_adjusted'] * 100:.2f}%/yr "
            f"(in-sample {ins['median'] * 100:.2f}% / {ins['risk_adjusted'] * 100:.2f}%)"
        )
        mean = result["mean"][name]["held_out"]
        print(f"     mean over {len(result['runs'])} seeds, held-out: {mean['median'] * 100:.2f}% / {mean['risk_adjusted'] * 100:.2f}%")
    print("  choices by seed:", *[f"{s}: {label}" for s, label in result["choices_by_seed"]], sep="\n    ")


if __name__ == "__main__":
    sys.exit(main())
