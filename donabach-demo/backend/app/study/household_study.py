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
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

from app.planner.baseline import STUDY_BASELINES as BASELINES
from app.planner.baseline import TYPICAL_ADVISOR
from app.planner.search import RISK_AVERSION, WEALTH_FLOOR, search, search_matched
from app.planner.strategies import menu
from app.sim import adaptive as ad
from app.sim.simulate import ModelOptions, build_inputs, run_batch, run_detail
from app.study import households as hh
from app.study.adaptive_evaluation import LABELS, four_way
from app.study.metrics import annualized, compare
from app.study.equity_share import advisor_allocation_chain, equity_exposure

EVAL_SEED_OFFSET = 1_000_003
DEFAULT_N_EVAL = 1_000
_HEIRS_RATE_COLUMN = re.compile(r"_heirs\d+$")  # the sensitivity columns of a flat heirs' rate; the engine's own valuation has none


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


def plan_exposure(household, chosen) -> dict:
    """Stocks as a share of the portfolio today and from age 70. A fixed share and glide have a formula; with a spending
    reserve the share moves with the household's expenses, so it is read off the plan's own year log."""
    age = household.primary_age
    if not chosen.reserve_years:
        policy = chosen.policy()
        return {"plan_equity_today": equity_exposure(policy, age, age), "plan_equity_from_70": equity_exposure(policy, 70.0, age)}
    log = run_detail(build_inputs(household, deterministic=True), chosen.policy()).log
    last = len(log["equity_share"]) - 1
    return {
        "plan_equity_today": float(log["equity_share"][0]),
        "plan_equity_from_70": float(np.median(log["equity_share"][min(max(0, 70 - age), last):])),
    }


def household_row(
    item: hh.StudyHousehold,
    position: int,
    n_search: int,
    n_eval: int,
    risk_aversion: float,
    adaptive_paths: int = 0,
    measure_risk_aversion: float | None = None,
    heirs_rates: tuple[float, ...] = (),
    skill: bool = False,
    style: str = "balanced",
    valuation: str = "liquidated",
    giving_share: float = 0.0,
    options: ModelOptions | None = None,
) -> dict:
    """`style` is the planning style whose menu the planner searches ("balanced" is the original menu, "equity_first" the
    spending-reserve family). `valuation` is what the planner maximizes: "liquidated" (the app's) or "heirs" (passed to heirs).
    `giving_share` gives the household that share of its wages to charity every year: the plan gives appreciated lots, the advisors
    cash; the plan is also run giving cash, to show what giving lots is worth. `risk_aversion` is what the planner searches at; `measure_risk_aversion` (default the same) is the risk aversion
    behind the reported risk-adjusted advantage, so plans chosen at different settings can be read on one yardstick.
    `heirs_rates` add the raw advantage with the pre-tax balance at the horizon taxed at those flat rates.
    `skill` adds the plan's tools run at the advisor's own allocation: the part of the advantage that is not extra equity."""
    measure_risk_aversion = risk_aversion if measure_risk_aversion is None else measure_risk_aversion
    household = item.household
    if giving_share > 0.0:
        goals = household.goals.model_copy(update={"charitable_giving": giving_share * household.total_wages})
        household = household.model_copy(update={"goals": goals})
    seed = 5_000 + position
    years = household.horizon_years if options is None or options.horizon_age is None else options.horizon_age - household.primary_age
    futures = build_inputs(household, n_paths=n_search, seed=seed, options=options)
    if style == "liability_matched":
        # the planner under its two limits, checked on futures it did not search (see `app.planner.search.search_matched`)
        validation = build_inputs(household, n_paths=1_200, seed=seed + 2_000_003, options=options)
        chosen = search_matched(futures, validation, menu(style=style))[1].strategy
    else:
        chosen = search(futures, strategies=menu(style=style), risk_aversion=risk_aversion, valuation=valuation).best.strategy
    held = build_inputs(household, n_paths=n_eval, seed=seed + EVAL_SEED_OFFSET, options=options)
    policies = [chosen.policy(), *(b.policy for b in BASELINES)]
    extra: dict[str, int] = {}

    def add(name: str, policy) -> None:
        extra[name] = len(policies)
        policies.append(policy)

    if skill:
        add("skill", advisor_allocation_chain(chosen)[-1][1])
    # the typical advisor as it was before its funds paid capital gains distributions, to show what that moves
    add("typical_advisor_no_dist", TYPICAL_ADVISOR.replace(fund_distribution=0.0, fund_distribution_short_term=0.0))
    if giving_share > 0.0:
        add("plan_cash_gifts", chosen.policy().replace(donate_lots=False))
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
        "plan_forced_sale": float(np.mean(batch.forced_years[0] > 0)),
        **plan_exposure(household, chosen),
    }
    for i, baseline in enumerate(BASELINES, start=1):
        adv = compare(batch.wealth[0], batch.wealth[i], years, measure_risk_aversion)
        key = baseline.key
        row[f"{key}_median"] = adv.baseline_median
        row[f"{key}_p10"] = float(np.percentile(batch.wealth[i], 10))
        row[f"{key}_taxes"] = float(np.median(batch.taxes_paid[i] + batch.pretax_owed[i]))
        row[f"{key}_shortfall"] = float(np.mean(batch.unfunded[i] > 0))
        row[f"{key}_forced_sale"] = float(np.mean(batch.forced_years[i] > 0))
        row[f"adv_median_vs_{key}"] = adv.median
        row[f"adv_risk_adjusted_vs_{key}"] = adv.risk_adjusted
        # the same futures with the estate passed to heirs at the horizon (a step-up, the heirs' rate on the pre-tax accounts)
        heirs = compare(batch.wealth_heirs[0], batch.wealth_heirs[i], years, measure_risk_aversion)
        row[f"passed_{key}_median"] = heirs.baseline_median
        row[f"passed_adv_median_vs_{key}"] = heirs.median
        row[f"passed_adv_risk_adjusted_vs_{key}"] = heirs.risk_adjusted
    if options is not None and options.horizon_age is not None:
        # a run to a later age also reports its results at 80 (the app's age), beside the end of the horizon
        for i, baseline in enumerate(BASELINES, start=1):
            at80 = compare(batch.wealth_at_80[0], batch.wealth_at_80[i], household.horizon_years, measure_risk_aversion)
            row[f"at80_adv_median_vs_{baseline.key}"] = at80.median
            row[f"at80_adv_risk_adjusted_vs_{baseline.key}"] = at80.risk_adjusted
        row["at80_plan_median"] = float(np.median(batch.wealth_at_80[0]))
    row["passed_plan_median"] = float(np.median(batch.wealth_heirs[0]))
    row["passed_plan_p10"] = float(np.percentile(batch.wealth_heirs[0], 10))
    j = extra["typical_advisor_no_dist"]
    before = compare(batch.wealth[0], batch.wealth[j], years, measure_risk_aversion)
    before_heirs = compare(batch.wealth_heirs[0], batch.wealth_heirs[j], years, measure_risk_aversion)
    row["adv_median_vs_typical_advisor_no_dist"] = before.median
    row["adv_risk_adjusted_vs_typical_advisor_no_dist"] = before.risk_adjusted
    row["passed_adv_median_vs_typical_advisor_no_dist"] = before_heirs.median
    row["passed_adv_risk_adjusted_vs_typical_advisor_no_dist"] = before_heirs.risk_adjusted
    row["typical_advisor_no_dist_median"] = before.baseline_median
    row["valuation"] = valuation
    row["giving"] = household.goals.charitable_giving
    if giving_share > 0.0:
        k = extra["plan_cash_gifts"]
        row["plan_cash_gifts_median"] = float(np.median(batch.wealth[k]))
        row["passed_plan_cash_gifts_median"] = float(np.median(batch.wealth_heirs[k]))
        row["lots_for_cash_median"] = annualized(float(np.median(batch.wealth[0])), float(np.median(batch.wealth[k])), years)
        row["passed_lots_for_cash_median"] = annualized(float(np.median(batch.wealth_heirs[0])), float(np.median(batch.wealth_heirs[k])), years)
    if skill:
        for i, baseline in enumerate(BASELINES, start=1):
            row[f"skill_median_vs_{baseline.key}"] = annualized(
                float(np.median(batch.wealth[extra["skill"]])), float(np.median(batch.wealth[i])), years
            )
        row["skill_shortfall"] = float(np.mean(batch.unfunded[extra["skill"]] > 0))
    if heirs_rates:
        balances = batch.pretax_balance
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
    skill: bool = False,
    style: str = "balanced",
    valuation: str = "liquidated",
    giving_share: float = 0.0,
    options: ModelOptions | None = None,
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
            household_row(
                items[position], position, n_search, n_eval, risk_aversion, adaptive_paths, measure_risk_aversion, heirs_rates, skill, style,
                valuation, giving_share, options,
            )
        )
        if progress and (position + 1) % 25 == 0:
            elapsed = time.perf_counter() - started
            print(f"  {position + 1}/{len(items)} households ({elapsed / (position + 1 - first):.1f}s each)", flush=True)
        if checkpoint is not None and (position + 1) % 25 == 0:
            pd.DataFrame(rows).to_csv(checkpoint, index=False)
    return pd.DataFrame(rows)


STYLE_NOTES = {
    "equity_first": "; planning style: equity first, a spending reserve with everything else in stocks",
    "liability_matched": "; planning style: liability matched, the reserve chosen to keep forced sales in falling years to 2% of futures and ruin no likelier than the advisor's",
}


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


def valuation_sections(frame: pd.DataFrame) -> list[str]:
    """The advantage under both valuations at the horizon, against both advisors (and the typical advisor as it was before its funds
    paid capital-gains distributions), as the median across the households of each type."""
    cols = [
        ("good_ria", "Good RIA"),
        ("typical_advisor", "Typical advisor (its funds pay distributions)"),
        ("typical_advisor_no_dist", "Typical advisor without distributions"),
    ]
    lines = [
        "## The two valuations at 80, against both advisors",
        "",
        "**Liquidated at 80**: everything is sold and taxed at the horizon. **Passed to heirs at 80**: a step-up in basis on the taxable "
        "account (no tax on its unrealized gain), the Roth as it stands, the pre-tax accounts after a flat 24% tax. Each cell is the "
        "median across the households of the type: the raw (median) advantage, then the risk-adjusted advantage. "
        + ("The plan was chosen for the heirs' valuation. " if "valuation" in frame.columns and (frame["valuation"] == "heirs").all() else "The plan was chosen under the liquidated valuation. "),
        "",
        "| Type | Against | Liquidated: median | Liquidated: risk-adjusted | Heirs: median | Heirs: risk-adjusted |",
        "|---|---|---|---|---|---|",
    ]

    def row(title: str, sub: pd.DataFrame, first: bool) -> list[str]:
        out = []
        for key, label in cols:
            suffix = "" if key != "typical_advisor_no_dist" else ""
            cells = [
                _pct(sub[f"adv_median_vs_{key}"].median()), _pct(sub[f"adv_risk_adjusted_vs_{key}"].median()),
                _pct(sub[f"passed_adv_median_vs_{key}"].median()), _pct(sub[f"passed_adv_risk_adjusted_vs_{key}"].median()),
            ]
            out.append(f"| {title if key == 'good_ria' else ''} | {label}{suffix} | " + " | ".join(cells) + " |")
        return out

    for t, title in hh.TYPES.items():
        lines += row(title, frame[frame["type"] == t], False)
    lines += row(f"**All {len(frame)} households**", frame, True)
    lines.append("")
    return lines


def heirs_sections(frame: pd.DataFrame) -> list[str]:
    """The raw advantage with the pre-tax balance at the horizon taxed at a flat heirs' rate (a sensitivity, not the app's rule)."""
    rates = sorted({int(c.rsplit("heirs", 1)[1]) for c in frame.columns if _HEIRS_RATE_COLUMN.search(c)})
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


def skill_sections(frame: pd.DataFrame) -> list[str]:
    """How much of the advantage over the good RIA is the tools and how much is holding more or less equity than it does."""
    lines = [
        "## How much of the advantage is the tools, and how much is a different amount of equity",
        "",
        "'Tools only' runs the plan's own choices (fee, asset location, conversions, withdrawal order, 401(k) type, goal funding, direct indexing) "
        "with the good RIA's allocation (80% stocks today falling to 50% from 70, no private credit), so it differs from the advisor in nothing "
        "else. The rest of the plan's advantage comes from its different stock share and private credit sleeve, which is a different amount of risk. "
        "Cells are medians across the households of the type; stocks are a share of the whole portfolio.",
        "",
        "| Type | Plan: stocks today / from 70 | Plan: raw advantage | Tools only: raw advantage | From the allocation | Chance of running out: plan / tools only / good RIA |",
        "|---|---|---|---|---|---|",
    ]

    def row(title: str, sub: pd.DataFrame) -> str:
        plan, tools = sub["adv_median_vs_good_ria"], sub["skill_median_vs_good_ria"]
        return (
            f"| {title} | {sub['plan_equity_today'].median():.0%} / {sub['plan_equity_from_70'].median():.0%} | {_pct(plan.median())} | "
            f"{_pct(tools.median())} ({_pct(tools.quantile(0.1))} to {_pct(tools.quantile(0.9))}) | {_pct((plan - tools).median())} | "
            f"{sub['plan_shortfall'].mean() * 100:.1f}% / {sub['skill_shortfall'].mean() * 100:.1f}% / {sub['good_ria_shortfall'].mean() * 100:.1f}% |"
        )

    for t, title in hh.TYPES.items():
        lines.append(row(title, frame[frame["type"] == t]))
    lines += [row(f"**All {len(frame)} households**", frame), ""]
    return lines


def summarize(
    frame: pd.DataFrame,
    n_eval: int,
    risk_aversion: float,
    measure_risk_aversion: float | None = None,
    style: str = "balanced",
    valuations: bool = False,
) -> str:
    """The study's report. `valuations` adds the table of the two valuations at 80 (the frame always has their columns)."""
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
        f"futures it never saw ({setting}{STYLE_NOTES.get(style, '')}). Nothing was tuned; the households were drawn from fixed ranges",
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
    if "choice_reserve" in frame.columns and (frame["choice_reserve"].astype(str) != "off").any():
        lines += [
            "",
            "Spending reserve chosen, by type (years of expenses held in bonds and private credit, everything else in stocks):",
            "",
            "| Type | 2 years | 4 years | 6 years |",
            "|---|---|---|---|",
        ]
        for t, title in hh.TYPES.items():
            sub = frame[frame["type"] == t]
            cells = " | ".join(f"{_share(sub, 'choice_reserve', lambda v, y=years: str(v) == y) * 100:.0f}%" for years in ("2", "4", "6"))
            lines.append(f"| {title} | {cells} |")
    if "judgment_median" in frame.columns:
        lines += [""] + adaptive_sections(frame)
    if "skill_median_vs_good_ria" in frame.columns:
        lines += [""] + skill_sections(frame)
    if valuations and "passed_adv_median_vs_good_ria" in frame.columns:
        lines += [""] + valuation_sections(frame)
    if any(_HEIRS_RATE_COLUMN.search(c) for c in frame.columns):
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
    parser.add_argument("--style", choices=("balanced", "equity_first", "liability_matched"), default="balanced", help="the planning style whose strategy menu the planner searches")
    parser.add_argument("--skill", action="store_true", help="also run each plan's tools at the good RIA's allocation (the part of the advantage that is not extra equity)")
    parser.add_argument("--valuation", choices=("liquidated", "heirs"), default="liquidated", help="the wealth the planner maximizes at the horizon")
    parser.add_argument("--giving-share", type=float, default=0.0, help="share of wages every household gives to charity a year")
    parser.add_argument("--horizon-age", type=int, default=None, help="simulate to this age (default 80); the rows then also carry the results at 80")
    parser.add_argument("--no-survivor", action="store_true", help="keep the couple joint to the end (the engine before the survivor phase)")
    parser.add_argument("--valuations", action="store_true", help="add the table of the two valuations at 80 (liquidated, passed to heirs) to the report")
    args = parser.parse_args(argv)
    frame = run(
        per_type=args.per_type, n_eval=args.n_eval, seed=args.seed, progress=True,
        adaptive_paths=args.adaptive_paths, checkpoint=args.checkpoint, risk_aversion=args.risk_aversion,
        measure_risk_aversion=args.measure_risk_aversion, heirs_rates=tuple(args.heirs_rates), skill=args.skill,
        style=args.style, valuation=args.valuation, giving_share=args.giving_share,
        options=ModelOptions(survivor=not args.no_survivor, horizon_age=args.horizon_age),
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out_dir / "household_study.csv", index=False)
    text = summarize(frame, args.n_eval, args.risk_aversion, args.measure_risk_aversion, args.style, args.valuations)
    (args.out_dir / "household_study.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
