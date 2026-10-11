"""The sample household at risk aversion 2, 3 and 5 (spec A7): how the recommendation changes.

    python -m app.study.risk_aversion --out ../reports/risk_aversion.md

Risk aversion is the CRRA coefficient behind the planner's score (default 3). A higher number
means a bad outcome costs more, so the planner trades median wealth for a smaller bad case.
Each row is a full search-then-score at that risk aversion, on the app's default futures (400,
seed 2026), scored on 2,000 held-out futures. Nothing is tuned: this is what the engine returns.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.study.measure import measure, sample_household

LEVELS = (2.0, 3.0, 5.0)


def render(rows: list[dict]) -> str:
    lines = [
        "# The sample household at risk aversion 2, 3 and 5",
        "",
        "Risk aversion is the CRRA coefficient behind the planner's objective (certainty-equivalent after-tax wealth",
        "at 80, $50,000 floor). The app's setting is 3. Each row repeats the whole search at that setting and scores",
        "the winner against each advisor on 2,000 futures the search never saw.",
        "",
        "| Risk aversion | Recommendation | Median adv. vs good RIA | Risk-adj. adv. vs good RIA | Median adv. vs typical advisor | Risk-adj. adv. vs typical advisor | Chance of a shortfall: plan / good RIA / typical |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        good = row["baselines"]["good_ria"]["held_out"]
        typical = row["baselines"].get("typical_advisor", {}).get("held_out")
        short_good = row["baselines"]["good_ria"]["shortfall"]
        short_typ = row["baselines"].get("typical_advisor", {}).get("shortfall")
        lines.append(
            f"| {row['risk_aversion']:g} | {row['strategy_label']} | {good['median'] * 100:+.2f}%/yr | "
            f"{good['risk_adjusted'] * 100:+.2f}%/yr | "
            + (f"{typical['median'] * 100:+.2f}%/yr | {typical['risk_adjusted'] * 100:+.2f}%/yr | " if typical else "n/a | n/a | ")
            + f"{short_good['plan'] * 100:.1f}% / {short_good['baseline'] * 100:.1f}% / "
            + (f"{short_typ['baseline'] * 100:.1f}%" if short_typ else "n/a")
            + " |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--n-eval", type=int, default=2000)
    args = parser.parse_args(argv)
    household = sample_household()
    rows = [measure(household, risk_aversion=level, n_eval=args.n_eval) for level in LEVELS]
    text = render(rows)
    args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
