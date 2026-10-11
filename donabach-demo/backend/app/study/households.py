"""Synthetic households for the household-type study (spec A10).

Six types, about fifty households each. Every household is drawn from ranges that make it a clear
example of its type; nothing is fitted to any result. All households are fictional.

1. diversified: modest unrealized gains (like the demo household)
2. concentrated: a single-stock position of 40%+ of investable assets with a low basis
3. big_gains: large unrealized gains in the brokerage account (basis under 40% of value)
4. early_retirement: retiring at 56 to 61 with several low-income years before Social Security
5. large_purchase: a purchase within three years that takes 25%+ of investable assets
6. high_earner: large pre-tax balances, projected at $3M or more at 70

Every household also gets a sustainability cap: it does not plan to spend more in retirement than
a 4.5% withdrawal from its projected liquid wealth at retirement (expected-return path) would fund.
Without it a good share of randomly drawn households plan lifestyles they cannot afford, and a study
of how the planner helps would mostly be a study of overspending. The cap looks at the household
only, never at any strategy's result.

Not modelled: a single stock's own (idiosyncratic) risk. The simulator holds all brokerage equity
as the diversified market, so for type 2 only the tax side of a concentrated position shows up.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from app.schemas import Accounts, Goals, Household, Person, SocialSecurity

TYPES: dict[str, str] = {
    "diversified": "Diversified, modest unrealized gains",
    "concentrated": "Concentrated single stock (40%+ of investable assets, low basis)",
    "big_gains": "Large unrealized gains (brokerage basis under 40% of value)",
    "early_retirement": "Early retirement (55 to 58 now, several low-income years before Social Security)",
    "large_purchase": "Large purchase within 3 years (25%+ of investable assets)",
    "high_earner": "High earners with large pre-tax balances ($3M+ projected at 70)",
}


@dataclass(frozen=True)
class StudyHousehold:
    type: str
    index: int
    household: Household
    note: str = ""  # e.g. the single stock's share of investable assets


def _u(rng: np.random.Generator, lo: float, hi: float) -> float:
    return float(rng.uniform(lo, hi))


def _log_u(rng: np.random.Generator, lo: float, hi: float) -> float:
    return float(np.exp(rng.uniform(np.log(lo), np.log(hi))))


def _people(rng: np.random.Generator, age: int, income: float, two_earner: float = 0.75) -> list[Person]:
    if rng.random() < two_earner:
        share = _u(rng, 0.25, 0.5)
        spouse_age = int(np.clip(age + rng.integers(-4, 5), 22, 69))
        return [Person(age=age, wages=income * (1 - share)), Person(age=spouse_age, wages=income * share)]
    return [Person(age=age, wages=income)]


def _children(rng: np.random.Generator, age: int) -> list[int]:
    n = int(rng.integers(0, 4)) if age <= 48 else int(rng.integers(0, 2))
    youngest_max = max(0, min(17, age - 22))
    return sorted(int(rng.integers(0, youngest_max + 1)) for _ in range(n))


def _college(rng: np.random.Generator, children: list[int]) -> dict:
    if not children:
        return dict(college_starts_in_years=None)
    return dict(
        college_starts_in_years=max(0, 18 - min(children)),
        college_annual_cost=_u(rng, 25_000, 45_000),
        college_years=4,
    )


def _social_security(income: float, start_age: int = 67, factor: float = 0.30) -> SocialSecurity:
    return SocialSecurity(annual_benefit=float(np.clip(factor * income, 20_000, 70_000)), start_age=start_age)


def _accounts(
    liquid: float,
    income: float,
    rng: np.random.Generator,
    *,
    pretax_share: tuple[float, float],
    roth_share: tuple[float, float],
    cash_to_income: tuple[float, float],
    basis_ratio: tuple[float, float],
    age: int,
    brokerage_floor: float = 0.08,
) -> Accounts:
    cash = income * _u(rng, *cash_to_income)
    pretax = liquid * _u(rng, *pretax_share)
    roth = liquid * _u(rng, *roth_share)
    brokerage = max(liquid * brokerage_floor, liquid - pretax - roth - cash)
    return Accounts(
        brokerage_value=brokerage,
        brokerage_basis=brokerage * _u(rng, *basis_ratio),
        pretax_balance=pretax,
        pretax_equity_share=float(np.clip(0.9 - 0.012 * (age - 25), 0.4, 0.9)),
        roth_balance=roth,
        cash=cash,
    )


# --------------------------------------------------------------------------------------------
# The six types
# --------------------------------------------------------------------------------------------


def diversified(rng: np.random.Generator) -> StudyHousehold:
    age = int(rng.integers(32, 49))
    income = _log_u(rng, 150_000, 350_000)
    liquid = income * _u(rng, 1.5, 3.5)
    children = _children(rng, age)
    home = rng.random() < 0.5
    goals = Goals(
        home_purchase_in_years=int(rng.integers(2, 9)) if home else None,
        home_down_payment=income * _u(rng, 0.3, 0.8),
        retirement_age=int(rng.integers(max(60, age + 1), 66)),
        retirement_spending=income * _u(rng, 0.45, 0.65),
        **_college(rng, children),
    )
    accounts = _accounts(
        liquid, income, rng, pretax_share=(0.45, 0.70), roth_share=(0.03, 0.12),
        cash_to_income=(0.05, 0.15), basis_ratio=(0.70, 0.92), age=age, brokerage_floor=0.10,
    )
    return StudyHousehold("diversified", 0, Household(
        people=_people(rng, age, income), children_ages=children, accounts=accounts, goals=goals,
        social_security=_social_security(income),
    ))


def concentrated(rng: np.random.Generator) -> StudyHousehold:
    age = int(rng.integers(35, 56))
    income = _log_u(rng, 150_000, 500_000)
    liquid = income * _u(rng, 2.0, 5.0)
    brokerage_share = _u(rng, 0.50, 0.75)
    stock_share = _u(rng, 0.40, min(0.70, brokerage_share))  # of investable assets
    stock_basis_ratio = _u(rng, 0.03, 0.25)  # low basis
    cash = income * _u(rng, 0.05, 0.12)
    roth = liquid * _u(rng, 0.0, 0.08)
    brokerage = liquid * brokerage_share
    pretax = max(0.0, liquid - brokerage - roth - cash)
    stock = liquid * stock_share
    other = brokerage - stock
    basis = stock * stock_basis_ratio + other * _u(rng, 0.70, 0.95)
    children = _children(rng, age)
    goals = Goals(
        home_purchase_in_years=None,
        retirement_age=int(rng.integers(max(58, age + 1), 68)),
        retirement_spending=income * _u(rng, 0.45, 0.70),
        **_college(rng, children),
    )
    accounts = Accounts(
        brokerage_value=brokerage, brokerage_basis=basis, pretax_balance=pretax,
        pretax_equity_share=float(np.clip(0.9 - 0.012 * (age - 25), 0.4, 0.9)), roth_balance=roth, cash=cash,
    )
    return StudyHousehold(
        "concentrated", 0,
        Household(people=_people(rng, age, income), children_ages=children, accounts=accounts, goals=goals,
                  social_security=_social_security(income)),
        note=f"single stock {stock_share * 100:.0f}% of investable assets at {stock_basis_ratio * 100:.0f}% basis",
    )


def big_gains(rng: np.random.Generator) -> StudyHousehold:
    age = int(rng.integers(40, 61))
    income = _log_u(rng, 120_000, 400_000)
    liquid = income * _u(rng, 2.5, 6.0)
    children = _children(rng, age)
    goals = Goals(
        home_purchase_in_years=None,
        retirement_age=int(rng.integers(max(60, age + 1), 69)),
        retirement_spending=income * _u(rng, 0.45, 0.70),
        **_college(rng, children),
    )
    brokerage_share = _u(rng, 0.30, 0.55)
    cash = income * _u(rng, 0.05, 0.12)
    roth = liquid * _u(rng, 0.02, 0.10)
    brokerage = liquid * brokerage_share
    accounts = Accounts(
        brokerage_value=brokerage, brokerage_basis=brokerage * _u(rng, 0.10, 0.38),  # basis under 40%
        pretax_balance=max(0.0, liquid - brokerage - roth - cash),
        pretax_equity_share=float(np.clip(0.9 - 0.012 * (age - 25), 0.4, 0.9)), roth_balance=roth, cash=cash,
    )
    return StudyHousehold("big_gains", 0, Household(
        people=_people(rng, age, income), children_ages=children, accounts=accounts, goals=goals,
        social_security=_social_security(income),
    ))


def early_retirement(rng: np.random.Generator) -> StudyHousehold:
    age = int(rng.integers(55, 59))
    income = _log_u(rng, 100_000, 300_000)
    liquid = income * _u(rng, 5.0, 9.0)
    retire = age + int(rng.integers(1, 4))  # 56 to 61
    ss_start = 67 if rng.random() < 0.7 else 70
    goals = Goals(
        home_purchase_in_years=None,
        college_starts_in_years=None,
        retirement_age=retire,
        retirement_spending=income * _u(rng, 0.45, 0.65),
    )
    accounts = _accounts(
        liquid, income, rng, pretax_share=(0.55, 0.80), roth_share=(0.05, 0.12),
        cash_to_income=(0.05, 0.15), basis_ratio=(0.60, 0.90), age=age, brokerage_floor=0.10,
    )
    return StudyHousehold("early_retirement", 0, Household(
        people=_people(rng, age, income, two_earner=0.6), children_ages=[], accounts=accounts, goals=goals,
        social_security=_social_security(income, ss_start, 0.35),
    ), note=f"retires at {retire}, Social Security at {ss_start}")


def large_purchase(rng: np.random.Generator) -> StudyHousehold:
    age = int(rng.integers(30, 51))
    income = _log_u(rng, 120_000, 400_000)
    liquid = income * _u(rng, 1.5, 4.0)
    children = _children(rng, age)
    share = _u(rng, 0.25, 0.50)  # of investable assets
    goals = Goals(
        home_purchase_in_years=int(rng.integers(1, 4)),
        home_down_payment=liquid * share,
        retirement_age=int(rng.integers(max(60, age + 1), 68)),
        retirement_spending=income * _u(rng, 0.45, 0.65),
        **_college(rng, children),
    )
    accounts = _accounts(
        liquid, income, rng, pretax_share=(0.35, 0.65), roth_share=(0.02, 0.12),
        cash_to_income=(0.05, 0.20), basis_ratio=(0.60, 0.95), age=age, brokerage_floor=0.15,
    )
    return StudyHousehold("large_purchase", 0, Household(
        people=_people(rng, age, income), children_ages=children, accounts=accounts, goals=goals,
        social_security=_social_security(income),
    ), note=f"purchase of {share * 100:.0f}% of investable assets")


def high_earner(rng: np.random.Generator, projected_pretax: Callable[[Household], float] | None = None) -> StudyHousehold:
    """Rejection-sampled until the pre-tax balance is projected at $3M+ at 70 (the caller supplies the projection)."""
    for _ in range(200):
        age = int(rng.integers(35, 51))
        income = _log_u(rng, 400_000, 900_000)
        liquid = income * _u(rng, 2.0, 4.5)
        children = _children(rng, age)
        goals = Goals(
            home_purchase_in_years=None,
            retirement_age=int(rng.integers(max(60, age + 1), 70)),
            retirement_spending=min(400_000.0, income * _u(rng, 0.30, 0.50)),
            **_college(rng, children),
        )
        pretax = income * _u(rng, 1.0, 3.0)
        brokerage = liquid * _u(rng, 0.10, 0.30)
        cash = income * _u(rng, 0.03, 0.08)
        accounts = Accounts(
            brokerage_value=brokerage, brokerage_basis=brokerage * _u(rng, 0.65, 0.95), pretax_balance=pretax,
            pretax_equity_share=float(np.clip(0.9 - 0.012 * (age - 25), 0.4, 0.9)),
            roth_balance=liquid * _u(rng, 0.0, 0.05), cash=cash,
        )
        household = Household(
            people=_people(rng, age, income, two_earner=0.85), children_ages=children, accounts=accounts,
            goals=goals, social_security=_social_security(income, factor=0.2),
        )
        if projected_pretax is None:
            return StudyHousehold("high_earner", 0, household)
        projected = projected_pretax(household)
        if projected >= 3_000_000.0:
            return StudyHousehold("high_earner", 0, household, note=f"pre-tax balance projected at ${projected / 1e6:.1f}M at 70")
    raise RuntimeError("could not draw a high-earner household with $3M+ projected pre-tax at 70")


def projected_pretax_at_70(household: Household) -> float:
    """The household's pre-tax balance at 70 along the expected-return path, with nothing converted."""
    from app.planner.baseline import RIA_BASELINE
    from app.sim.simulate import build_inputs, run_detail

    log = run_detail(build_inputs(household, deterministic=True), RIA_BASELINE).log
    ages = log["age"]
    index = int(np.flatnonzero(ages == 69)[0]) if (ages == 69).any() else len(ages) - 1  # year-end of age 69 = age 70
    return float(log["pretax"][index])


SUSTAINABLE_WITHDRAWAL_RATE = 0.045


def cap_retirement_spending(household: Household) -> Household:
    """Lower planned retirement spending to what a 4.5% withdrawal from projected wealth would fund."""
    from app.planner.baseline import RIA_BASELINE
    from app.sim.simulate import build_inputs, run_detail

    log = run_detail(build_inputs(household, deterministic=True), RIA_BASELINE).log
    t = max(0, household.goals.retirement_age - household.primary_age - 1)  # the last working year
    wealth = float(log["pretax"][t] + log["roth"][t] + log["brokerage"][t] + log["bucket"][t])
    cap = SUSTAINABLE_WITHDRAWAL_RATE * wealth
    if household.goals.retirement_spending <= cap:
        return household
    goals = household.goals.model_copy(update={"retirement_spending": cap})
    return household.model_copy(update={"goals": goals})


def generate(seed: int = 10, per_type: int = 50) -> list[StudyHousehold]:
    """`per_type` households of each of the six types, reproducible from `seed`."""
    out: list[StudyHousehold] = []
    makers: dict[str, Callable[[np.random.Generator], StudyHousehold]] = {
        "diversified": diversified,
        "concentrated": concentrated,
        "big_gains": big_gains,
        "early_retirement": early_retirement,
        "large_purchase": large_purchase,
        "high_earner": lambda rng: high_earner(rng, projected_pretax_at_70),
    }
    for t, key in enumerate(TYPES):
        rng = np.random.default_rng([seed, t])
        for i in range(per_type):
            made = makers[key](rng)
            out.append(StudyHousehold(key, i, cap_retirement_spending(made.household), made.note))
    return out
