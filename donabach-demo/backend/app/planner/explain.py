"""Why the plan wins, and what each decision is worth.

* `advantage_steps`: start from the RIA baseline and switch Donabach's decisions on one at a
  time, recording the change in median after-tax wealth at the horizon (80) on the same futures.
* `year_detail`: for one year of the deterministic plan, the decisions taken, that year's full
  tax return, and the value of each decision, found by re-running the plan with only that
  decision removed for that year and reporting the change in after-tax wealth at the horizon.
* `headline_reason`: a one-line reason for the recommendation, computed from the simulation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel

from app.planner.baseline import RIA_BASELINE
from app.planner.search import SearchResult
from app.planner.strategies import (
    DONABACH_FLAT_FEE,
    GLIDE_START_AGE,
    Strategy,
)
from app.schemas import HORIZON_AGE
from app.sim import simulate as sim
from app.sim.simulate import Policy, SimInputs, run_batch, run_detail
from app.tax import params_2026 as P
from app.tax.engine import TaxInputs, TaxLine, TaxReturn, compute_return, pretax_withdrawal_rate

# --------------------------------------------------------------------------------------------
# Where the advantage comes from
# --------------------------------------------------------------------------------------------


class AdvantageStep(BaseModel):
    label: str
    delta_median: float  # change in median after-tax wealth at the horizon from switching this on
    delta_p10: float
    cumulative_median: float
    active: bool  # False when the chosen strategy does not use this decision


def advantage_policies(strategy: Strategy) -> list[tuple[str, Policy]]:
    """Cumulative policies from the RIA baseline to `strategy`, in the order decisions are switched on."""
    chosen = strategy.policy()
    p0 = RIA_BASELINE
    p1 = p0.replace(breakpoint_fees=False, flat_fee=DONABACH_FLAT_FEE)
    p2 = p1.replace(donabach_location=True)
    p2b = p2.replace(lot_method=chosen.lot_method, short_term_ordinary=chosen.short_term_ordinary, donate_lots=chosen.donate_lots)
    p3 = p2b.replace(direct_indexing=chosen.direct_indexing)
    p4 = p3.replace(
        goal_bonds=chosen.goal_bonds,
        stock_share=chosen.stock_share,
        glide_start_age=GLIDE_START_AGE,
        glide_drop=chosen.glide_drop,
        private_credit=chosen.private_credit,
        reserve_years=chosen.reserve_years,
        reserve_refill_after_gains=chosen.reserve_refill_after_gains,
    )
    p5 = p4.replace(
        conversion_top=chosen.conversion_top,
        conversion_every_year=chosen.conversion_every_year,
        bracket_withdrawals=chosen.bracket_withdrawals,
        withdrawal_top=chosen.withdrawal_top,
        k401=chosen.k401,
        goal_funding=chosen.goal_funding,
    )
    assert p5 == chosen, "the last step must land exactly on the chosen strategy"
    return [
        ("RIA baseline", p0),
        ("Lower fee", p1),
        ("Asset location", p2),
        ("Tax-lot selection", p2b),
        ("Direct indexing", p3),
        ("Goal bonds, allocation and private credit", p4),
        ("Roth timing and withdrawal order", p5),
    ]


def advantage_steps(inputs: SimInputs, strategy: Strategy) -> list[AdvantageStep]:
    steps = advantage_policies(strategy)
    wealth = run_batch(inputs, [policy for _, policy in steps]).wealth
    medians = np.median(wealth, axis=1)
    p10 = np.percentile(wealth, 10, axis=1)
    out = []
    for i in range(1, len(steps)):
        label, _ = steps[i]
        out.append(
            AdvantageStep(
                label=label,
                delta_median=float(medians[i] - medians[i - 1]),
                delta_p10=float(p10[i] - p10[i - 1]),
                cumulative_median=float(medians[i] - medians[0]),
                active=steps[i][1] != steps[i - 1][1],
            )
        )
    return out


# --------------------------------------------------------------------------------------------
# One year of the plan
# --------------------------------------------------------------------------------------------

DECISION_GATES = {
    "conversion": sim.G_CONV,
    "harvest": sim.G_HARVEST,
    "bucket": sim.G_BUCKET,
    "location": sim.G_LOCATION,
    "withdraw": sim.G_WITHDRAW,
    "k401": sim.G_K401,
    "borrow": sim.G_BORROW,
}


class Decision(BaseModel):
    key: str
    label: str
    description: str
    amount: float | None = None
    value: float | None = None  # after-tax wealth at the horizon with the decision, minus without it
    valued: bool = True


class YearDetail(BaseModel):
    year_index: int
    age: int
    decisions: list[Decision]
    tax_lines: list[TaxLine]
    tax_return: TaxReturn
    wealth_at_year_end: float


def tax_return_for_year(log: dict[str, np.ndarray], t: int) -> TaxReturn:
    """Rebuild year `t`'s full tax return from the inputs the simulator logged for it."""
    return compute_return(
        TaxInputs(
            wages=max(0.0, float(log["wages_taxable"][t])),
            interest=max(0.0, float(log["interest"][t])),
            qualified_dividends=max(0.0, float(log["dividends"][t])),
            ordinary_dividends=max(0.0, float(log["dividends"][t])) + float(log["fund_distribution_short_term"][t]),
            net_capital_gain=float(log["net_gain"][t]),
            short_term_gain=float(log["short_term_gain"][t]),
            retirement_distributions=max(0.0, float(log["ret_dist"][t])),
            roth_conversions=max(0.0, float(log["conv"][t])),
            social_security=float(log["ss"][t]),
            early_withdrawal_base=max(0.0, float(log["early_base"][t])),
            children_under_17=int(log["kids"][t]),
            dependents=int(log["deps"][t]),
            capital_loss_carryforward=max(0.0, float(log["cf_in"][t])),
            aged_spouses=int(log["aged"][t]),
            cash_gifts=float(log["gift_cash"][t]),
            stock_gifts=float(log["gift_stock"][t]),
        )
    )


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _active_decisions(strategy: Strategy, policy: Policy, log: dict[str, np.ndarray], t: int) -> list[Decision]:
    """The decisions in force in year `t` (those that can be valued by removing them)."""
    found: list[Decision] = []
    if log["conv"][t] > 0:
        bracket = strategy.conversion_bracket
        found.append(
            Decision(
                key="conversion",
                label="Roth conversion",
                description=f"Converted {_money(log['conv'][t])} to Roth, filling the {bracket}% bracket; "
                "the tax is paid from the taxable account.",
                amount=float(log["conv"][t]),
            )
        )
    if log["harvest"][t] > 0:
        method = "stock by stock (direct indexing)" if policy.direct_indexing else "at fund level"
        found.append(
            Decision(
                key="harvest",
                label="Loss harvesting",
                description=f"Harvested {_money(log['harvest'][t])} of losses {method}.",
                amount=float(log["harvest"][t]),
            )
        )
    if policy.goal_bonds and log["bucket_flow"][t] != 0:
        flow = float(log["bucket_flow"][t])
        verb = "Moved" if flow > 0 else "Released"
        found.append(
            Decision(
                key="bucket",
                label="Goal bonds",
                description=f"{verb} {_money(abs(flow))} {'into' if flow > 0 else 'from'} the goal bond bucket, "
                f"which now holds {_money(log['bucket'][t])} for goals due in the next four years.",
                amount=flow,
            )
        )
    if log["borrowed"][t] > 0:
        found.append(
            Decision(
                key="borrow",
                label="Borrow for the goal",
                description=f"Borrowed {_money(log['borrowed'][t])} against the taxable account at "
                f"{P.BORROWING_RATE_REAL * 100:.1f}% (real) instead of selling assets; the loan stands at "
                f"{_money(log['loan'][t])} and is repaid from savings or by realizing gains in low-tax years.",
                amount=float(log["borrowed"][t]),
            )
        )
    if log["k401_roth"][t] > 0:
        found.append(
            Decision(
                key="k401",
                label="Roth 401(k)",
                description=f"Contributed {_money(log['k401_roth'][t])} to the Roth side of the 401(k), after tax, "
                f"instead of pre-tax; the extra {_money(log['roth_extra_tax'][t])} of tax this year came out of "
                "brokerage saving.",
                amount=float(log["k401_roth"][t]),
            )
        )
    if policy.donabach_location:
        found.append(
            Decision(
                key="location",
                label="Asset location",
                description="Private credit and bonds sit in the pre-tax account first; the Roth and "
                "brokerage accounts hold stocks.",
            )
        )
    if policy.bracket_withdrawals and log["spend_need"][t] > 0 and log["age"][t] >= P.EARLY_WITHDRAWAL_AGE:
        target = _bracket_label(policy.withdrawal_top)
        found.append(
            Decision(
                key="withdraw",
                label="Withdrawal order",
                description=f"Took pre-tax money up to the {target}% bracket first, then brokerage, then Roth "
                f"(pre-tax withdrawals this year: {_money(log['ret_dist'][t])}).",
                amount=float(log["ret_dist"][t]),
            )
        )
    return found


def _bracket_label(top: float) -> int:
    return {P.TOP_OF_12: 12, P.TOP_OF_22: 22, P.TOP_OF_24: 24}.get(top, 22)


def year_detail(inputs_det: SimInputs, strategy: Strategy, year_index: int) -> YearDetail:
    """Decisions, tax return and the value of each decision for one year of the deterministic plan."""
    policy = strategy.policy()
    full = run_detail(inputs_det, policy)
    log = full.log
    t = int(np.clip(year_index, 0, inputs_det.n_years - 1))
    decisions = _active_decisions(strategy, policy, log, t)

    # Re-run with each decision removed for this year only.
    if decisions:
        gates = np.ones((len(decisions), inputs_det.n_years, sim.NGATE))
        for row, decision in enumerate(decisions):
            gates[row, t, DECISION_GATES[decision.key]] = 0.0
        without = run_batch(inputs_det, [policy] * len(decisions), gates=gates).wealth[:, 0]
        for decision, wealth_without in zip(decisions, without, strict=True):
            decision.value = float(full.wealth[0, 0] - wealth_without)

    return _finish_year(policy, log, t, decisions)


def _finish_year(policy: Policy, log: dict[str, np.ndarray], t: int, decisions: list[Decision]) -> YearDetail:
    """Add the unvalued entries (a forced sale, the stock share) and the year's full tax return."""
    if log["forced_sale"][t] > 0:
        decisions.append(
            Decision(
                key="forced_sale",
                label="Forced sale",
                description=f"The market fell far enough to push the loan above 40% of the taxable account, so "
                f"{_money(log['forced_sale'][t])} was sold to bring it back to 30%.",
                amount=float(log["forced_sale"][t]),
                valued=False,
            )
        )
    share = float(log["stock_target"][t])
    decisions.append(
        Decision(
            key="stock_share",
            label="Stock share",
            description=f"Target {share * 100:.0f}% stocks in long-term money"
            + (f" ({policy.private_credit * 100:.0f}% of it set aside as private credit)." if policy.private_credit else "."),
            amount=share,
            valued=False,
        )
    )
    tax_return = tax_return_for_year(log, t)
    return YearDetail(
        year_index=t,
        age=int(log["age"][t]),
        decisions=decisions,
        tax_lines=tax_return.lines(),
        tax_return=tax_return,
        wealth_at_year_end=float(log["wealth"][t]),
    )


def year_detail_from_log(strategy: Strategy, policy: Policy, log: dict[str, np.ndarray], t: int) -> YearDetail:
    """One year of a plan whose path is already simulated (the adaptive plan's): what was done and the tax return.

    `strategy` and `policy` describe that year's choices. The decisions are not valued here (a value by removing a
    decision needs a re-run of the whole plan; the adaptive planner's own scores are in its "Why this year")."""
    decisions = _active_decisions(strategy, policy, log, t)
    for decision in decisions:
        decision.valued = False
    return _finish_year(policy, log, t, decisions)


# --------------------------------------------------------------------------------------------
# The one-line reason
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PretaxProjection:
    balance: float
    rate: float  # effective federal rate when withdrawn evenly over 20 years beside Social Security


def pretax_projection(inputs_det: SimInputs, policy: Policy) -> PretaxProjection:
    log = run_detail(inputs_det, policy).log
    balance = float(log["pretax"][-1])
    rate = float(pretax_withdrawal_rate(balance, float(inputs_det.hhc[sim.HC_SS]), float(log["aged"][-1])))
    return PretaxProjection(balance, rate)


def _compact(x: float) -> str:
    if abs(x) >= 1e6:
        return f"${x / 1e6:.2f}M".replace(".00M", "M")
    return f"${x / 1e3:,.0f}k"


def headline_reason(inputs_det: SimInputs, search_result: SearchResult, strategy: Strategy) -> str:
    """One line, computed from the simulation, on how the plan treats the pre-tax balance."""
    no_conversions = strategy.policy().replace(conversion_top=0.0, withdrawal_top=P.TOP_OF_22)
    plain = pretax_projection(inputs_det, no_conversions)
    if strategy.conversion_bracket is not None:
        with_plan = pretax_projection(inputs_det, strategy.policy())
        return (
            f"Without conversions your pre-tax balance reaches {_compact(plain.balance)} by {HORIZON_AGE}, taxed at about "
            f"{plain.rate * 100:.0f}% when withdrawn; filling the {strategy.conversion_bracket}% bracket "
            f"brings it to {_compact(with_plan.balance)}."
        )
    best_with = next((r for r in search_result.ranked if r.strategy.conversion_bracket is not None), None)
    gap = ""
    if best_with is not None and search_result.best.outcome.score > 0:
        shortfall = 1.0 - best_with.outcome.score / search_result.best.outcome.score
        gap = f" The best plan with Roth conversions scores {shortfall * 100:.1f}% lower, so paying that tax early does not pay."
    return (
        f"Your pre-tax balance is projected at {_compact(plain.balance)} at {HORIZON_AGE}, taxed at about "
        f"{plain.rate * 100:.0f}% when withdrawn.{gap}"
    )
