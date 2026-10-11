"""Which options win across a synthetic sample of households (spec A2: stock share before and after).

    python -m app.study.winners --k 100 --paths 150 --out ../reports/stock_share_wins.md

The sample is the training-data exporter's own household generator (`export_training_data`,
seed 1, 100 households), searched on the same futures under two menus: the stock shares offered
before the review (70/80/90/100%) and the widened menu (50/60/70/80/90/100%). Everything else about
the menu is identical, so the only thing that differs between the two runs is the options on offer.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np

from app.planner.search import search
from app.planner.strategies import PRE_REVIEW_STOCK_SHARES, STOCK_SHARES, menu


def stock_share_wins(k: int = 100, paths: int = 150, seed: int = 1) -> dict[str, Counter]:
    """Winning stock share per household under the old and the widened menu."""
    from export_training_data import sample_household

    from app.sim.simulate import build_inputs

    rng = np.random.default_rng(seed)
    old_menu = menu(PRE_REVIEW_STOCK_SHARES)
    new_menu = menu(STOCK_SHARES)
    before: Counter = Counter()
    after: Counter = Counter()
    moved: Counter = Counter()  # households whose winner changed share, by (old -> new)
    for _ in range(k):
        household = sample_household(rng)
        futures = build_inputs(household, n_paths=paths, seed=int(rng.integers(1, 2**31 - 1)))
        old_best = search(futures, strategies=old_menu).best.strategy
        new_best = search(futures, strategies=new_menu).best.strategy
        before[old_best.stock_share] += 1
        after[new_best.stock_share] += 1
        if old_best.stock_share != new_best.stock_share:
            moved[(old_best.stock_share, new_best.stock_share)] += 1
    return {"before": before, "after": after, "moved": moved}


def render(result: dict[str, Counter], k: int, paths: int) -> str:
    before, after, moved = result["before"], result["after"], result["moved"]
    shares = sorted(set(STOCK_SHARES) | set(PRE_REVIEW_STOCK_SHARES))
    lines = [
        "# How often each stock share wins (100 synthetic households)",
        "",
        f"{k} synthetic households (the training-data generator, seed 1), each searched on {paths} simulated futures.",
        "Before: the menu offered 70/80/90/100% stocks. After (spec A2): 50/60/70/80/90/100%. Same households, same futures.",
        "",
        "| Stock share | Wins before | Wins after |",
        "|---|---|---|",
    ]
    for share in shares:
        b = before.get(share, 0)
        a = after.get(share, 0)
        lines.append(f"| {round(share * 100)}% | {b if share in PRE_REVIEW_STOCK_SHARES else 'not offered'} | {a} |")
    lines += [
        "",
        f"{sum(moved.values())} of {k} households changed their winning share when the menu widened.",
    ]
    if moved:
        lines += ["", "| Was | Became | Households |", "|---|---|---|"]
        for (old, new), n in sorted(moved.items()):
            lines.append(f"| {round(old * 100)}% | {round(new * 100)}% | {n} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--k", type=int, default=100)
    parser.add_argument("--paths", type=int, default=150)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = stock_share_wins(args.k, args.paths, args.seed)
    text = render(result, args.k, args.paths)
    args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
