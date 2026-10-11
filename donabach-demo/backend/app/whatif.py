"""What-if scenarios: presets and editable inputs applied to a household before re-planning."""

from __future__ import annotations

from app.api_models import Change, HouseholdEdits, Preset
from app.schemas import Household, MarketShock

PRESET_LABELS: dict[str, str] = {
    "home_next_year": "Move home purchase to next year",
    "spouse_b_income_cut": "Spouse B changes jobs, income down 20%",
    "retire_57": "Retire at 57",
    "market_drop_30": "Market drops 30% next year",
}

SPOUSE_INCOME_CUT = 0.20
EARLY_RETIREMENT_AGE = 57
MARKET_DROP = -0.30


class WhatIfError(ValueError):
    """The scenario cannot be applied to this household."""


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _years(n: int | None) -> str:
    if n is None:
        return "none"
    return "this year" if n == 0 else f"in {n} {'year' if n == 1 else 'years'}"


def apply_whatif(
    household: Household,
    presets: list[Preset],
    edits: HouseholdEdits,
    shock: MarketShock | None = None,
) -> tuple[Household, MarketShock | None, list[Change]]:
    """Return the changed household, the market shock to apply, and a description of what changed."""
    data = household.model_dump()
    changes: list[Change] = []
    goals, accounts, ss, people = data["goals"], data["accounts"], data["social_security"], data["people"]

    def change(field: str, label: str, before: str, after: str) -> None:
        if before != after:
            changes.append(Change(field=field, label=label, before=before, after=after))

    def set_home(years: int | None, label: str = "Home purchase") -> None:
        change("home_purchase_in_years", label, _years(goals["home_purchase_in_years"]), _years(years))
        goals["home_purchase_in_years"] = years

    for preset in presets:
        if preset == "home_next_year":
            set_home(1)
        elif preset == "spouse_b_income_cut":
            if len(people) < 2:
                raise WhatIfError("There is no second earner to change.")
            before = people[1]["wages"]
            people[1]["wages"] = before * (1.0 - SPOUSE_INCOME_CUT)
            change("spouse_wages", "Spouse B income", _money(before), _money(people[1]["wages"]))
        elif preset == "retire_57":
            if household.primary_age >= EARLY_RETIREMENT_AGE:
                raise WhatIfError("Retiring at 57 is not in the future for this household.")
            change("retirement_age", "Retirement age", str(goals["retirement_age"]), str(EARLY_RETIREMENT_AGE))
            goals["retirement_age"] = EARLY_RETIREMENT_AGE
        elif preset == "market_drop_30":
            shock = MarketShock(year=1, equity_return=MARKET_DROP)
            change("market_shock", "Stock market", "no shock", "down 30% next year")

    if edits.retirement_age is not None:
        change("retirement_age", "Retirement age", str(goals["retirement_age"]), str(edits.retirement_age))
        goals["retirement_age"] = edits.retirement_age
    if edits.retirement_spending is not None:
        change("retirement_spending", "Retirement spending", _money(goals["retirement_spending"]), _money(edits.retirement_spending))
        goals["retirement_spending"] = edits.retirement_spending
    if edits.remove_home_purchase:
        set_home(None)
    elif edits.home_purchase_in_years is not None:
        set_home(edits.home_purchase_in_years)
    if edits.home_down_payment is not None:
        change("home_down_payment", "Down payment", _money(goals["home_down_payment"]), _money(edits.home_down_payment))
        goals["home_down_payment"] = edits.home_down_payment
    if edits.remove_college:
        change("college_starts_in_years", "College", _years(goals["college_starts_in_years"]), "none")
        goals["college_starts_in_years"] = None
    elif edits.college_starts_in_years is not None:
        change("college_starts_in_years", "College starts", _years(goals["college_starts_in_years"]), _years(edits.college_starts_in_years))
        goals["college_starts_in_years"] = edits.college_starts_in_years
    if edits.college_annual_cost is not None:
        change("college_annual_cost", "College cost a year", _money(goals["college_annual_cost"]), _money(edits.college_annual_cost))
        goals["college_annual_cost"] = edits.college_annual_cost
    if edits.primary_wages is not None:
        change("primary_wages", "Primary income", _money(people[0]["wages"]), _money(edits.primary_wages))
        people[0]["wages"] = edits.primary_wages
    if edits.spouse_wages is not None:
        if len(people) < 2:
            raise WhatIfError("There is no second earner to change.")
        change("spouse_wages", "Spouse B income", _money(people[1]["wages"]), _money(edits.spouse_wages))
        people[1]["wages"] = edits.spouse_wages
    if edits.social_security_annual is not None:
        change("social_security_annual", "Social Security", _money(ss["annual_benefit"]), _money(edits.social_security_annual))
        ss["annual_benefit"] = edits.social_security_annual
    if edits.roth_balance is not None:
        change("roth_balance", "Roth IRA", _money(accounts["roth_balance"]), _money(edits.roth_balance))
        accounts["roth_balance"] = edits.roth_balance
    if edits.cash is not None:
        change("cash", "Cash", _money(accounts["cash"]), _money(edits.cash))
        accounts["cash"] = edits.cash

    try:
        changed = Household.model_validate(data)
    except ValueError as exc:
        raise WhatIfError(str(exc)) from exc
    return changed, shock, changes
