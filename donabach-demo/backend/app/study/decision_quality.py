"""How good are the year-by-year planner's decisions, judged on futures it never saw?

    python -m app.study.decision_quality --paths 80 --out ../reports/adaptive_decision_quality.md

The planner picks each year's action by scoring candidates on a few dozen simulated futures. The best of
a dozen candidates scored on the same few dozen futures is partly luck, and the objective (certainty-equivalent
wealth with risk aversion 3) is dominated by the few futures in which money runs out, which a few dozen rollouts
rarely contain. So whether a search design actually improves on the fixed strategy has to be measured on
independent futures, not on the ones the choice was made on.

Method. Every path follows the fixed strategy (the planner's *shadow* mode: it searches and records what it would
choose, but its choice is not applied, so every design is judged on the same states). Then, in every year, the
candidates it scored and the action it chose are re-scored on `reference_k` fresh futures from a stream it never used,
importance-sampled toward bad markets so the tail is represented. The decision's value is the reference's relative
gain in certainty-equivalent wealth of the chosen action over the fixed strategy's action.

Nothing here is tuned toward a result: the designs are the ones that were considered and all are reported.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.planner.search import search
from app.sim import adaptive as ad
from app.sim.simulate import build_inputs
from app.study.measure import sample_household

SEED = 2026
EVAL_SEED_OFFSET = 1_000_003


@dataclass(frozen=True)
class Design:
    name: str
    description: str
    settings: dict


DESIGNS = (
    Design("plain", "K=32, change if the best candidate is 1 standard error better (the search as first built)", dict(k=32, z_min=1.0, tilt=0.0, confirm_k=0)),
    Design("plain_z0", "K=32, take the best-scoring candidate whatever the margin", dict(k=32, z_min=0.0, tilt=0.0, confirm_k=0)),
    Design("plain_z2", "K=32, change only if 2 standard errors better", dict(k=32, z_min=2.0, tilt=0.0, confirm_k=0)),
    Design("tilted", "K=32, importance-sampled toward bad markets, 1 standard error", dict(k=32, z_min=1.0, tilt=0.25, confirm_k=0)),
    Design("confirmed_z0", "K=32 tilted, take the best, keep a change only if it wins 1.645 SE on 64 fresh futures", dict(k=32, z_min=0.0, tilt=0.25, confirm_k=64, confirm_z=1.645)),
    Design("default", "K=32 tilted, 1 SE screen, keep a change only if it wins 1.645 SE on 64 fresh futures (the planner's default)", dict(k=32, z_min=1.0, tilt=0.25, confirm_k=64, confirm_z=1.645)),
    Design("k128", "K=128 tilted, 1 standard error, no confirmation", dict(k=128, z_min=1.0, tilt=0.25, confirm_k=0)),
    Design("k256", "K=256 tilted, 1 standard error, no confirmation", dict(k=256, z_min=1.0, tilt=0.25, confirm_k=0)),
)
BY_NAME = {d.name: d for d in DESIGNS}
TAX_TIMING = ("conversion", "realize_gains", "goal_funding", "k401")
ALLOCATION = ("private_credit", "stock_share")


@dataclass
class Measurement:
    design: Design
    decisions: int
    departures: float
    mean_gain_bp: float
    mean_gain_departing_bp: float
    harmful_share: float
    helpful_share: float
    by_dimension: dict[str, tuple[int, float]]  # dimension -> (decisions changing it, mean gain bp of those decisions)
    seconds_per_100_paths: float
    gains: np.ndarray  # (paths, years) relative gain of the chosen action over the continuation, on the reference futures


def measure(design: Design, inputs, policy, paths: int, reference_k: int, reference_tilt: float) -> Measurement:
    settings = ad.AdaptiveSettings(shadow=True, **design.settings)
    started = time.perf_counter()
    result = ad.run_adaptive(inputs, policy, settings, record_candidates=True)
    seconds = time.perf_counter() - started
    utility = ad.probe_candidates(inputs, policy, result, reference_k=reference_k, reference_tilt=reference_tilt)
    n_paths, n_years = result.n_candidates.shape
    gains = np.zeros((n_paths, n_years))
    for p in range(n_paths):
        for t in range(n_years):
            n = int(result.n_candidates[p, t])
            ce = ad.certainty_equivalent_of_utility(utility[p, t, : n + 1], settings.risk_aversion)
            gains[p, t] = ce[n] / ce[0] - 1.0
    departs = (result.chosen != result.continuation).any(axis=2)
    by_dimension = {}
    for d, name in enumerate(ad.DIM_NAMES):
        changed = result.chosen[:, :, d] != result.continuation[:, :, d]
        by_dimension[name] = (int(changed.sum()), float(gains[changed].mean() * 1e4) if changed.any() else 0.0)
    g = gains[departs]
    return Measurement(
        design=design,
        decisions=n_paths * n_years,
        departures=float(departs.mean()),
        mean_gain_bp=float(gains.mean() * 1e4),
        mean_gain_departing_bp=float(g.mean() * 1e4) if g.size else 0.0,
        harmful_share=float((g < -1e-4).mean()) if g.size else 0.0,
        helpful_share=float((g > 1e-4).mean()) if g.size else 0.0,
        by_dimension=by_dimension,
        seconds_per_100_paths=seconds / n_paths * 100.0,
        gains=gains,
    )


def run(paths: int = 80, reference_k: int = 1_024, reference_tilt: float = 0.25, designs=DESIGNS, progress: bool = False) -> list[Measurement]:
    household = sample_household()
    strategy = search(build_inputs(household, n_paths=400, seed=SEED)).best.strategy
    policy = strategy.policy()
    inputs = build_inputs(household, n_paths=paths, seed=SEED + EVAL_SEED_OFFSET)
    out = []
    for design in designs:
        m = measure(design, inputs, policy, paths, reference_k, reference_tilt)
        out.append(m)
        if progress:
            print(f"  {design.name:14s} departures {m.departures:5.1%}  mean gain {m.mean_gain_bp:+6.1f} bp  harmful {m.harmful_share:4.0%}  helpful {m.helpful_share:4.0%}", flush=True)
    return out


def report(measurements: list[Measurement], paths: int, reference_k: int, reference_tilt: float, strategy_label: str) -> str:
    lines = [
        "# Year-by-year planner: decision quality on independent futures",
        "",
        "Generated by `python -m app.study.decision_quality` (see its docstring for the method). Nothing was tuned toward a result;",
        "every design that was considered is in the table.",
        "",
        f"* Household: the demo household. Continuation (best fixed strategy): {strategy_label}.",
        f"* {paths} held-out paths x 42 years = {paths * 42:,} decisions per design. Each path follows the fixed strategy; the planner searches each year",
        "  and records what it *would* choose (shadow mode), so every design is judged on the same states.",
        f"* Each candidate and each chosen action is then re-scored on {reference_k:,} fresh futures the search never used, importance-sampled toward bad",
        f"  markets (tilt {reference_tilt}) so the tail that dominates certainty-equivalent wealth is represented.",
        "* **Gain** of a decision = relative gain in certainty-equivalent after-tax wealth at the horizon of the chosen action over the fixed strategy's action,",
        "  in basis points (1 bp = 0.01%). Positive means the decision helped. **Harmful** and **helpful** count departures worth less than -1 bp / more than +1 bp.",
        "",
        "| Design | Departs | Mean gain per decision | Mean gain when it departs | Harmful | Helpful | Seconds per 100 paths |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in measurements:
        lines.append(
            f"| {m.design.description} | {m.departures:.1%} | {m.mean_gain_bp:+.1f} bp | {m.mean_gain_departing_bp:+.1f} bp | "
            f"{m.harmful_share:.0%} | {m.helpful_share:.0%} | {m.seconds_per_100_paths:.1f} |"
        )
    lines += ["", "## Where the gains and losses come from", "", "Mean gain (bp) of the decisions that changed each dimension, with the number of such decisions.", ""]
    names = list(ad.DIM_NAMES)
    lines += ["| Design | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for m in measurements:
        cells = [f"{m.by_dimension[n][1]:+.0f} bp (n={m.by_dimension[n][0]})" if m.by_dimension[n][0] else "none" for n in names]
        lines.append(f"| {m.design.name} | " + " | ".join(cells) + " |")
    by = {m.design.name: m for m in measurements}
    lines += ["", "## Reading this", ""]
    if {"plain", "default"} <= set(by):
        plain, default = by["plain"], by["default"]
        lines += [
            f"* The search as first built made the planner's own objective **worse** on average ({plain.mean_gain_bp:+.1f} bp per decision; {plain.harmful_share:.0%} of its changes "
            "were harmful): the best of a dozen candidates scored on the same 32 rollouts is flattered by luck, and 32 rollouts almost never contain the futures in "
            "which money runs out, so changes that add tail risk look free.",
            f"* Importance-sampling the rollouts toward bad markets (the weights keep every estimate unbiased) and re-testing each proposed change on fresh futures remove "
            f"most of that harm. The default design ends at {default.mean_gain_bp:+.1f} bp per decision, with {default.harmful_share:.0%} of its changes harmful, "
            f"and it changes {default.departures:.1%} of decisions.",
        ]
        conversion = default.by_dimension["conversion"]
        lines.append(
            f"* What the default still does is mostly Roth conversions ({conversion[0]} decisions, {conversion[1]:+.0f} bp each): their value is in the bulk of outcomes and is "
            "easy to measure. Stock-share and private-credit changes are tail effects; they are rare under the default."
        )
    if {"plain_z0", "plain_z2"} <= set(by):
        lines.append(
            f"* Taking the best candidate whatever the margin is far worse ({by['plain_z0'].mean_gain_bp:+.1f} bp); demanding two standard errors on the same rollouts "
            f"({by['plain_z2'].mean_gain_bp:+.1f} bp) removes most changes but still lets bad ones through."
        )
    if {"default", "k128", "k256"} <= set(by):
        lines.append(
            f"* More rollouts per candidate find more of the real gains: {by['k256'].mean_gain_bp:+.1f} bp per decision at K=256 against {by['default'].mean_gain_bp:+.1f} bp for the default "
            f"at about {by['k256'].seconds_per_100_paths / max(by['default'].seconds_per_100_paths, 1e-9):.0f} times the cost; K=128 without the confirmation step "
            f"({by['k128'].mean_gain_bp:+.1f} bp) is no better than the default. At K=256 the stock-share changes the planner makes are on average "
            f"{'mildly positive' if by['k256'].by_dimension['stock_share'][1] > 0 else 'not positive'} ({by['k256'].by_dimension['stock_share'][1]:+.0f} bp) and private-credit changes "
            f"{'positive' if by['k256'].by_dimension['private_credit'][1] > 0 else 'negative'} ({by['k256'].by_dimension['private_credit'][1]:+.0f} bp)."
        )
    lines += [
        "* The reference is itself a Monte Carlo estimate (a tilted sample of 1,024 futures): far more accurate than the search's 32 rollouts, not exact. "
        "A decision worth less than about 1 bp cannot be told from zero.",
        "* This table is about single decisions measured against the fixed strategy's continuation. What they add up to on whole paths, "
        "against the same futures the other strategies are measured on, is in `reports/adaptive_evaluation.md`.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--paths", type=int, default=80)
    parser.add_argument("--reference-k", type=int, default=1_024)
    parser.add_argument("--reference-tilt", type=float, default=0.25)
    parser.add_argument("--designs", default=",".join(BY_NAME), help="comma-separated names from: " + ", ".join(BY_NAME))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    designs = [BY_NAME[n] for n in args.designs.split(",")]
    household = sample_household()
    strategy = search(build_inputs(household, n_paths=400, seed=SEED)).best.strategy
    measurements = run(args.paths, args.reference_k, args.reference_tilt, designs, progress=True)
    text = report(measurements, args.paths, args.reference_k, args.reference_tilt, strategy.short_label())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
