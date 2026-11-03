"""A search over plausible households for the showcase: which one shows the most Waramoug can do?

Only the household varies. The engine, its assumptions and the planner are used exactly as the app uses them; the one thing added around
them is the cost of moving into direct indexing: the engine opens its direct-indexed book with the opening brokerage position at its
existing cost basis (nothing is sold), but a household holding funds has to sell them to hold individual stocks, so a strategy with direct
indexing is run on the household AFTER that sale (the tax on the gain, federal with the investment-income tax plus Illinois, taken out of
the proceeds, the basis reset to market) and the advisor on the household as it is.

Plausibility. Every candidate is checked before it is scored (`plausibility`). The Federal Reserve's data host is not reachable from this
environment, so the SCF anchors below are the 2022 Survey of Consumer Finances figures as published in secondary summaries (retrieved by
web search; not checked against the Fed's own tables or the microdata). Checks that are rules of thumb rather than SCF figures are named
as such in their `source`.
"""

from __future__ import annotations

import dataclasses
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.planner.baseline import RIA_BASELINE
from app.planner.search import FORCED_SALE_LIMIT
from app.planner.strategies import Strategy
from app.schemas import Accounts, Goals, Household, Person, SocialSecurity
from app.sim import simulate as S
from app.sim.simulate import build_inputs, run_batch
from app.tax import params_2026 as P
from app.tax.engine import TaxInputs, compute_return

SEED = 2026

# --- SCF 2022 anchors (published summaries; see the module docstring) -------------------------------------------------------------
SCF_MEDIAN_FAMILY_INCOME = 70_260.0  # all families, 2021 income in 2022 dollars
SCF_TOP10_INCOME = 248_600.0  # minimum family income of the top 10%
SCF_P90_NET_WORTH = {  # 90th percentile of net worth by age of head (2022 dollars): 35-44, 45-49, 45-54 (taken for 50-54), 55-64, 60-64
    range(35, 45): 1_170_000.0,
    range(45, 50): 1_420_000.0,
    range(50, 55): 1_990_000.0,
    range(55, 60): 2_500_000.0,
    range(60, 65): 3_040_000.0,
}
SCF_RETIREMENT_MEDIAN_HOLDERS = {range(35, 45): 45_000.0, range(45, 55): 115_000.0, range(55, 65): 185_000.0}  # median among families with accounts
SCF_RETIREMENT_TOP_SHARE = 1_000_000.0  # fewer than 10% of households in any age group hold more than this in retirement accounts (9.2% at 55-64)
MAX_WAGES = 500_000.0
K401_LIMIT = 24_500.0  # the engine's own limit (the 401(k) contribution the planner assumes)
BROKERAGE_SAVINGS_SHARE = S.BROKERAGE_SAVINGS_SHARE
KEEP_401K_SHARE = S.KEEP_401K_SHARE_OF_WAGES


def _lookup(table: dict, age: int) -> float | None:
    for rng, value in table.items():
        if age in rng:
            return value
    return None


# --- the household as a profile ---------------------------------------------------------------------------------------------------
SS_BEND = (1_286.0, 7_749.0)  # 2026 PIA bend points (monthly)
SS_WAGE_BASE = 184_500.0


def ss_benefit(wages: float, age: int, retirement_age: int) -> float:
    """A yearly Social Security benefit at 67 from the SSA formula, for steady real wages from 22 to the retirement age (35 best years)."""
    years = max(1, min(35, retirement_age - 22))
    aime = min(wages, SS_WAGE_BASE) * years / 35.0 / 12.0
    b1, b2 = SS_BEND
    pia = 0.9 * min(aime, b1) + 0.32 * max(0.0, min(aime, b2) - b1) + 0.15 * max(0.0, aime - b2)
    return round(12.0 * pia, 2)


@dataclass(frozen=True)
class Profile:
    age: int
    wages: float
    retirement_age: int
    spend_ratio: float
    pretax: float
    roth: float
    brokerage: float
    basis_ratio: float
    cash: float
    college: tuple[int, float] | None  # (starts in years, a year)
    home: tuple[int, float] | None  # (in years, down payment)
    giving: float

    def household(self) -> Household:
        college_years = 4
        child_age = max(0, 18 - self.college[0]) if self.college else 8
        goals = Goals(
            home_purchase_in_years=self.home[0] if self.home else None,
            home_down_payment=self.home[1] if self.home else 120_000.0,
            college_starts_in_years=self.college[0] if self.college else None,
            college_annual_cost=self.college[1] if self.college else 35_000.0,
            college_years=college_years if self.college else 0,
            retirement_age=self.retirement_age,
            retirement_spending=round(self.spend_ratio * self.wages, 2),
            charitable_giving=self.giving,
        )
        return Household(
            people=[Person(name="John Smith", age=self.age, wages=self.wages, pretax_401k=0.0)],
            children_ages=[child_age],
            accounts=Accounts(
                brokerage_value=self.brokerage, brokerage_basis=round(self.brokerage * self.basis_ratio, 2), pretax_balance=self.pretax,
                pretax_equity_share=0.6, roth_balance=self.roth, roth_equity_share=1.0, cash=self.cash,
            ),
            goals=goals,
            social_security=SocialSecurity(annual_benefit=ss_benefit(self.wages, self.age, self.retirement_age), start_age=67),
        )


# --- plausibility -------------------------------------------------------------------------------------------------------------------


def plausibility(p: Profile) -> dict[str, tuple[bool, str, str]]:
    """Every check as {name: (passed, detail, source)}."""
    out: dict[str, tuple[bool, str, str]] = {}
    retirement = p.pretax + p.roth
    financial = retirement + p.brokerage + p.cash
    p90 = _lookup(SCF_P90_NET_WORTH, p.age)
    ratio = (p90 / SCF_TOP10_INCOME) if p90 else None
    hold = _lookup(SCF_RETIREMENT_MEDIAN_HOLDERS, min(p.age, 64))
    saving = (min(K401_LIMIT, KEEP_401K_SHARE * p.wages) + BROKERAGE_SAVINGS_SHARE * p.wages) / p.wages

    def add(name, ok, detail, source):
        out[name] = (bool(ok), detail, source)

    add("income", SCF_MEDIAN_FAMILY_INCOME <= p.wages <= MAX_WAGES, f"wages ${p.wages:,.0f} (SCF median ${SCF_MEDIAN_FAMILY_INCOME:,.0f}, top-10% from ${SCF_TOP10_INCOME:,.0f}; cap ${MAX_WAGES:,.0f})", "SCF 2022")
    add("retirement accounts below the top decile", retirement <= SCF_RETIREMENT_TOP_SHARE, f"401(k)/IRA + Roth ${retirement:,.0f} (fewer than 10% of households in any age group hold over ${SCF_RETIREMENT_TOP_SHARE:,.0f})", "SCF 2022 (CRS)")
    add("retirement accounts at least the holders' median", hold is not None and retirement >= hold, f"${retirement:,.0f} against the median ${hold:,.0f} among families with accounts at this age" if hold else "age outside the table", "SCF 2022")
    add("financial assets below age p90 net worth", p90 is not None and financial <= p90, f"financial assets ${financial:,.0f} against the age-group 90th percentile of NET WORTH ${p90:,.0f}" if p90 else "age outside the table", "SCF 2022")
    add("financial assets in line with income", ratio is not None and financial <= ratio * p.wages, f"{financial / p.wages:.1f}x income against at most {ratio:.1f}x (age p90 net worth / top-10% income)" if ratio else "n/a", "SCF 2022 (derived)")
    add("windfall or cash within a year's income", p.cash <= p.wages, f"cash ${p.cash:,.0f} against income ${p.wages:,.0f}", "rule of thumb")
    add("cost basis between 20% and 100% of value", p.brokerage == 0 or 0.2 <= p.basis_ratio <= 1.0, f"basis {p.basis_ratio:.0%} of value", "rule of thumb")
    add("implied saving rate at most 30%", saving <= 0.30, f"the engine saves {saving:.0%} of wages (401(k) up to ${K401_LIMIT:,.0f} + 10% in the brokerage account)", "engine assumption; rule of thumb")
    add("retirement spending 35% to 65% of wages", 0.35 <= p.spend_ratio <= 0.65, f"{p.spend_ratio:.0%} of wages", "rule of thumb")
    add("retirement age", 55 <= p.retirement_age <= 70 and p.retirement_age >= p.age + 3, f"retire at {p.retirement_age} from {p.age}", "rule of thumb")
    if p.home:
        add("home down payment fundable", p.home[1] <= p.brokerage + p.cash and p.home[1] <= 1.0 * p.wages, f"down payment ${p.home[1]:,.0f} against liquid ${p.brokerage + p.cash:,.0f} and income ${p.wages:,.0f}", "rule of thumb")
    if p.college:
        add("college cost a year", 25_000 <= p.college[1] <= 80_000, f"${p.college[1]:,.0f} a year starting in {p.college[0]} years", "rule of thumb")
    if p.giving:
        add("giving at most 10% of wages", p.giving <= 0.10 * p.wages, f"${p.giving:,.0f} = {p.giving / p.wages:.1%} of wages", "rule of thumb")
    return out


def plausible(p: Profile) -> bool:
    try:
        p.household()
    except ValueError:
        return False
    return all(ok for ok, _, _ in plausibility(p).values())


# --- the cost of moving into direct indexing -----------------------------------------------------------------------------------------


def transition(h: Household) -> tuple[Household, float]:
    """The household after selling its brokerage funds to hold individual stocks: the tax on the gain (the incremental year-one tax of the
    federal return with the investment-income tax, plus Illinois, at this household's income) comes out of the proceeds, and the basis is
    reset to market. Returns the household and the tax."""
    a = h.accounts
    gain = max(0.0, a.brokerage_value - a.brokerage_basis)
    if gain <= 0.0:
        return h, 0.0
    wages = h.people[0].wages - min(K401_LIMIT, KEEP_401K_SHARE * h.people[0].wages)

    def tax(g: float) -> float:
        r = compute_return(
            TaxInputs(
                wages=wages, interest=0.0175 * a.cash, qualified_dividends=S.markets.DIVIDEND_YIELD * a.brokerage_value,
                ordinary_dividends=S.markets.DIVIDEND_YIELD * a.brokerage_value, net_capital_gain=g, children_under_17=sum(1 for c in h.children_ages if c <= P.CTC_MAX_CHILD_AGE),
            )
        )
        return r.federal_total + r.illinois_tax

    owed = tax(gain) - tax(0.0)
    data = h.model_dump()
    value = a.brokerage_value - owed
    data["accounts"]["brokerage_value"] = value
    data["accounts"]["brokerage_basis"] = value
    return Household.model_validate(data), owed


# --- scoring ----------------------------------------------------------------------------------------------------------------------------


def _futures(h: Household, n: int, offset: int = 0, job_loss=None):
    kw = {"job_loss": job_loss} if job_loss else {}
    return build_inputs(h, n_paths=n, seed=SEED + offset, **kw)


QUICK_STRATEGIES = [
    Strategy(1.0, conv, 0.15, di, False, "pretax", "sell", reserve_years=years)
    for years in (2, 6, 12)
    for conv in ("fill22_every", "fill24_every")
    for di in (False, True)
]


QUICK_OFFSET = 4_000_039  # the futures of the search itself (the quick scores and the climb): seed offset, apart from the finalist and final sets


def quick_score(p: Profile, n: int = 300, offset: int = QUICK_OFFSET) -> dict:
    """A fast score: the best of a few typical strategies (direct indexing after its transition tax) against the advisor, on `n` futures."""
    h = p.household()
    hd, tax = transition(h)
    years = h.horizon_years
    fut = _futures(h, n, offset)
    adv = run_batch(fut, [RIA_BASELINE])
    advisor = float(np.median(adv.wealth[0]))
    advisor_ruin = float(np.mean(adv.unfunded[0] > 0))
    off = [s for s in QUICK_STRATEGIES if not s.direct_indexing]
    on = [s for s in QUICK_STRATEGIES if s.direct_indexing]
    # the planner's own limits, screened on these few futures with slack: the chance of selling stocks in a falling year for goals or spending
    # at most 2%, and the chance of running out of money no higher than the advisor's (the hard limits, on the search futures)
    candidates = []
    for batch, strategies in ((run_batch(fut, [s.policy() for s in off]), off),) + (
        ((run_batch(_futures(hd, n, offset), [s.policy() for s in on]), on),) if tax >= 0.0 and on else ()
    ):
        for i, strat_ in enumerate(strategies):
            ok = float(np.mean(batch.forced_years[i] > 0)) <= FORCED_SALE_LIMIT and float(np.mean(batch.unfunded[i] > 0)) <= advisor_ruin
            candidates.append((float(np.median(batch.wealth[i])), strat_, ok))
    pool = [c for c in candidates if c[2]]
    feasible = bool(pool)
    best, strategy, _ = max(pool or candidates, key=lambda m: m[0])
    rate = (best / advisor) ** (1.0 / years) - 1.0 if feasible and best > 0 and advisor > 0 else -1.0
    return {"rate": rate, "wealth": best, "advisor": advisor, "advisor_ruin": advisor_ruin, "spending": h.goals.retirement_spending, "tax": tax, "strategy": strategy.key, "feasible": feasible}


ADVISOR_CUSHION = 10.0  # the standard advisor's median wealth at 80 must be at least this many years of retirement spending ...
ADVISOR_MAX_RUIN = 0.10  # ... and it may run out of money in at most this share of futures: a percentage gap over an advisor whose household is
# broke (a base near zero) is an artifact of the base, not a result


def funded(row: dict) -> bool:
    """Is the household one the standard advisor can actually fund? (rows scored before the ruin was recorded are judged on the cushion alone)"""
    return row.get("feasible", False) and row["advisor"] >= ADVISOR_CUSHION * row["spending"] and row.get("advisor_ruin", 0.0) <= ADVISOR_MAX_RUIN


# --- sampling ---------------------------------------------------------------------------------------------------------------------------

GRID = {
    "age": [40, 42, 44, 46, 48, 49, 50, 51, 52, 54, 56, 58, 60],
    "wages": [100_000.0, 150_000.0, 204_268.12, 250_000.0, 275_000.0, 300_000.0, 325_000.0, 350_000.0, 400_000.0, 500_000.0],
    "retirement_age": [55, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 70],
    "spend_ratio": [0.35, 0.40, 0.44, 0.50, 0.55],
    "pretax": [100_000.0, 250_000.0, 429_185.46, 600_000.0, 800_000.0, 1_000_000.0],
    "roth": [0.0, 50_000.0, 94_380.32, 200_000.0, 400_000.0],
    "brokerage": [0.0, 100_000.0, 300_000.0, 645_776.59, 800_000.0, 1_000_000.0, 1_250_000.0, 1_500_000.0],
    "basis_ratio": [0.25, 0.4, 0.6, 0.8, 1.0],
    "cash": [10_000.0, 23_940.44, 40_000.0, 60_000.0, 100_000.0, 150_000.0, 300_000.0],
    "college": [None, (3, 44_539.62), (8, 44_539.62), (8, 60_000.0), (12, 44_539.62)],
    "home": [None, (2, 150_000.0), (3, 100_000.0), (3, 150_000.0), (4, 150_000.0), (5, 150_000.0), (5, 250_000.0)],
    "giving": [0.0, 5_000.0, 10_000.0, 25_000.0],
}


def sample(rng: random.Random) -> Profile:
    return Profile(**{k: rng.choice(v) for k, v in GRID.items()})


def neighbours(p: Profile):
    """Every profile one grid step away from `p` in one parameter."""
    for key, values in GRID.items():
        current = getattr(p, key)
        if current not in values:
            continue
        i = values.index(current)
        for j in (i - 1, i + 1):
            if 0 <= j < len(values):
                yield dataclasses.replace(p, **{key: values[j]})


def to_json(p: Profile) -> dict:
    return dataclasses.asdict(p)


def from_json(d: dict) -> Profile:
    d = dict(d)
    for k in ("college", "home"):
        d[k] = tuple(d[k]) if d[k] is not None else None
    return Profile(**d)


# --- command line -----------------------------------------------------------------------------------------------------------------------


def cmd_sample(args: list[str]) -> None:
    """sample SHARD N OUT: score N random plausible profiles."""
    shard, n, out = int(args[0]), int(args[1]), Path(args[2])
    rng = random.Random(1000 + shard)
    done = 0
    tried = 0
    with out.open("a") as f:
        while done < n:
            p = sample(rng)
            tried += 1
            if not plausible(p):
                continue
            try:
                s = quick_score(p)
            except Exception as exc:  # a profile the engine rejects
                print("skip", exc, file=sys.stderr)
                continue
            f.write(json.dumps({"profile": to_json(p), **s}) + "\n")
            f.flush()
            done += 1
            if done % 25 == 0:
                print(f"shard {shard}: {done}/{n} scored ({tried} drawn)", flush=True)


def cmd_rescore(args: list[str]) -> None:
    """rescore IN OUT SHARD SHARDS: score the profiles of IN again (this module's current rules) and write them to OUT."""
    src, out, shard, shards = Path(args[0]), Path(args[1]), int(args[2]), int(args[3])
    rows = [json.loads(line) for line in src.read_text().splitlines() if line.strip()][shard::shards]
    with out.open("a") as f:
        for i, r in enumerate(rows):
            try:
                sc = quick_score(from_json(r["profile"]))
            except Exception:
                continue
            f.write(json.dumps({"profile": r["profile"], **sc}) + "\n")
            f.flush()
            if (i + 1) % 25 == 0:
                print(f"shard {shard}: {i + 1}/{len(rows)}", flush=True)


def cmd_climb(args: list[str]) -> None:
    """climb IN OUT TOP ROUNDS: from the best profiles in IN, score neighbours (plausible ones) and keep improving."""
    src, out, top, rounds = Path(args[0]), Path(args[1]), int(args[2]), int(args[3])
    rows = [json.loads(line) for line in src.read_text().splitlines() if line.strip()]
    seen = {json.dumps(r["profile"], sort_keys=True) for r in rows}
    for r in rows:
        r.setdefault("spending", from_json(r["profile"]).household().goals.retirement_spending)
    rows = [r for r in rows if funded(r)]
    rows.sort(key=lambda r: -r["rate"])
    frontier = rows[:top]
    with out.open("a") as f:
        for rnd in range(rounds):
            fresh = []
            for r in frontier:
                for q in neighbours(from_json(r["profile"])):
                    key = json.dumps(to_json(q), sort_keys=True)
                    if key in seen or not plausible(q):
                        continue
                    seen.add(key)
                    try:
                        s = quick_score(q)
                    except Exception:
                        continue
                    row = {"profile": to_json(q), **s}
                    f.write(json.dumps(row) + "\n")
                    f.flush()
                    if funded(row):
                        fresh.append(row)
            pool = sorted(frontier + fresh, key=lambda r: -r["rate"])
            frontier = pool[:top]
            print(f"round {rnd + 1}: {len(fresh)} new, best {frontier[0]['rate']:.3%}", flush=True)


if __name__ == "__main__":
    {"sample": cmd_sample, "climb": cmd_climb, "rescore": cmd_rescore}[sys.argv[1]](sys.argv[2:])
