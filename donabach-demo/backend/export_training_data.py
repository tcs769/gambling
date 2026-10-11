"""Export training data for the strategy recommender.

    python export_training_data.py --k 2000 --paths 150 --seed 1 --out data/training_data.parquet

For each of K synthetic households (ranges configurable, see `SamplingRanges`) this runs the
search planner on a reduced number of futures and writes one row: the exact feature vector the
app builds (`app.ml.interfaces.household_features`) plus the best strategy's choices as
`label_*` columns. The recommender is trained elsewhere; this script trains nothing.

Extra columns for weighting or filtering examples: the engine's score for the best strategy and
for the RIA baseline, and how far the best strategy with a different result trailed the winner
(`score_gap_to_second`; near zero means several strategies are close and the label is soft).
When strategies tie exactly, the label is the first in menu order (e.g. "low-income years only"
rather than "every year").
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app.ml.interfaces import FEATURE_NAMES, household_features
from app.planner.baseline import RIA_BASELINE
from app.planner.search import Outcome, search
from app.planner.strategies import CHOICES
from app.schemas import Accounts, Goals, Household, Person, SocialSecurity
from app.sim.simulate import build_inputs, run_batch


@dataclass(frozen=True)
class SamplingRanges:
    age: tuple[int, int] = (25, 60)
    household_income: tuple[float, float] = (60_000.0, 600_000.0)  # sampled log-uniformly
    two_earner_probability: float = 0.7
    second_earner_share: tuple[float, float] = (0.2, 0.5)
    # Liquid wealth as a multiple of income per year worked since 25.
    wealth_multiple_per_year: tuple[float, float] = (0.05, 0.25)
    pretax_share: tuple[float, float] = (0.35, 0.80)
    roth_share: tuple[float, float] = (0.0, 0.15)
    cash_to_income: tuple[float, float] = (0.02, 0.15)
    brokerage_basis_ratio: tuple[float, float] = (0.60, 1.00)
    children: tuple[int, int] = (0, 3)
    home_goal_probability: float = 0.35
    retirement_age: tuple[int, int] = (55, 67)
    retirement_spending_to_income: tuple[float, float] = (0.45, 0.80)


def _uniform(rng: np.random.Generator, bounds: tuple[float, float]) -> float:
    return float(rng.uniform(*bounds))


def sample_household(rng: np.random.Generator, r: SamplingRanges = SamplingRanges()) -> Household:
    age = int(rng.integers(r.age[0], r.age[1] + 1))
    income = float(np.exp(rng.uniform(np.log(r.household_income[0]), np.log(r.household_income[1]))))
    people = [Person(age=age, wages=income)]
    if rng.random() < r.two_earner_probability:
        share = _uniform(rng, r.second_earner_share)
        spouse_age = int(np.clip(age + rng.integers(-4, 5), 22, 69))
        people = [
            Person(age=age, wages=income * (1.0 - share)),
            Person(age=spouse_age, wages=income * share),
        ]

    years_worked = max(1, age - 25)
    liquid = income * years_worked * _uniform(rng, r.wealth_multiple_per_year)
    cash = income * _uniform(rng, r.cash_to_income)
    pretax = liquid * _uniform(rng, r.pretax_share)
    roth = liquid * _uniform(rng, r.roth_share)
    brokerage = max(0.0, liquid - pretax - roth)
    accounts = Accounts(
        brokerage_value=brokerage,
        brokerage_basis=brokerage * _uniform(rng, r.brokerage_basis_ratio),
        pretax_balance=pretax,
        pretax_equity_share=float(np.clip(0.9 - 0.012 * (age - 25), 0.4, 0.9)),
        roth_balance=roth,
        cash=cash,
    )

    n_children = int(rng.integers(r.children[0], r.children[1] + 1)) if age <= 50 else 0
    youngest_max = max(0, min(17, age - 20))
    children = sorted(int(rng.integers(0, youngest_max + 1)) for _ in range(n_children))

    home = rng.random() < r.home_goal_probability
    goals = Goals(
        home_purchase_in_years=int(rng.integers(1, 9)) if home else None,
        home_down_payment=income * float(rng.uniform(0.3, 1.0)),
        college_starts_in_years=max(0, 18 - min(children)) if children else None,
        college_annual_cost=float(rng.uniform(20_000, 45_000)),
        college_years=4,
        retirement_age=int(rng.integers(max(r.retirement_age[0], age + 1), r.retirement_age[1] + 1)),
        retirement_spending=min(400_000.0, income * _uniform(rng, r.retirement_spending_to_income)),
    )
    social_security = SocialSecurity(annual_benefit=float(np.clip(0.30 * income, 15_000, 70_000)), start_age=67)
    return Household(
        people=people,
        children_ages=children,
        accounts=accounts,
        goals=goals,
        social_security=social_security,
    )


def export(
    k: int,
    paths: int = 150,
    seed: int = 1,
    out: Path | None = None,
    ranges: SamplingRanges = SamplingRanges(),
    progress: bool = False,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    started = time.perf_counter()
    for i in range(k):
        household = sample_household(rng, ranges)
        futures = build_inputs(household, n_paths=paths, seed=int(rng.integers(1, 2**31 - 1)))
        result = search(futures)
        best = result.best
        ria = Outcome.of(run_batch(futures, [RIA_BASELINE]).wealth[0])
        # Exact ties (e.g. "fill 12% every year" vs "low-income years only" when no bracket room
        # exists) are not real runners-up; measure the gap to the best *different* result.
        runner_up = next(r for r in result.ranked[1:] if r.tied_with is None)
        second = runner_up.outcome.score
        row = dict(household_features(household))
        row.update({f"label_{choice}": value for choice, value in best.strategy.choices().items()})
        row.update(
            best_score=best.outcome.score,
            best_median=best.outcome.median,
            best_p10=best.outcome.p10,
            ria_score=ria.score,
            ria_median=ria.median,
            score_gap_to_second=1.0 - second / best.outcome.score if best.outcome.score > 0 else 0.0,
            n_paths=paths,
        )
        rows.append(row)
        if progress and (i + 1) % 50 == 0:
            rate = (i + 1) / (time.perf_counter() - started)
            print(f"  {i + 1}/{k} households ({rate:.1f}/s)", file=sys.stderr)
    frame = pd.DataFrame(rows)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out, index=False)
    return frame


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--k", type=int, default=500, help="number of synthetic households")
    parser.add_argument("--paths", type=int, default=150, help="simulated futures per household")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=Path("data/training_data.parquet"))
    args = parser.parse_args(argv)
    frame = export(args.k, args.paths, args.seed, args.out, progress=True)
    print(f"Wrote {len(frame)} rows x {len(frame.columns)} columns to {args.out}")
    print(f"Features ({len(FEATURE_NAMES)}): see app.ml.interfaces.FEATURE_NAMES")
    print(f"Labels: {', '.join('label_' + c for c in CHOICES)}")


if __name__ == "__main__":
    main()
