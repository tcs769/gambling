"""How the sample household's result moves under the corrected A8 assumptions (analysis only).

    python -m app.study.sensitivity --out ../reports/sensitivity.md

The two assumptions reviewed in `reports/assumption_review.md` are NOT changed in the app. This
reruns the whole search-then-score on the sample household with each proposed correction applied
(alone and together) so the effect on the headline is visible. Every scenario uses the same
futures; only the assumption differs. Scored on 2,000 held-out futures against the good RIA.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from app.planner.strategies import menu
from app.sim import markets
from app.sim.simulate import ModelOptions
from app.study.measure import DEFAULT_SEEDS, measure_seeds, sample_household

SPEC = markets.DEFAULT_ASSUMPTIONS
PC_LOWER_RETURN = replace(SPEC, means=(0.055, 0.015, 0.025))
PC_MORE_RISK = replace(SPEC, sds=(0.16, 0.05, 0.12), correlation=((1.0, 0.1, 0.7), (0.1, 1.0, 0.1), (0.7, 0.1, 1.0)))
PC_STRESS = replace(SPEC, pc_mode="stress")
EVIDENCE_HARVEST = ModelOptions(harvest_model="evidence", di_fee_premium=0.002)

SCENARIOS: list[tuple[str, str, ModelOptions, list | None]] = [
    ("As specified", "Every assumption as in the app today.", ModelOptions(), None),
    (
        "Direct indexing: evidence-based harvest",
        "Harvest = min(35% of value, basis, 0.85 b0^3 x decline + 0.14 x value x b1^14), b = basis/value, plus a 0.20% "
        "a year fee premium on direct-indexed equity.",
        EVIDENCE_HARVEST,
        None,
    ),
    (
        "Direct indexing: evidence-based harvest, no fee premium",
        "The same harvest rule alone.",
        ModelOptions(harvest_model="evidence"),
        None,
    ),
    (
        "Direct indexing forced on, as specified",
        "The planner must use direct indexing (the sample household's winner does not use it once conversions are "
        "allowed, so the rows above cannot show what the assumption is worth).",
        ModelOptions(),
        [st for st in menu() if st.direct_indexing],
    ),
    (
        "Direct indexing forced on, evidence-based harvest and fee premium",
        "The same, with the evidence-based harvest rule and the 0.20% fee premium.",
        EVIDENCE_HARVEST,
        [st for st in menu() if st.direct_indexing],
    ),
    (
        "Private credit: 2.5% real return",
        "Return 1 point lower (the low end of the plausible 2-5% range); volatility and correlations as specified.",
        ModelOptions(market=PC_LOWER_RETURN),
        None,
    ),
    (
        "Private credit: 12% volatility, 0.7 correlation with stocks",
        "The proposed values for levered or semi-liquid retail vehicles.",
        ModelOptions(market=PC_MORE_RISK),
        None,
    ),
    (
        "Private credit: equity-linked stress tails",
        "Calm years N(4.9%, 6%); in a year stocks fall more than 1.28 standard deviations below their mean (about "
        "1 in 10) private credit is N(-10%, 10%). Overall mean about 3.4%, volatility about 8%.",
        ModelOptions(market=PC_STRESS),
        None,
    ),
    (
        "Both proposals together",
        "Evidence-based harvest with the fee premium, and private credit with equity-linked stress tails.",
        ModelOptions(harvest_model="evidence", di_fee_premium=0.002, market=PC_STRESS),
        None,
    ),
    (
        "Both proposals, lower and riskier private credit",
        "Evidence-based harvest with the fee premium, and private credit at 2.5% return, 12% volatility, 0.7 correlation.",
        ModelOptions(
            harvest_model="evidence",
            di_fee_premium=0.002,
            market=replace(PC_MORE_RISK, means=(0.055, 0.015, 0.025)),
        ),
        None,
    ),
    (
        "No private credit allowed",
        "The planner may not hold any private credit (sleeve fixed at 0%); everything else as specified.",
        ModelOptions(),
        menu(private_credit_shares=(0.0,)),
    ),
]


def render(rows: list[tuple[str, str, dict]]) -> str:
    lines = [
        "# Sensitivity of the sample household to the corrected A8 assumptions",
        "",
        "**Analysis only: the app still uses the assumptions as specified.** Each row repeats the whole search on the",
        "sample household with the correction applied, then scores the winner on 2,000 futures the search never saw,",
        "against the good RIA, on the same futures as every other row (the corrections change the world the plan is",
        "simulated in; the baseline lives in the same world). See `reports/assumption_review.md` for the evidence.",
        "",
        "| Scenario | What changes | Recommendation (seed 2026) | Median advantage | Risk-adjusted advantage | Mean of 5 seeds (median / risk-adj.) |",
        "|---|---|---|---|---|---|",
    ]
    for name, what, result in rows:
        app = result["app_seed_run"]
        held = app["baselines"]["good_ria"]["held_out"]
        mean = result["mean"]["good_ria"]["held_out"]
        lines.append(
            f"| {name} | {what} | {app['strategy_label']} | {held['median'] * 100:+.2f}%/yr | "
            f"{held['risk_adjusted'] * 100:+.2f}%/yr | {mean['median'] * 100:+.2f}% / {mean['risk_adjusted'] * 100:+.2f}% |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--n-eval", type=int, default=2000)
    args = parser.parse_args(argv)
    household = sample_household()
    rows = []
    for name, what, options, strategies in SCENARIOS:
        result = measure_seeds(household, seeds=DEFAULT_SEEDS, n_eval=args.n_eval, options=options, strategies=strategies)
        rows.append((name, what, result))
        held = result["app_seed_run"]["baselines"]["good_ria"]["held_out"]
        print(f"{name}: {result['app_seed_run']['strategy_label']} | median {held['median'] * 100:+.2f}% risk-adj {held['risk_adjusted'] * 100:+.2f}%", flush=True)
    text = render(rows)
    args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
