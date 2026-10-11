"""Which household should the showcase be about? A short list from the 300-household study.

The list is the five households with the highest raw median advantage over the good advisor, in the study, that are plausible
and can be named as a type. "Plausible" is decided from the household alone, never from a result, by the screens below (written
before the list was looked at): ordinary ages, incomes and savings, a taxable account that is not nearly all gain and not nearly
all of the savings, a retirement that can be funded by the household and by the advisor alike, goals that are not larger than
what is saved for them. The study ranks households on 1,000 futures each, and the best of 300 is partly lucky, so each of the
twelve best that pass is measured again on 2,000 other futures (the showcase's own, `app.showcase`) that played no part in
choosing it. The list keeps the study's order, so the figure measured on the fresh futures, which is the one the showcase
shows, is not itself a winner of anything; ranking on it too would pick the luckiest twice. Each household is listed with what it
is worth and what it is made of. Nothing is tuned.

    python -m app.study.showcase_pick --out ../reports/showcase_candidates.md --fixtures ../reports/showcase_candidates
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app import showcase
from app.study import households
from app.study.households import TYPES, StudyHousehold

DEFAULT_CSV = Path(__file__).resolve().parents[3] / "reports" / "household_study_equity_first" / "household_study.csv"

SCREENS = (
    ("a primary earner aged 35 to 60", lambda r, h: 35 <= h.primary_age <= 60),
    ("household wages of $90,000 to $750,000 a year", lambda r, h: 90_000 <= h.total_wages <= 750_000),
    ("savings of $0.5 million to $15 million", lambda r, h: 500_000 <= h.liquid_wealth <= 15_000_000),
    ("a taxable account that is at most 85% unrealized gain", lambda r, h: r["basis_ratio"] >= 0.15),
    ("a taxable account that is at most 70% of savings", lambda r, h: h.accounts.brokerage_value <= 0.70 * h.liquid_wealth),
    ("retirement spending between $25,000 and the household's wages", lambda r, h: 25_000 <= h.goals.retirement_spending <= h.total_wages),
    (
        "a home purchase of at most 60% of the money outside retirement accounts",
        lambda r, h: h.goals.home_purchase_in_years is None
        or h.goals.home_down_payment <= 0.6 * (h.accounts.brokerage_value + h.accounts.cash),
    ),
    ("a plan the household can fund (not underfunded)", lambda r, h: not bool(r["underfunded"])),
    ("at most a 5% chance of running out of money, for the plan and for the advisor", lambda r, h: r["plan_shortfall"] <= 0.05 and r["good_ria_shortfall"] <= 0.05),
)

# Fictional names, in the order candidates are listed: (family, first names of the earners).
NAMES = (
    ("Okafor", ("Chidi", "Amara")),
    ("Lindqvist", ("Anders", "Maja")),
    ("Moreau", ("Julien", "Camille")),
    ("Tanaka", ("Kenji", "Yuki")),
    ("Haddad", ("Samir", "Leila")),
    ("Castellanos", ("Mateo", "Lucia")),
    ("Whitfield", ("Graham", "Eleanor")),
    ("Novak", ("Tomas", "Petra")),
    ("Adeyemi", ("Tunde", "Folake")),
    ("Brennan", ("Declan", "Siobhan")),
    ("Iyer", ("Arjun", "Meera")),
    ("Santos", ("Rafael", "Beatriz")),
)

TYPE_BLURB = {
    "diversified": "diversified savers",
    "concentrated": "a concentrated single-stock position",
    "big_gains": "large unrealized gains",
    "early_retirement": "early retirement",
    "large_purchase": "a large purchase ahead",
    "high_earner": "high earners with large pre-tax balances",
}


@dataclass
class Candidate:
    rank: int
    row: pd.Series
    study: StudyHousehold
    name: str
    fixture: showcase.Fixture
    analysis: showcase.ShowcaseAnalysis
    strategy_sentence: str


def load_study(csv: Path) -> pd.DataFrame:
    return pd.read_csv(csv)


def reconstruct(frame: pd.DataFrame, seed: int = 10, per_type: int = 50) -> dict[tuple[str, int], StudyHousehold]:
    """The study's households, rebuilt from the generator (checked against the CSV's own columns)."""
    built = {(h.type, h.index): h for h in households.generate(seed=seed, per_type=per_type)}
    for _, row in frame.iterrows():
        h = built[(row["type"], int(row["index"]))].household
        if abs(h.total_wages - row["wages"]) > 1.0 or abs(h.liquid_wealth - row["liquid_wealth"]) > 1.0:
            raise ValueError(f"the generator no longer gives the study's household {row['type']} {row['index']}")
    return built


def screen(frame: pd.DataFrame, built: dict[tuple[str, int], StudyHousehold]) -> tuple[pd.DataFrame, list[tuple[str, int]]]:
    """The households that pass every screen, and how many each screen removed on its own."""
    keep = np.ones(len(frame), dtype=bool)
    removed: list[tuple[str, int]] = []
    for label, test in SCREENS:
        passes = np.array([bool(test(row, built[(row["type"], int(row["index"]))].household)) for _, row in frame.iterrows()])
        removed.append((label, int((~passes).sum())))
        keep &= passes
    return frame[keep], removed


def _name_household(study: StudyHousehold, naming: tuple[str, tuple[str, str]]):
    family, firsts = naming
    h = study.household.model_copy(deep=True)
    for person, first in zip(h.people, firsts, strict=False):
        person.name = f"{first} {family}"
    return h


def describe(study: StudyHousehold) -> str:
    h = study.household
    a, g = h.accounts, h.goals
    ages = " and ".join(str(p.age) for p in h.people)
    earners = "two earners" if len(h.people) == 2 else "one earner"
    kids = f", {len(h.children_ages)} child{'ren' if len(h.children_ages) > 1 else ''}" if h.children_ages else ""
    gain = max(0.0, a.brokerage_value - a.brokerage_basis)
    parts = [
        f"{earners} aged {ages}{kids}, ${h.total_wages / 1000:,.0f}k of wages, ${h.liquid_wealth / 1e6:,.2f}M saved "
        f"(${a.brokerage_value / 1e6:,.2f}M taxable with ${gain / 1e6:,.2f}M of unrealized gain, ${a.pretax_balance / 1e6:,.2f}M pre-tax, "
        f"${a.roth_balance / 1e6:,.2f}M Roth)",
        f"retiring at {g.retirement_age} on ${g.retirement_spending / 1000:,.0f}k a year",
    ]
    if g.home_purchase_in_years is not None and g.home_down_payment > 0:
        parts.append(f"a ${g.home_down_payment / 1000:,.0f}k home purchase in {g.home_purchase_in_years} years")
    if g.college_starts_in_years is not None and g.college_annual_cost > 0:
        parts.append(f"college from year {g.college_starts_in_years}")
    return "; ".join(parts) + "."


def remeasure(frame: pd.DataFrame, built, count: int) -> list[Candidate]:
    pool = frame.sort_values("adv_median_vs_good_ria", ascending=False).head(count)
    showcase.reset()
    measured: list[Candidate] = []
    for _, row in pool.iterrows():
        study = built[(row["type"], int(row["index"]))]
        fixture = showcase.Fixture(
            id=f"{row['type']}-{int(row['index'])}", name="", type_label=TYPES[row["type"]], tagline="", household=study.household
        )
        prepared = showcase.prepare(fixture)
        analysis = showcase.analyze(prepared)
        measured.append(Candidate(0, row, study, "", fixture, analysis, prepared.strategy.short_label()))
    # `measured` keeps the study's order: the rank is the study's, never the fresh futures' (see the module's note on picking twice).
    for rank, c in enumerate(measured, start=1):
        # Names go by rank, so the list reads the same however the pool was drawn (they play no part in the simulation).
        naming = NAMES[(rank - 1) % len(NAMES)]
        c.rank, c.name = rank, naming[0]
        c.fixture = c.fixture.model_copy(update={"name": f"The {naming[0]} family", "household": _name_household(c.study, naming)})
    return measured


def _pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def _usd(x: float) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def render(frame_all: pd.DataFrame, passed: pd.DataFrame, removed, candidates: list[Candidate], seconds: float | None = None) -> str:
    lines = [
        "# Showcase household: five candidates",
        "",
        "Generated by `python -m app.study.showcase_pick` from the 300-household study (equity-first planning style, after tax lots). "
        "The households are fictional and the families' names are made up.",
        "",
        "**How the list was made.** Households were screened for plausibility from their own numbers (never from a result):",
        "",
        *[f"* {label}" + f" (removes {n} of {len(frame_all)} on its own)" for label, n in removed],
        "",
        f"{len(passed)} of {len(frame_all)} households pass all of them. The five with the highest raw median advantage *in the study* "
        "are listed, in the study's order. The study ranks households on 1,000 futures each, so the best of 300 is partly lucky: "
        f"each of the {len(candidates)} best was therefore measured again on 2,000 other futures (the showcase's own), which played no part in "
        "choosing it. The figure measured there is the one the showcase shows, and it is not itself picked as a winner. Raw advantage is the "
        "annual growth-rate difference of median after-tax wealth at 80 against the good advisor; risk-adjusted is the same on "
        "certainty-equivalent wealth at risk aversion 3.",
        "",
        "| # | Household | Type | Raw advantage (2,000 fresh futures) | In the study (picked on) | Risk-adjusted | Dollars more at 80 | Runs out of money: plan / advisor |",
        "|---|---|---|---|---|---|---|---|",
    ]
    top = candidates[:5]
    for c in top:
        a = c.analysis.advantage
        lines.append(
            f"| {c.rank} | The {c.name} family | {TYPES[c.row['type']]} | **{_pct(a.median_rate)}** | {_pct(c.row['adv_median_vs_good_ria'])} | "
            f"{_pct(a.risk_adjusted_rate)} | ${a.median_dollars:,.0f} | {a.plan_shortfall:.1%} / {a.advisor_shortfall:.1%} |"
        )
    lines.append("")
    for c in top:
        a = c.analysis.advantage
        biggest = sorted(c.analysis.bars, key=lambda b: b.delta_rate, reverse=True)[:3]
        lines += [
            f"## {c.rank}. The {c.name} family: {TYPE_BLURB[c.row['type']]}",
            "",
            f"* **Who:** {describe(c.study)}",
            f"* **The plan:** {c.strategy_sentence}.",
            f"* **Against the good advisor:** {_pct(a.median_rate)} a year in median after-tax wealth at 80 (${a.median_dollars:,.0f} more: "
            f"${a.plan_median_at_horizon:,.0f} against ${a.advisor_median_at_horizon:,.0f}), {_pct(a.risk_adjusted_rate)} risk-adjusted; "
            f"10th percentile ${a.plan_p10_at_horizon:,.0f} against ${a.advisor_p10_at_horizon:,.0f}; runs out of money in "
            f"{a.plan_shortfall:.1%} of futures against {a.advisor_shortfall:.1%}.",
            "* **Where it comes from:** " + "; ".join(f"{b.label} {_pct(b.delta_rate)} a year ({_usd(b.delta_dollars)})" for b in biggest) + ".",
            "* **Tax lots:** " + (
                f"selling the highest-cost lots first is worth {_pct(lots.delta_rate)} a year ({_usd(lots.delta_dollars)}) of that."
                if (lots := next((b for b in c.analysis.bars if b.key == "lots"), None)) is not None
                else "not used."
            ),
            "",
        ]
    if candidates[5:]:
        lines += [
            "Next in the study's order, also measured on the fresh futures (study / fresh): "
            + ", ".join(
                f"The {c.name} family ({TYPES[c.row['type']].split(' (')[0].lower()}, {_pct(c.row['adv_median_vs_good_ria'])} / "
                f"{_pct(c.analysis.advantage.median_rate)})"
                for c in candidates[5:]
            )
            + ".",
            "",
        ]
    if seconds is not None:
        lines.append(f"_Computed in {seconds:,.0f} seconds._")
    return "\n".join(lines).rstrip() + "\n"


def write_fixtures(candidates: list[Candidate], folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for c in candidates[:5]:
        fixture = c.fixture.model_copy(
            update={
                "id": c.name.lower(),
                "tagline": describe(c.study),
            }
        )
        path = folder / f"{c.rank}_{c.name.lower()}.json"
        path.write_text(json.dumps(json.loads(fixture.model_dump_json()), indent=2) + "\n")
        paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--pool", type=int, default=12, help="how many of the study's best are measured again")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--fixtures", type=Path, default=None, help="write each listed household as a showcase fixture here")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    frame = load_study(args.csv)
    built = reconstruct(frame)
    passed, removed = screen(frame, built)
    candidates = remeasure(passed, built, args.pool)
    text = render(frame, passed, removed, candidates, time.perf_counter() - started)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    if args.fixtures:
        write_fixtures(candidates, args.fixtures)
    print(text)


if __name__ == "__main__":
    main()
