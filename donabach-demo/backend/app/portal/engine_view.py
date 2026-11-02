"""The customer's view of a plan: every figure comes from the engine's own run of the household, computed once here.

`compute_plan` runs the real planner (the liability-matched search on the household, with the event applied to every simulated future) and
measures the plan and the standard advisor on 2,000 futures the search never saw, exactly as the showcase does. `build_plan` then turns
the engine's deterministic year-by-year log into the portfolio screens. Nothing is typed in: where a figure is finer-grained than the engine
(fund names, sectors, regions, the US / international split) it comes from `app.portal.illustrative` and the field says so.

How a plan is chosen when the household changes: the search is re-run on the changed household. The strategy the customer already has is
kept unless the new one is clearly better (its median advantage over the current one is above the sampling noise of the 2,000 futures,
the lower end of the 90% range of the bootstrap) or the current one no longer meets the limits it was chosen under. A change that moves
the strategy by less than the noise of the measurement does not rebuild the portfolio.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass

import numpy as np


from app.planner.baseline import RIA_BASELINE
from app.planner.plan import EVAL_SEED_OFFSET, VALIDATION_PATHS, VALIDATION_SEED_OFFSET
from app.planner.search import FORCED_SALE_LIMIT, search_matched
from app.planner.strategies import Strategy, menu
from app.portal import illustrative as ill
from app.portal.models import (
    AccountHoldings,
    AdvisorCard,
    AssetRow,
    BarRow,
    BracketStep,
    BracketView,
    Comparison,
    ConversionRow,
    GoalCard,
    GoalMarker,
    GoalsTab,
    HoldingRow,
    HoldingsTab,
    IncomeRow,
    Location,
    LocationRow,
    Mix,
    MixChange,
    MixShare,
    Move,
    MoveChange,
    Overview,
    Plan,
    Portfolio,
    ProjectionPoint,
    RequiredWithdrawals,
    RetirementTab,
    StockRow,
    Summary,
    TaxesTab,
    TaxesThisYear,
    WhatChanged,
)
from app.schemas import HORIZON_AGE, Household, JobLoss
from app.sim import markets
from app.sim import simulate as S
from app.sim.simulate import build_inputs, run_batch, run_detail
from app.study import metrics
from app.tax import params_2026 as P

SEARCH_PATHS = 400
EVAL_PATHS = 2000
SEED = 2026
RAISE = 1.10  # "a raise": wages 10% higher
JOB_LOSS = JobLoss(year=1, years=1, keep=0.0)  # the engine's existing job-loss scenario: no wages for a year, starting next year
CONVERSION_NEEDS_OK = 25_000.0  # a Roth conversion at least this large waits for the customer's OK
SCHEDULED_BIG_FACTOR = 2.0  # next year's conversion needs the OK when it is this many times this year's
PROJECTED_RETIREMENT_ROWS = 8
YEAR0 = P.TAX_YEAR

ASSETS = (
    ("us_stocks", "US stocks"),
    ("intl_stocks", "International stocks"),
    ("bonds", "Bonds"),
    ("private_credit", "Private credit"),
    ("cash", "Cash"),
)
ACCOUNTS = (("brokerage", "Brokerage"), ("pretax", "401(k)/IRA"), ("roth", "Roth IRA"))
_STOCK_RETURN = float(markets.MEANS[markets.EQUITY])
_BOND_RETURN = float(markets.MEANS[markets.BOND])
_CREDIT_RETURN = float(markets.MEANS[markets.PRIVATE_CREDIT])
EXPECTED_RETURN = {
    "us_stocks": _STOCK_RETURN,
    "intl_stocks": _STOCK_RETURN,  # the engine holds one stock class
    "bonds": _BOND_RETURN,
    "private_credit": _CREDIT_RETURN,
    "cash": _BOND_RETURN,  # the engine holds cash with its bonds
}


# --------------------------------------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------------------------------------


def round_to_total(values: list[float], total: float | None = None) -> list[int]:
    """Whole dollars that add up to the rounded total (largest remainder), so a displayed column never disagrees with its total."""
    target = round(sum(values) if total is None else total)
    floors = [int(np.floor(v + 1e-9)) for v in values]
    short = target - sum(floors)
    order = sorted(range(len(values)), key=lambda i: values[i] - floors[i], reverse=True)
    for i in order[: max(0, short)]:
        floors[i] += 1
    return floors


def _canon(household: Household) -> str:
    return json.dumps(household.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def plan_id(household: Household, event: str, previous_id: str | None) -> str:
    key = f"{_canon(household)}|{event}|{previous_id or ''}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def content_id(household: Household, event: str) -> str:
    return hashlib.sha1(f"{_canon(apply_event(household, event))}|{event}".encode()).hexdigest()[:12]


def normalize(household: Household) -> Household:
    """Money to the cent and shares to six places, so a household read from the documents and the same household from the fixture are one."""
    data = household.model_dump()
    for person in data["people"]:
        person["wages"] = round(person["wages"], 2)
        person["pretax_401k"] = round(person["pretax_401k"], 2)
    for key in ("brokerage_value", "brokerage_basis", "pretax_balance", "roth_balance", "cash"):
        data["accounts"][key] = round(data["accounts"][key], 2)
    for key in ("pretax_equity_share", "roth_equity_share"):
        data["accounts"][key] = round(data["accounts"][key], 6)
    for key in ("home_down_payment", "college_annual_cost", "retirement_spending", "charitable_giving"):
        data["goals"][key] = round(data["goals"][key], 2)
    data["social_security"]["annual_benefit"] = round(data["social_security"]["annual_benefit"], 2)
    data["snapshot"] = None  # what the tax form printed feeds the profile only, never the plan
    data["estimated"] = []
    return Household.model_validate(data)


def apply_event(household: Household, event: str) -> Household:
    """A raise changes the household's wages; a job loss is applied to the simulated futures, not to the household."""
    if event == "raise":
        data = household.model_dump()
        for person in data["people"]:
            person["wages"] = round(person["wages"] * RAISE, 2)
        return Household.model_validate(data)
    return household


# --------------------------------------------------------------------------------------------------------------------------
# The plan: the planner's search, the evaluation futures, the deterministic log
# --------------------------------------------------------------------------------------------------------------------------


@dataclass
class Computed:
    household: Household  # with the event applied (a raise), as planned
    event: str
    strategy: Strategy
    strategy_kept: bool  # the customer's strategy was kept (the search found nothing clearly better)
    years: int
    plan_wealth: np.ndarray
    advisor_wealth: np.ndarray
    plan_paths: np.ndarray
    plan_log: dict[str, np.ndarray]
    advisor_log: dict[str, np.ndarray]
    det: S.SimInputs
    seconds: float = 0.0


def compute_plan(household: Household, event: str, anchor: Strategy | None = None) -> Computed:
    import time

    started = time.perf_counter()
    planned = apply_event(household, event)
    kwargs = {"job_loss": JOB_LOSS} if event == "job_loss" else {}
    futures = build_inputs(planned, n_paths=SEARCH_PATHS, seed=SEED, **kwargs)
    validation = build_inputs(planned, n_paths=VALIDATION_PATHS, seed=SEED + VALIDATION_SEED_OFFSET, **kwargs)
    strategy = search_matched(futures, validation, menu(style="liability_matched"))[1].strategy
    evaluation = build_inputs(planned, n_paths=EVAL_PATHS, seed=SEED + EVAL_SEED_OFFSET, **kwargs)
    years = evaluation.n_years
    kept = False
    if anchor is not None and anchor != strategy:
        batch = run_batch(evaluation, [anchor.policy(), strategy.policy(), RIA_BASELINE])
        # The current strategy still meets the limits it was chosen under when it is no worse on them than the searched one on these same
        # futures (a chance measured on 2,000 futures is only good to about a point, so the limit itself is not applied to it alone).
        held_forced, new_forced = float(np.mean(batch.forced_years[0] > 0)), float(np.mean(batch.forced_years[1] > 0))
        held_ruin, new_ruin, advisor_ruin = (float(np.mean(batch.unfunded[i] > 0)) for i in (0, 1, 2))
        held_ok = held_forced <= max(FORCED_SALE_LIMIT, new_forced) and held_ruin <= max(advisor_ruin, new_ruin)
        better = metrics.compare(batch.wealth[1], batch.wealth[0], years, with_range=True, median_only=True)
        if held_ok and better.median_range[0] <= 0.0:
            strategy, kept = anchor, True
    elif anchor is not None:
        kept = True
    batch = run_batch(evaluation, [strategy.policy(), RIA_BASELINE], record_paths=True)
    det = build_inputs(planned, deterministic=True, **kwargs)
    return Computed(
        household=planned,
        event=event,
        strategy=strategy,
        strategy_kept=kept,
        years=years,
        plan_wealth=batch.wealth[0],
        advisor_wealth=batch.wealth[1],
        plan_paths=batch.path_wealth[0],
        plan_log=run_detail(det, strategy.policy()).log,
        advisor_log=run_detail(det, RIA_BASELINE).log,
        det=det,
        seconds=time.perf_counter() - started,
    )


# --------------------------------------------------------------------------------------------------------------------------
# Today's allocation: the engine's own first-year rebalance applied to today's balances
# --------------------------------------------------------------------------------------------------------------------------


@dataclass
class Allocation:
    # dollars by account and class, after the first rebalance
    pretax: dict[str, float]
    roth: dict[str, float]
    brokerage: dict[str, float]
    stock_basis: float  # the brokerage stocks' cost basis after it
    stock_value: float

    def account(self, key: str) -> dict[str, float]:
        return getattr(self, key)


def initial_allocation(household: Household, policy: S.Policy, det: S.SimInputs) -> Allocation:
    """What step 7 of the engine's year does with today's balances (`_rebalance`), for the policy's first-year action. Mirrors the kernel's
    own arithmetic for the target (stock share, private credit, the spending reserve, what must stay in the taxable account); the balances
    are today's, before the year's growth."""
    st = S._initial_state(household)
    row = policy.row(float(household.primary_age))
    act = np.zeros(S.NACT)
    S._policy_action(row, np.ones(S.NGATE), det.tv, 0, float(det.wages[0, 0]), act)
    total = float(sum(st[i] for i in (S.S_PE, S.S_PB, S.S_PP, S.S_RE, S.S_RB, S.S_RP, S.S_BE, S.S_BB, S.S_BP)))
    share, pc_share = float(act[S.A_STOCK]), float(act[S.A_PC])
    if act[S.A_RESERVE] > 0.5:
        needed = sum(float(S._need_of(det.tv, j, 0.0)) for j in range(1, int(act[S.A_RESERVE] + 0.5) + 1) if j < det.tv.shape[0])
        pc_held = pc_share if act[S.A_LOCATION] > 0.5 else 0.0
        safe = min(1.0, max(needed / total, pc_held)) if total > 0 else 0.0
        early = sum(
            float(S._need_of(det.tv, j, 0.0))
            for j in range(1, int(act[S.A_RESERVE] + 0.5) + 1)
            if j < det.tv.shape[0] and det.tv[j, S.TV_AGE] < S._EARLY_AGE
        )
        if act[S.A_LOCATION] > 0.5:
            S._rebalance(st, 1.0 - safe, min(pc_share, safe), False, early)
        else:
            S._rebalance(st, 1.0 - safe, 0.0, True)
    elif act[S.A_LOCATION] > 0.5:
        S._rebalance(st, share * (1.0 - pc_share), pc_share, False)
    else:
        S._rebalance(st, share, 0.0, True)
    g = lambda i: float(st[i])  # noqa: E731
    return Allocation(
        pretax={"stocks": g(S.S_PE), "bonds": g(S.S_PB), "private_credit": g(S.S_PP)},
        roth={"stocks": g(S.S_RE), "bonds": g(S.S_RB), "private_credit": g(S.S_RP)},
        brokerage={"stocks": g(S.S_BE), "bonds": g(S.S_BB), "private_credit": g(S.S_BP)},
        stock_basis=g(S.S_BBASIS),
        stock_value=g(S.S_BE),
    )


def _split_stocks(alloc: Allocation) -> dict[str, dict[str, float]]:
    """US / international stocks by account: the same illustrative split in every account (the engine holds one stock class)."""
    return {
        k: {"us_stocks": alloc.account(k)["stocks"] * ill.US_SHARE_OF_STOCKS, "intl_stocks": alloc.account(k)["stocks"] * (1.0 - ill.US_SHARE_OF_STOCKS)}
        for k, _ in ACCOUNTS
    }


def asset_matrix(alloc: Allocation) -> dict[str, dict[str, float]]:
    """Dollars by class and account: {class: {brokerage, pretax, roth}}."""
    stock = _split_stocks(alloc)
    out: dict[str, dict[str, float]] = {key: {} for key, _ in ASSETS}
    for acct, _ in ACCOUNTS:
        a = alloc.account(acct)
        out["us_stocks"][acct] = stock[acct]["us_stocks"]
        out["intl_stocks"][acct] = stock[acct]["intl_stocks"]
        out["bonds"][acct] = a["bonds"]
        out["private_credit"][acct] = a["private_credit"]
        out["cash"][acct] = 0.0  # the engine invests the household's cash in the target mix
    return out


# --------------------------------------------------------------------------------------------------------------------------
# Building the screens
# --------------------------------------------------------------------------------------------------------------------------


def _bracket_rate_at(ordinary_taxable: float) -> float:
    for top, rate in P.FED_BRACKETS_MFJ:
        if ordinary_taxable <= top + 1e-6:
            return rate
    return P.FED_BRACKETS_MFJ[-1][1]


def _ordinary_taxable(log: dict[str, np.ndarray], t: int) -> float:
    """Ordinary taxable income after the year's conversion: taxable income less the qualified dividends and net long-term gains it holds."""
    preferential = float(log["dividends"][t]) + max(0.0, float(log["net_gain"][t]))
    return max(0.0, float(log["taxable_income"][t]) - preferential)


def _fee(policy: S.Policy, total: float, age: float) -> float:
    row = policy.row(age)
    return float(S._advisory_fee(total, row[S.SP_FEE_BREAKPOINTS], row[S.SP_FEE_FLAT]))


def _mix_rows(matrix: dict[str, dict[str, float]], accounts_total: dict[str, float]) -> Mix:
    keys = [k for k, _ in ASSETS]
    raw = [sum(matrix[k].values()) for k in keys]
    total = sum(accounts_total.values())
    whole = round_to_total(raw, total)
    rows = [
        AssetRow(key=k, label=label, amount=float(whole[i]), share=round(max(0.0, raw[i]) / total, 9) if total else 0.0, expected_return=EXPECTED_RETURN[k])
        for i, (k, label) in enumerate(ASSETS)
    ]
    return Mix(rows=rows, total=float(round(total)))


def _location(matrix: dict[str, dict[str, float]], accounts_total: dict[str, float]) -> Location:
    """Dollars by class and account that add up, row by row and column by column, to the displayed totals."""
    keys = [k for k, _ in ASSETS]
    accts = [k for k, _ in ACCOUNTS]
    col_totals = dict(zip(accts, round_to_total([accounts_total[a] for a in accts]), strict=True))
    cells: dict[tuple[str, str], int] = {}
    for a in accts:
        col = round_to_total([matrix[k][a] for k in keys], col_totals[a])
        for k, v in zip(keys, col, strict=True):
            cells[(k, a)] = v
    rows = []
    for k, label in ASSETS:
        b, p, r = cells[(k, "brokerage")], cells[(k, "pretax")], cells[(k, "roth")]
        rows.append(LocationRow(key=k, label=label, brokerage=float(b), pretax=float(p), roth=float(r), total=float(b + p + r)))
    total = LocationRow(
        key="total", label="Total", brokerage=float(col_totals["brokerage"]), pretax=float(col_totals["pretax"]),
        roth=float(col_totals["roth"]), total=float(sum(col_totals.values())),
    )
    return Location(rows=rows, total=total)


def build_plan(c: Computed, previous: Plan | None = None, change_label: str | None = None) -> Plan:
    h = c.household
    policy = c.strategy.policy()
    log, alog = c.plan_log, c.advisor_log
    age0 = h.primary_age
    a = h.accounts
    accounts_total = {"brokerage": a.brokerage_value + a.cash, "pretax": a.pretax_balance, "roth": a.roth_balance}
    total_savings = sum(accounts_total.values())

    alloc = initial_allocation(h, policy, c.det)
    matrix = asset_matrix(alloc)
    mix = _mix_rows(matrix, accounts_total)
    location = _location(matrix, accounts_total)

    # --- the plan against the advisor, from the same two sets of wealth at the horizon
    plan_med = float(np.median(c.plan_wealth))
    adv_med = float(np.median(c.advisor_wealth))
    dollars_more = plan_med - adv_med
    rate = (plan_med / adv_med) ** (1.0 / c.years) - 1.0 if adv_med > 0 and plan_med > 0 else 0.0

    # --- fees
    fee_rate = float(policy.flat_fee)
    fee_dollars = fee_rate * total_savings
    advisor_fee = _fee(RIA_BASELINE, total_savings, float(age0))

    # --- this year's taxes
    conv = float(log["conv"][0])
    conv_tax = float(log["conv_tax"][0])
    harvest = float(log["harvest"][0])
    net = float(log["net_gain"][0])
    carried = max(0.0, float(log["cf_out"][0]) - float(log["cf_in"][0]))
    if net >= 0.0:
        offset, deducted = harvest, 0.0
        carried = 0.0
    else:
        offset = max(0.0, net + harvest)
        deducted = max(0.0, harvest - offset - carried)
    interest_kept = (alloc.pretax["bonds"] + alloc.roth["bonds"]) * markets.BOND_INTEREST_YIELD + (
        alloc.pretax["private_credit"] + alloc.roth["private_credit"]
    ) * markets.PRIVATE_CREDIT_INCOME_YIELD
    tax_saved = float(alog["total_tax"][0]) - (float(log["total_tax"][0]) - conv_tax)
    taxes_this_year = TaxesThisYear(
        roth_conversion=conv, conversion_tax=conv_tax, losses_harvested=harvest, gains_offset=offset,
        deducted_from_income=deducted, carried_forward=carried, interest_kept_out=interest_kept, tax_saved=tax_saved,
    )
    after = _ordinary_taxable(log, 0)
    before = max(0.0, after - conv)
    fill_rate = _bracket_rate_at(after) if conv > 0 else _bracket_rate_at(before)
    steps, floor = [], 0.0
    for top, r in P.FED_BRACKETS_MFJ:
        steps.append(BracketStep(rate=r, floor=floor, ceiling=None if top == float("inf") else top, filled=bool(abs(r - fill_rate) < 1e-9)))
        floor = top
    bracket = BracketView(
        brackets=steps, taxable_before=before, conversion=conv, fills_to=before + conv, marginal_rate=fill_rate,
        illinois_tax_on_conversion=float(log["conv_il_tax"][0]),
    )
    conversions = [
        ConversionRow(
            year=YEAR0 + t, age=int(log["age"][t]), amount=float(log["conv"][t]), tax=float(log["conv_tax"][t]),
            bracket_rate=_bracket_rate_at(_ordinary_taxable(log, t)),
        )
        for t in range(len(log["age"]))
        if log["conv"][t] > 0.5
    ]

    # --- this year's moves
    next_conv = float(log["conv"][1]) if len(log["conv"]) > 1 else 0.0
    moves: list[Move] = [
        Move(key="invest", title="Invest your savings in the target mix", amount=float(round(total_savings)), timing="This year", status="done"),
        Move(key="location", title="Place bonds and private credit in the 401(k)/IRA and stocks in the Roth and brokerage accounts"
             if policy.donabach_location else "Hold the same mix in every account", timing="This year", status="done"),
        Move(key="lots", title="Sell the highest-cost lots first", timing="Ongoing", status="ongoing"),
    ]
    if policy.tax_loss_harvesting:
        moves.append(Move(key="harvest", title="Harvest losses", amount=harvest if harvest > 0 else None, timing="Ongoing", status="ongoing"))
    if conv > 0:
        moves.append(
            Move(
                key="conversion", title="Roth conversion", amount=conv, timing="This year", age=int(log["age"][0]),
                status="needs_ok" if conv >= CONVERSION_NEEDS_OK else "scheduled", detail=f"Tax {_money(conv_tax)}",
            )
        )
    if next_conv > 0:
        big = next_conv >= SCHEDULED_BIG_FACTOR * max(conv, 1.0) and next_conv >= CONVERSION_NEEDS_OK
        moves.append(
            Move(
                key="conversion_next", title="Roth conversion", amount=next_conv, timing=f"Next year (age {int(log['age'][1])})", age=int(log["age"][1]),
                status="needs_ok" if big else "scheduled", detail=f"Tax {_money(float(log['conv_tax'][1]))}",
            )
        )
    if h.people[0].pretax_401k > 0 and policy.k401 != "pretax":
        moves.append(
            Move(key="k401", title="Change your 401(k) contributions to the Roth option through your employer", timing="This year",
                 status="your_step")
        )

    # --- projection
    start = S.initial_after_tax_wealth(h)
    med_path = np.median(c.plan_paths, axis=0)
    projection = [ProjectionPoint(age=age0, wealth=float(start))] + [
        ProjectionPoint(age=age0 + t + 1, wealth=float(med_path[t])) for t in range(c.years)
    ]
    projection[-1] = ProjectionPoint(age=age0 + c.years, wealth=plan_med)
    g = h.goals
    markers: list[GoalMarker] = []
    if g.college_starts_in_years is not None and g.college_annual_cost > 0 and g.college_years > 0:
        s_age = age0 + g.college_starts_in_years
        markers.append(GoalMarker(key="college", label="College", start_age=s_age, end_age=s_age + g.college_years))
    if g.home_purchase_in_years is not None and g.home_down_payment > 0:
        markers.append(GoalMarker(key="home", label="Home purchase", start_age=age0 + g.home_purchase_in_years))
    markers.append(GoalMarker(key="retirement", label="Retirement", start_age=g.retirement_age))
    markers.append(GoalMarker(key="social_security", label="Social Security", start_age=h.social_security.start_age))

    # --- holdings
    holdings = _holdings(alloc, matrix, policy, location)

    # --- retirement income
    rows = _income_rows(h, log)
    required = _required(h, log)
    order = _withdrawal_order(policy)

    # --- goals
    goals = _goals(h, c, log)

    portfolio = Portfolio(
        summary=Summary(
            horizon_age=HORIZON_AGE, age=age0, projected_wealth=plan_med, invested_today=float(round(total_savings)), fee_dollars=fee_dollars,
            fee_rate=fee_rate, tax_saved=tax_saved,
        ),
        overview=Overview(projection=projection, markers=markers, mix=mix, location=location, moves=moves),
        holdings=holdings,
        taxes=TaxesTab(
            this_year=taxes_this_year, bracket=bracket, opportunities=[], opportunities_illustrative=False, conversions=conversions,
        ),
        retirement=RetirementTab(rows=rows, withdrawal_order=order, required=required),
        goals=goals,
    )

    # --- comparison
    adv_alloc = initial_allocation(h, RIA_BASELINE, c.det)
    adv_matrix = asset_matrix(adv_alloc)
    adv_mix = _mix_rows(adv_matrix, accounts_total)
    top = max(plan_med, adv_med, 1.0)
    comparison = Comparison(
        dollars_more=dollars_more,
        rate_per_year=rate,
        advisor=AdvisorCard(
            title="Standard wealth advisor", wealth_80=adv_med, bar=adv_med / top,
            mix=[MixShare(key=r.key, label=r.label, share=r.share) for r in adv_mix.rows],
            accounts=["Same mix in every account"],
            harvesting="Fund-level, in large down years", harvested_so_far=float(alog["harvest"][0]),
            roth_conversion=float(alog["conv"][0]), fee_dollars=advisor_fee, fee_rate=advisor_fee / total_savings if total_savings else 0.0,
        ),
        waramoug=AdvisorCard(
            title="Waramoug", wealth_80=plan_med, bar=plan_med / top,
            mix=[MixShare(key=r.key, label=r.label, share=r.share) for r in mix.rows],
            accounts=_account_lines(location),
            harvesting="Stock by stock" if policy.direct_indexing else ("Fund-level, in large down years" if policy.tax_loss_harvesting else "None"),
            harvested_so_far=harvest, roth_conversion=conv, fee_dollars=fee_dollars, fee_rate=fee_rate,
        ),
    )
    pid = plan_id(h, c.event, previous.plan_id if previous else None)
    plan = Plan(plan_id=pid, household=h, portfolio=portfolio, comparison=comparison, event=c.event)  # type: ignore[arg-type]
    if previous is not None:
        plan.what_changed = what_changed(previous, plan, change_label or "")
    return plan


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _account_lines(location: Location) -> list[str]:
    """Where Waramoug puts what: for each account, the classes it holds the most of (from the engine's own allocation)."""
    lines = []
    names = {"brokerage": "Brokerage", "pretax": "401(k)/IRA", "roth": "Roth IRA"}
    for acct in ("brokerage", "pretax", "roth"):
        held = [(r.label, getattr(r, acct)) for r in location.rows if getattr(r, acct) > 0.5]
        total = sum(v for _, v in held)
        if total <= 0:
            continue
        held.sort(key=lambda x: -x[1])
        lines.append(f"{names[acct]}: " + ", ".join(f"{label} {v / total:.0%}" for label, v in held))
    return lines


def _holdings(alloc: Allocation, matrix, policy: S.Policy, location: Location) -> HoldingsTab:
    stock_gain_total = max(0.0, alloc.stock_value - alloc.stock_basis)
    stock_total = sum(matrix["us_stocks"].values()) + sum(matrix["intl_stocks"].values())
    accounts: list[AccountHoldings] = []
    taxation = {"brokerage": "Taxable", "pretax": "Taxed when withdrawn", "roth": "Tax-free"}
    labels = {"brokerage": "Brokerage", "pretax": "401(k)/IRA", "roth": "Roth IRA"}
    for acct, _ in ACCOUNTS:
        balance = float(getattr(location.total, acct))
        rows: list[HoldingRow] = []
        values = {r.key: getattr(r, acct) for r in location.rows}
        for key, _label in ASSETS:
            v = values[key]
            if v <= 0:
                continue
            name = ill.FUND_NAMES[key]
            positions = 1
            gain = None
            yld = None
            if key in ("us_stocks", "intl_stocks"):
                if acct == "brokerage":
                    gain = stock_gain_total * (matrix[key][acct] / stock_total_in_brokerage(matrix)) if stock_total_in_brokerage(matrix) > 0 else 0.0
                else:
                    yld = markets.DIVIDEND_YIELD
                if key == "us_stocks" and acct == "brokerage" and policy.direct_indexing:
                    name, positions = ill.DIRECT_INDEXING_NAME, S.N_STOCKS
            elif key == "bonds":
                yld = markets.BOND_INTEREST_YIELD
            elif key == "private_credit":
                yld = markets.PRIVATE_CREDIT_INCOME_YIELD
            rows.append(HoldingRow(name=name, positions=positions, value=float(v), gain=gain, yield_rate=yld, share=v / balance if balance else 0.0))
        whole_gain = None
        if acct == "brokerage":
            # per-holding gains are whole dollars that add up to the account's unrealized gain
            gains = [r.gain or 0.0 for r in rows]
            fixed = round_to_total(gains, stock_gain_total)
            k = 0
            for r in rows:
                if r.gain is not None:
                    r.gain = float(fixed[k])
                k += 1
            whole_gain = float(sum(fixed))
        accounts.append(
            AccountHoldings(
                key=acct, label=labels[acct], balance=balance, taxation=taxation[acct],
                cost_basis=(
                    float(sum(r.value for r in rows if r.gain is not None) - (whole_gain or 0.0)) if acct == "brokerage" else None
                ),
                unrealized_gain=whole_gain, holdings=rows,
            )
        )
    stocks_amount = float(round(stock_total))
    sectors = [BarRow(label=name, share=w, amount=round(stocks_amount * w)) for name, w in ill.SECTORS]
    regions = [BarRow(label="United States", share=ill.US_SHARE_OF_STOCKS, amount=round(stocks_amount * ill.US_SHARE_OF_STOCKS))] + [
        BarRow(label=name, share=(1 - ill.US_SHARE_OF_STOCKS) * w, amount=round(stocks_amount * (1 - ill.US_SHARE_OF_STOCKS) * w))
        for name, w in ill.INTERNATIONAL_REGIONS
    ]
    largest = None
    if policy.direct_indexing:
        us_brokerage = matrix["us_stocks"]["brokerage"]
        ratio = stock_gain_total / alloc.stock_value if alloc.stock_value > 0 else 0.0
        largest = [StockRow(name=n, value=round(us_brokerage * w), gain=round(us_brokerage * w * ratio)) for n, w in ill.LARGEST_US_STOCKS]
    return HoldingsTab(accounts=accounts, largest_stocks=largest, sectors=sectors, regions=regions)


def stock_total_in_brokerage(matrix) -> float:
    return matrix["us_stocks"]["brokerage"] + matrix["intl_stocks"]["brokerage"]


def _income_rows(h: Household, log: dict[str, np.ndarray]) -> list[IncomeRow]:
    start = max(0, h.goals.retirement_age - h.primary_age)
    rows = []
    for t in range(start, min(len(log["age"]), start + PROJECTED_RETIREMENT_ROWS)):
        ss = float(log["ss"][t])
        spending = float(log["spend_need"][t]) + ss
        tax = float(log["total_tax"][t])
        pretax = float(log["ret_dist"][t])
        roth = float(log["withdrawn_roth"][t])
        taxable = float(log["withdrawn_brokerage"][t]) + float(log["portfolio_tax"][t])
        rows.append(
            IncomeRow(
                age=int(log["age"][t]), year=YEAR0 + t, social_security=ss, from_pretax=pretax, from_taxable=taxable, from_roth=roth,
                total_sources=ss + pretax + taxable + roth, spending=spending, tax=tax, total_uses=spending + tax,
            )
        )
    return rows


def _required(h: Household, log: dict[str, np.ndarray]) -> RequiredWithdrawals:
    start_age = int(P.rmd_start_age(P.TAX_YEAR - h.primary_age))
    t0 = start_age - h.primary_age
    if t0 >= len(log["age"]):
        return RequiredWithdrawals(start_age=start_age, first_amount=0.0, covered=True, note=f"None before age {HORIZON_AGE}")
    first = 0.0
    covered = True
    for t in range(max(0, t0), len(log["age"])):
        if log["rmd"][t] > 0.5:
            first = float(log["rmd"][t])
            covered = float(log["ret_dist"][t]) >= first - 0.5
            break
    note = "No pre-tax balance left at that age" if first <= 0.5 else "Planned withdrawals cover it" if covered else "Planned withdrawals fall short"
    return RequiredWithdrawals(start_age=start_age, first_amount=first, covered=covered, note=note)


def _withdrawal_order(policy: S.Policy) -> list[str]:
    if policy.bracket_withdrawals:
        return [
            "Required withdrawals from the 401(k)/IRA",
            "401(k)/IRA, up to the top of the 22% bracket",
            "Brokerage account",
            "Roth IRA last",
        ]
    return ["Every account in proportion to its balance"]


def _goals(h: Household, c: Computed, log: dict[str, np.ndarray]) -> GoalsTab:
    g = h.goals
    age0 = h.primary_age
    med = np.median(c.plan_paths, axis=0)  # median wealth at the end of year t

    def wealth_at(age: int) -> float:
        t = age - age0 - 1
        if t < 0:
            return float(S.initial_after_tax_wealth(h))
        return float(med[min(t, len(med) - 1)])

    def status(progress: float) -> str:
        return "On track" if progress >= 1.0 else "Close" if progress >= 0.8 else "Behind"

    cards: list[GoalCard] = []
    if g.college_starts_in_years is not None and g.college_annual_cost > 0 and g.college_years > 0:
        total = g.college_annual_cost * g.college_years
        s_age = age0 + g.college_starts_in_years
        progress = min(1.0, wealth_at(s_age) / total) if total > 0 else 1.0
        cards.append(
            GoalCard(key="college", label="College", target=total, target_label=f"{_money(total)} in total",
                     timing=f"Starts at age {s_age}, {g.college_years} years", progress=progress, status=status(progress))  # type: ignore[arg-type]
        )
    if g.home_purchase_in_years is not None and g.home_down_payment > 0:
        s_age = age0 + g.home_purchase_in_years
        progress = min(1.0, wealth_at(s_age) / g.home_down_payment)
        cards.append(
            GoalCard(key="home", label="Home purchase", target=g.home_down_payment, target_label=f"{_money(g.home_down_payment)} down payment",
                     timing=f"At age {s_age}", progress=progress, status=status(progress))  # type: ignore[arg-type]
        )
    t_ret = max(0, g.retirement_age - age0)
    need = float(sum(log["spend_need"][t] for t in range(t_ret, len(log["spend_need"]))))
    progress = min(1.0, wealth_at(g.retirement_age) / need) if need > 0 else 1.0
    cards.append(
        GoalCard(key="retirement", label="Retirement", target=g.retirement_spending,
                 target_label=f"{_money(g.retirement_spending)} a year", timing=f"From age {g.retirement_age}", progress=progress,
                 status=status(progress))  # type: ignore[arg-type]
    )
    return GoalsTab(cards=cards)


# --------------------------------------------------------------------------------------------------------------------------
# What changed
# --------------------------------------------------------------------------------------------------------------------------


def what_changed(before: Plan, after: Plan, changed: str) -> WhatChanged:
    mix = []
    for rb, ra in zip(before.portfolio.overview.mix.rows, after.portfolio.overview.mix.rows, strict=True):
        mix.append(MixChange(key=ra.key, label=ra.label, before=rb.share, after=ra.share, moved=abs(round(ra.share * 100) - round(rb.share * 100)) >= 1))
    old = {m.key: m for m in before.portfolio.overview.moves}
    new = {m.key: m for m in after.portfolio.overview.moves}
    moves: list[MoveChange] = []
    for key, m in new.items():
        if key not in old:
            moves.append(MoveChange(kind="added", title=_move_title(m), after=_move_text(m)))
        elif (old[key].amount, old[key].status) != (m.amount, m.status):
            moves.append(MoveChange(kind="changed", title=_move_title(m), before=_move_text(old[key]), after=_move_text(m)))
    for key, m in old.items():
        if key not in new:
            moves.append(MoveChange(kind="removed", title=_move_title(m), before=_move_text(m)))
    conv_b = _next_conversion(before)
    conv_a = _next_conversion(after)
    return WhatChanged(
        changed=changed, mix=mix, wealth_before=before.portfolio.summary.projected_wealth, wealth_after=after.portfolio.summary.projected_wealth,
        moves=moves, conversion_age=conv_a[0] or conv_b[0] or 0, conversion_before=conv_b[1], conversion_after=conv_a[1],
    )


def _next_conversion(plan: Plan) -> tuple[int | None, float]:
    """The Roth conversion in the year after the first (the year a job loss changes), as a (age, amount) pair."""
    rows = plan.portfolio.taxes.conversions
    if len(rows) >= 2:
        return rows[1].age, rows[1].amount
    return (None, 0.0)


def _move_title(m: Move) -> str:
    return f"{m.title} at {m.age}" if m.key.startswith("conversion") and m.age is not None else m.title


def _move_text(m: Move) -> str:
    status = {"done": "Done", "ongoing": "Ongoing", "scheduled": "Scheduled", "needs_ok": "Needs your OK", "your_step": "Your step"}[m.status]
    return f"{_money(m.amount)}, {status}" if m.amount is not None else status


# --------------------------------------------------------------------------------------------------------------------------
# The cache of plans (precomputed in demo mode) and the change presets
# --------------------------------------------------------------------------------------------------------------------------

_lock = threading.RLock()
_plans: dict[str, Plan] = {}
_strategies: dict[str, Strategy] = {}
_computed_seconds: dict[str, float] = {}
_content: dict[str, str] = {}


def get_plan(household: Household, event: str = "none", previous_id: str | None = None, change_label: str | None = None) -> Plan:
    """The plan for the household (and event), from the cache when it was precomputed, else the real planner, live."""
    household = normalize(household)
    pid = plan_id(apply_event(household, event), event, previous_id)
    with _lock:
        hit = _plans.get(pid)
        if hit is not None:
            return hit
        previous = _plans.get(previous_id) if previous_id else None
        if previous is not None and _content.get(previous.plan_id) == content_id(household, event):
            return previous  # nothing was changed: the plan the customer already has
        anchor = _strategies.get(previous_id) if previous_id else None
        computed = compute_plan(household, event, anchor)
        plan = build_plan(computed, previous, change_label)
        _plans[plan.plan_id] = plan
        _strategies[plan.plan_id] = computed.strategy
        _computed_seconds[plan.plan_id] = computed.seconds
        _content[plan.plan_id] = content_id(household, event)
        return plan


def lookup(pid: str) -> Plan | None:
    with _lock:
        return _plans.get(pid)


def seconds_for(pid: str) -> float | None:
    return _computed_seconds.get(pid)


def reset() -> None:
    with _lock:
        _plans.clear()
        _strategies.clear()
        _computed_seconds.clear()
        _content.clear()
