"""The household-type study (spec A10): the planner on 300 synthetic households of six types.

    python -m app.study.household_study --per-type 50 --out-dir ../reports

For each household: search the strategy menu on 400 futures, then score the winner and both
advisors on `n_eval` fresh futures the search never saw. Writes `household_study.csv` (one row per
household) and `household_study.md` (the summary by type). Nothing is tuned.

Annualized advantage and the two measures are defined in `app.study.metrics`.

With `--adaptive-paths N` the year-by-year adaptive planner (spec part B) is also run on N of the held-out futures of
every household, and the four-way comparison (typical advisor, good RIA, best fixed strategy, adaptive planner) and
the value of judgment over time are reported by household type (spec B5).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from app.planner.baseline import BASELINES
from app.planner.search import RISK_AVERSION, WEALTH_FLOOR, search
from app.sim import adaptive as ad
from app.sim.simulate import HC_SS, TV_AGED, build_inputs, run_batch
from app.study import households as hh
from app.study.adaptive_evaluation import LABELS, four_way
from app.study.metrics import annualized, compare
from app.study.reach import pretax_balance

EVAL_SEED_OFFSET = 1_000_003
DEFAULT_N_EVAL = 1_000


def adaptive_columns(item: hh.StudyHousehold, chosen, position: int, adaptive_paths: int, risk_aversion: float) -> dict:
    """The four-way comparison and the value of judgment on `adaptive_paths` of the household's held-out futures."""
    household = item.household
    held = build_inputs(household, n_paths=adaptive_paths, seed=5_000 + position + EVAL_SEED_OFFSET)
    fw = four_way(household, chosen, held, ad.AdaptiveSettings(risk_aversion=risk_aversion))
    out: dict = {"adaptive_paths": adaptive_paths, "adaptive_seconds": fw.adaptive.elapsed_seconds}
    for key in LABELS:
        r = fw.row(key)
        out.update({f"fw_{key}_{name}": value for name, value in r.items()})
    for key in ("good_ria", "best_fixed", "adaptive"):
        for over in ("typical_advisor", "good_ria"):
            adv = fw.advantage(key, over, with_range=False)
            out[f"fw_{key}_adv_median_vs_{over}"] = adv.median
            out[f"fw_{key}_adv_risk_adjusted_vs_{over}"] = adv.risk_adjusted
    judgment = fw.judgment
    out["judgment_median"] = judgment.median
    out["judgment_risk_adjusted"] = judgment.risk_adjusted
    differs = fw.adaptive.chosen != fw.adaptive.continuation
    out["departure_share"] = float(differs.any(axis=2).mean())
    for d, name in enumerate(ad.DIM_NAMES):
        out[f"departure_{name}"] = float(differs[:, :, d].mean())
    return out


def household_row(
    item: hh.StudyHousehold,
    position: int,
    n_search: int,
    n_eval: int,
    risk_aversion: float,
    adaptive_paths: int = 0,
    measure_risk_aversion: float | None = None,
    heirs_rates: tuple[float, ...] = (),
) -> dict:
    """`risk_aversion` is what the planner searches at; `measure_risk_aversion` (default the same) is the risk aversion
    behind the reported risk-adjusted advantage, so plans chosen at different settings can be read on one yardstick.
    `heirs_rates` add the raw advantage with the pre-tax balance at the horizon taxed at those flat rates."""
    measure_risk_aversion = risk_aversion if measure_risk_aversion is None else measure_risk_aversion
    household = item.household
    seed = 5_000 + position
    years = household.horizon_years
    futures = build_inputs(household, n_paths=n_search, seed=seed)
    chosen = search(futures, risk_aversion=risk_aversion).best.strategy
    held = build_inputs(household, n_paths=n_eval, seed=seed + EVAL_SEED_OFFSET)
    policies = [chosen.policy(), *(b.policy for b in BASELINES)]
    batch = run_batch(held, policies)
    a = household.accounts
    liquid = household.liquid_wealth
    row = {
        "type": item.type,
        "index": item.index,
        "note": item.note,
        "age": household.primary_age,
        "wages": household.total_wages,
        "liquid_wealth": liquid,
        "pretax": a.pretax_balance,
        "roth": a.roth_balance,
        "brokerage": a.brokerage_value,
        "basis_ratio": a.brokerage_basis / a.brokerage_value if a.brokerage_value else 0.0,
        "cash": a.cash,
        "retirement_age": household.goals.retirement_age,
        "years": years,
        "strategy": chosen.short_label(),
        **{f"choice_{k}": v for k, v in chosen.choices().items()},
        "plan_median": float(np.median(batch.wealth[0])),
        "plan_p10": float(np.percentile(batch.wealth[0], 10)),
        "plan_taxes": float(np.median(batch.taxes_paid[0] + batch.pretax_owed[0])),
        "plan_shortfall": float(np.mean(batch.unfunded[0] > 0)),
    }
    for i, baseline in enumerate(BASELINES, start=1):
        adv = compare(batch.wealth[0], batch.wealth[i], years, measure_risk_aversion)
        key = baseline.key
        row[f"{key}_median"] = adv.baseline_median
        row[f"{key}_p10"] = float(np.percentile(batch.wealth[i], 10))
        row[f"{key}_taxes"] = float(np.median(batch.taxes_paid[i] + batch.pretax_owed[i]))
        row[f"{key}_shortfall"] = float(np.mean(batch.unfunded[i] > 0))
        row[f"adv_median_vs_{key}"] = adv.median
        row[f"adv_risk_adjusted_vs_{key}"] = adv.risk_adjusted
    if heirs_rates:
        ss, aged = float(held.hhc[HC_SS]), float(held.tv[-1, TV_AGED])
        balances = np.vstack([pretax_balance(batch.pretax_owed[i], ss, aged) for i in range(len(policies))])
        for rate in heirs_rates:
            wealth = batch.wealth + batch.pretax_owed - rate * balances
            for i, baseline in enumerate(BASELINES, start=1):
                row[f"adv_median_vs_{baseline.key}_heirs{round(rate * 100)}"] = annualized(
                    float(np.median(wealth[0])), float(np.median(wealth[i])), years
                )
    # households that run out of money in most futures: the floored objective stops being informative
    row["underfunded"] = bool(row["plan_median"] < WEALTH_FLOOR)
    if adaptive_paths > 0:
        row.update(adaptive_columns(item, chosen, position, adaptive_paths, risk_aversion))
    return row


def run(
    per_type: int = 50,
    n_search: int = 400,
    n_eval: int = DEFAULT_N_EVAL,
    risk_aversion: float = RISK_AVERSION,
    seed: int = 10,
    progress: bool = False,
    adaptive_paths: int = 0,
    checkpoint: Path | None = None,
    measure_risk_aversion: float | None = None,
    heirs_rates: tuple[float, ...] = (),
) -> pd.DataFrame:
    """The study. With a `checkpoint` path the rows so far are saved every 25 households and a rerun resumes from them."""
    items = hh.generate(seed=seed, per_type=per_type)
    rows: list[dict] = []
    if checkpoint is not None and checkpoint.exists():
        header = pd.read_csv(checkpoint, nrows=0).columns
        # the menu options ("50", "15") are text: do not let them read back as numbers; an empty note reads back as NaN
        previous = pd.read_csv(checkpoint, dtype={c: str for c in header if c.startswith("choice_")}).fillna({"note": ""})
        if len(previous) <= len(items) and (adaptive_paths == 0 or "judgment_median" in previous.columns):
            rows = previous.to_dict("records")
            print(f"  resuming from {len(rows)} households in {checkpoint}", flush=True)
    started = time.perf_counter()
    first = len(rows)
    for position in range(first, len(items)):
        rows.append(
            household_row(items[position], position, n_search, n_eval, risk_aversion, adaptive_paths, measure_risk_aversion, heirs_rates)
        )
        if progress and (position + 1) % 25 == 0:
            elapsed = time.perf_counter() - started
            print(f"  {position + 1}/{len(items)} households ({elapsed / (position + 1 - first):.1f}s each)", flush=True)
        if checkpoint is not None and (position + 1) % 25 == 0:
            pd.DataFrame(rows).to_csv(checkpoint, index=False)
    return pd.DataFrame(rows)


def _pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def _share(frame: pd.DataFrame, column: str, predicate) -> float:
    return float(frame[column].map(predicate).mean())


def _spread(values: pd.Series) -> str:
    return f"{_pct(values.median())} ({_pct(values.quantile(0.1))} to {_pct(values.quantile(0.9))})"


def _dollars(x: float) -> str:
    return f"${x:,.0f}"


def adaptive_sections(frame: pd.DataFrame) -> list[str]:
    """The four-way comparison and the value of judgment, by household type (spec B5)."""
    n = int(frame["adaptive_paths"].iloc[0])
    seconds = frame["adaptive_seconds"].mean()
    lines = [
        "## The adaptive planner: four strategies, by type",
        "",
        f"On {n} of each household's held-out futures (the same futures for all four strategies), the **typical advisor**, the **good RIA**, the **best fixed strategy** "
        "(the winner above) and the **adaptive planner** (the year-by-year planner of spec part B, K = 32 rollouts per candidate, "
        f"each proposed change re-tested on 64 fresh futures; {seconds:.1f} seconds per household on average). Advantage cells are the median across the "
        "households of the type, with the 10th to 90th percentile across households. The 10th-percentile outcome and lifetime taxes are medians across households (real 2026 dollars, "
        "at the household's horizon; taxes are those paid over the plan plus tax owed on the pre-tax balance at the end).",
        f"With only {n} futures per household the risk-adjusted figure of a single household is noisy (it is decided by whether one or two futures run out of money), so read the medians across households, not any one household.",
        "",
        "| Type | Strategy | Median advantage over the typical advisor | Risk-adjusted advantage over the typical advisor | Median advantage over the good RIA | Risk-adjusted advantage over the good RIA | 10th-percentile outcome | Lifetime taxes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for t, title in hh.TYPES.items():
        sub = frame[frame["type"] == t]
        for key, label in LABELS.items():
            cells = []
            for over in ("typical_advisor", "good_ria"):
                for measure in ("median", "risk_adjusted"):
                    column = f"fw_{key}_adv_{measure}_vs_{over}"
                    cells.append(_spread(sub[column]) if column in sub.columns else "baseline" if key == "typical_advisor" and over == "typical_advisor" else "n/a")
            lines.append(
                f"| {title if key == 'typical_advisor' else ''} | {label} | " + " | ".join(cells)
                + f" | {_dollars(sub[f'fw_{key}_p10'].median())} | {_dollars(sub[f'fw_{key}_taxes'].median())} |"
            )
    lines += [
        "",
        "## The value of judgment over time, by type",
        "",
        "The adaptive planner against the best fixed strategy it continues, on the same futures: what choosing each year's decisions after seeing that year's returns adds.",
        "",
        "| Type | Median advantage over the best fixed strategy | Risk-adjusted advantage over the best fixed strategy | Households where it is ahead (median / risk-adjusted) | Decision-years where it leaves the fixed strategy | Mostly changes |",
        "|---|---|---|---|---|---|",
    ]
    names = list(ad.DIM_NAMES)

    def row(title: str, sub: pd.DataFrame) -> str:
        shares = {name: sub[f"departure_{name}"].mean() for name in names}
        top = max(shares, key=shares.get)
        return (
            f"| {title} | {_spread(sub['judgment_median'])} | {_spread(sub['judgment_risk_adjusted'])} | "
            f"{(sub['judgment_median'] > 0).mean() * 100:.0f}% / {(sub['judgment_risk_adjusted'] > 0).mean() * 100:.0f}% | "
            f"{sub['departure_share'].mean() * 100:.1f}% | {top.replace('_', ' ')} ({shares[top] * 100:.1f}%) |"
        )

    for t, title in hh.TYPES.items():
        lines.append(row(title, frame[frame["type"] == t]))
    lines.append(row(f"**All {len(frame)} households**", frame))
    lines.append("")
    return lines


def heirs_sections(frame: pd.DataFrame) -> list[str]:
    """The raw advantage with the pre-tax balance at the horizon taxed at a flat heirs' rate (a sensitivity, not the app's rule)."""
    rates = sorted({int(c.rsplit("heirs", 1)[1]) for c in frame.columns if "_heirs" in c})
    lines = [
        "## If heirs paid a flat tax on pre-tax money at the horizon (sensitivity)",
        "",
        "The app values a pre-tax balance at the horizon as if it were withdrawn evenly over 20 years beside Social Security, a low rate. "
        "A non-spouse heir must empty an inherited account within ten years. Median raw advantage over the good RIA with the balance taxed at a flat rate instead "
        "(median across the households of the type; the plan's choices are the ones the planner made under the app's rule).",
        "",
        "| Type | As specified | " + " | ".join(f"Heirs at {r}%" for r in rates) + " |",
        "|---|---|" + "---|" * len(rates),
    ]
    for t, title in hh.TYPES.items():
        sub = frame[frame["type"] == t]
        cells = [_pct(sub["adv_median_vs_good_ria"].median())] + [_pct(sub[f"adv_median_vs_good_ria_heirs{r}"].median()) for r in rates]
        lines.append(f"| {title} | " + " | ".join(cells) + " |")
    cells = [_pct(frame["adv_median_vs_good_ria"].median())] + [_pct(frame[f"adv_median_vs_good_ria_heirs{r}"].median()) for r in rates]
    lines += [f"| **All {len(frame)} households** | " + " | ".join(f"**{c}**" for c in cells) + " |", ""]
    return lines


def summarize(frame: pd.DataFrame, n_eval: int, risk_aversion: float, measure_risk_aversion: float | None = None) -> str:
    measure = risk_aversion if measure_risk_aversion is None else measure_risk_aversion
    setting = (
        f"risk aversion {risk_aversion:g}"
        if measure == risk_aversion
        else f"the planner searched at risk aversion {risk_aversion:g}; risk-adjusted figures are at risk aversion {measure:g}"
    )
    lines = [
        "# Household-type study",
        "",
        f"{len(frame)} synthetic households ({frame.groupby('type').size().iloc[0]} of each of six types), all fictional. For each, the planner searched",
        f"its strategy menu on 400 simulated futures and the winner was scored against both advisors on {n_eval:,} fresh",
        f"futures it never saw ({setting}). Nothing was tuned; the households were drawn from fixed ranges",
        "that make each a clear example of its type (see `backend/app/study/households.py`).",
        "",
        "* **Median advantage**: difference in median after-tax wealth at the horizon, annualized as a growth-rate difference.",
        "* **Risk-adjusted advantage**: the same on certainty-equivalent wealth (the planner's objective).",
        "* Each cell is the **median across the households of that type** (with the 10th to 90th percentile across households).",
        "  Dollar-weighted or pooled figures would differ; this is the typical household of the type.",
        "",
    ]
    for baseline in BASELINES:
        key = baseline.key
        lines += [
            f"## Against the {baseline.label.lower()}",
            "",
            f"{baseline.definition}",
            "",
            "| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |",
            "|---|---|---|---|---|---|",
        ]
        for t, title in hh.TYPES.items():
            sub = frame[frame["type"] == t]
            m = sub[f"adv_median_vs_{key}"]
            r = sub[f"adv_risk_adjusted_vs_{key}"]
            lines.append(
                f"| {title} | {len(sub)} | {_pct(m.median())} ({_pct(m.quantile(0.1))} to {_pct(m.quantile(0.9))}) | "
                f"{_pct(r.median())} ({_pct(r.quantile(0.1))} to {_pct(r.quantile(0.9))}) | "
                f"{(m > 0).mean() * 100:.0f}% | {(r > 0).mean() * 100:.0f}% |"
            )
        m, r = frame[f"adv_median_vs_{key}"], frame[f"adv_risk_adjusted_vs_{key}"]
        lines += [
            f"| **All {len(frame)} households** | {len(frame)} | **{_pct(m.median())}** ({_pct(m.quantile(0.1))} to {_pct(m.quantile(0.9))}) | "
            f"**{_pct(r.median())}** ({_pct(r.quantile(0.1))} to {_pct(r.quantile(0.9))}) | {(m > 0).mean() * 100:.0f}% | {(r > 0).mean() * 100:.0f}% |",
            "",
        ]

    lines += [
        "## What the planner chose, by type",
        "",
        "Share of households of each type whose winning strategy uses each option.",
        "",
        "| Type | Lowest stock share (50%) | Stock share 80%+ | Roth conversions | Private credit 15% | Direct indexing | Goal bonds | Roth 401(k) (any) | Borrow for goals |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for t, title in hh.TYPES.items():
        sub = frame[frame["type"] == t]
        lines.append(
            f"| {title} | {_share(sub, 'choice_stock_share', lambda v: v == '50') * 100:.0f}% | "
            f"{_share(sub, 'choice_stock_share', lambda v: int(v) >= 80) * 100:.0f}% | "
            f"{_share(sub, 'choice_conversion', lambda v: v != 'none') * 100:.0f}% | "
            f"{_share(sub, 'choice_private_credit', lambda v: v == '15') * 100:.0f}% | "
            f"{_share(sub, 'choice_direct_indexing', lambda v: v == 'on') * 100:.0f}% | "
            f"{_share(sub, 'choice_goal_bonds', lambda v: v == 'on') * 100:.0f}% | "
            f"{_share(sub, 'choice_k401', lambda v: v != 'pretax') * 100:.0f}% | "
            f"{_share(sub, 'choice_goal_funding', lambda v: v == 'borrow') * 100:.0f}% |"
        )
    if "judgment_median" in frame.columns:
        lines += [""] + adaptive_sections(frame)
    if any("_heirs" in c for c in frame.columns):
        lines += [""] + heirs_sections(frame)
    lines += [
        "",
        "## Reading these numbers",
        "",
        f"* **Underfunded households.** {int(frame['underfunded'].sum())} of {len(frame)} households have a median after-tax wealth at the horizon below the "
        f"${WEALTH_FLOOR:,.0f} floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so "
        "for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: "
        + ", ".join(
            f"{title.split(' (')[0].split(',')[0]} {frame[frame['type'] == t]['plan_shortfall'].mean() * 100:.1f}% for the plan vs "
            f"{frame[frame['type'] == t]['good_ria_shortfall'].mean() * 100:.1f}% for the good RIA"
            for t, title in hh.TYPES.items()
        )
        + ".",
        "* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra "
        "risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.",
        "* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-type", type=int, default=50)
    parser.add_argument("--n-eval", type=int, default=DEFAULT_N_EVAL)
    parser.add_argument("--seed", type=int, default=10)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--adaptive-paths", type=int, default=0, help="also run the adaptive planner on this many futures per household (spec B5)")
    parser.add_argument("--checkpoint", type=Path, default=None, help="save progress here every 25 households and resume from it")
    parser.add_argument("--risk-aversion", type=float, default=RISK_AVERSION, help="the risk aversion the planner searches at (the app's is 3)")
    parser.add_argument(
        "--measure-risk-aversion", type=float, default=None, help="the risk aversion behind the reported risk-adjusted advantage (default: the same)"
    )
    parser.add_argument(
        "--heirs-rates", type=float, nargs="*", default=[], help="flat tax rates on pre-tax money at the horizon to report as a sensitivity, e.g. 0.24 0.32"
    )
    args = parser.parse_args(argv)
    frame = run(
        per_type=args.per_type, n_eval=args.n_eval, seed=args.seed, progress=True,
        adaptive_paths=args.adaptive_paths, checkpoint=args.checkpoint, risk_aversion=args.risk_aversion,
        measure_risk_aversion=args.measure_risk_aversion, heirs_rates=tuple(args.heirs_rates),
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out_dir / "household_study.csv", index=False)
    text = summarize(frame, args.n_eval, args.risk_aversion, args.measure_risk_aversion)
    (args.out_dir / "household_study.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
