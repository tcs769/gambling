"""Build the household from parsed documents, the user's corrections and their answers.

Values come from the parsed documents unless the user corrected them (`overrides`). A value the
parser could not read, and the user did not supply, is reported rather than silently defaulted.
Roth balance, cash and the Social Security estimate are not on any document; they come from the
answers and are labelled "Estimated".
"""

from __future__ import annotations

from app.api_models import AccountLine, Answers, GoalLine, HouseholdProfile, MissingField
from app.docs.models import ParsedDocument, ParsedField
from app.schemas import (
    Accounts,
    Goals,
    Household,
    IncomeSnapshot,
    Person,
    SocialSecurity,
)
from app.tax.picture import current_tax_return

ESTIMATED = ("roth_balance", "cash", "social_security")


class MissingFieldsError(Exception):
    def __init__(self, missing: list[MissingField]):
        super().__init__("Some values could not be read: " + ", ".join(m.label for m in missing))
        self.missing = missing


class _Fields:
    """Parsed fields by key, with the user's corrections applied."""

    def __init__(self, documents: list[ParsedDocument], overrides: dict[str, float | str]):
        self.by_key: dict[str, ParsedField] = {f.key: f for d in documents for f in d.fields}
        self.overrides = overrides
        self.missing: dict[str, MissingField] = {}

    def has(self, key: str) -> bool:
        return key in self.overrides or (key in self.by_key and self.by_key[key].value is not None)

    def number(self, key: str, required: bool = True, default: float = 0.0) -> float:
        if key in self.overrides:
            return float(self.overrides[key])
        field = self.by_key.get(key)
        if field is not None and field.value is not None:
            return float(field.value)
        if required:
            label = field.label if field is not None else key.replace("_", " ")
            self.missing[key] = MissingField(key=key, label=label)
        return default

    def meta(self, key: str, name: str) -> str | float | None:
        field = self.by_key.get(key)
        return field.meta.get(name) if field is not None else None


def build_household(
    documents: list[ParsedDocument], overrides: dict[str, float | str], answers: Answers
) -> Household:
    f = _Fields(documents, overrides)

    # --- people
    primary_age = int(f.number("taxpayer_age"))
    taxpayer_deferral = f.number("k401_contrib_taxpayer", required=False)
    taxpayer_wages = f.number("w2_wages_taxpayer") + taxpayer_deferral
    people = [Person(name="", age=primary_age or 18, wages=taxpayer_wages, pretax_401k=taxpayer_deferral)]
    if f.has("spouse_age"):
        spouse_deferral = f.number("k401_contrib_spouse", required=False)
        spouse_wages = f.number("w2_wages_spouse") + spouse_deferral
        people.append(Person(name="", age=int(f.number("spouse_age")), wages=spouse_wages, pretax_401k=spouse_deferral))

    # --- children
    n_children = int(f.number("children_under_17", required=False))
    child_age = int(f.number("child_age_1", required=n_children > 0)) if n_children else 0
    children = [child_age] * n_children

    # --- accounts
    equity_value = sum(
        f.number(f"alloc_{i}_value", required=False)
        for i in range(1, 20)
        if f.has(f"alloc_{i}_value") and f.meta(f"alloc_{i}_value", "asset_class") == "equity"
    )
    allocated = sum(f.number(f"alloc_{i}_value", required=False) for i in range(1, 20) if f.has(f"alloc_{i}_value"))
    pretax_total = f.number("k401_total_balance", required=False)
    equity_share = equity_value / allocated if allocated > 0 else 0.75
    accounts = Accounts(
        brokerage_value=f.number("brokerage_total_value", required=False),
        brokerage_basis=f.number("brokerage_cost_basis", required=False),
        pretax_balance=pretax_total,
        pretax_equity_share=min(1.0, max(0.0, equity_share)),
        roth_balance=answers.roth_balance,
        cash=answers.cash,
    )

    snapshot = IncomeSnapshot(
        wages_after_401k=f.number("wages_1a", required=False),
        interest=f.number("taxable_interest_2b", required=False),
        qualified_dividends=f.number("qualified_dividends_3a", required=False),
        ordinary_dividends=f.number("ordinary_dividends_3b", required=False),
        net_capital_gain=f.number("capital_gain_7", required=False),
    )

    if f.missing:
        raise MissingFieldsError(list(f.missing.values()))

    goals = Goals(
        home_purchase_in_years=answers.home_purchase_in_years,
        home_down_payment=answers.home_down_payment,
        college_starts_in_years=answers.college_starts_in_years,
        college_annual_cost=answers.college_annual_cost,
        college_years=answers.college_years,
        retirement_age=answers.retirement_age,
        retirement_spending=answers.retirement_spending,
    )
    return Household(
        people=people,
        children_ages=children,
        accounts=accounts,
        goals=goals,
        social_security=SocialSecurity(
            annual_benefit=answers.social_security_annual, start_age=answers.social_security_start_age
        ),
        snapshot=snapshot,
        estimated=list(ESTIMATED),
    )


def _money(x: float) -> str:
    return f"${x:,.0f}"


def household_profile(household: Household) -> HouseholdProfile:
    a, g, ss = household.accounts, household.goals, household.social_security
    unrealized = max(0.0, a.brokerage_value - a.brokerage_basis)
    accounts = [
        AccountLine(
            label="401(k) and IRA",
            amount=a.pretax_balance,
            detail=f"{a.pretax_equity_share * 100:.0f}% stocks, pre-tax",
        ),
        AccountLine(
            label="Taxable brokerage",
            amount=a.brokerage_value,
            detail=f"Cost basis {_money(a.brokerage_basis)}, unrealized gain {_money(unrealized)}",
        ),
        AccountLine(label="Roth IRA", amount=a.roth_balance, estimated=True, detail="Estimated"),
        AccountLine(label="Cash", amount=a.cash, estimated=True, detail="Estimated"),
    ]
    goals: list[GoalLine] = []
    if g.home_purchase_in_years is not None:
        goals.append(
            GoalLine(
                label="Home purchase",
                detail=f"{_money(g.home_down_payment)} down in {g.home_purchase_in_years} "
                f"{'year' if g.home_purchase_in_years == 1 else 'years'}",
            )
        )
    if g.college_starts_in_years is not None and g.college_years > 0:
        goals.append(
            GoalLine(
                label="College",
                detail=f"{_money(g.college_annual_cost)} a year for {g.college_years} years, "
                f"starting in {g.college_starts_in_years} years",
            )
        )
    goals.append(
        GoalLine(
            label="Retirement",
            detail=f"Retire at {g.retirement_age}, spending {_money(g.retirement_spending)} a year",
        )
    )
    goals.append(
        GoalLine(
            label="Social Security",
            detail=f"{_money(ss.annual_benefit)} a year from age {ss.start_age}",
            estimated=True,
        )
    )
    tax = current_tax_return(household)
    return HouseholdProfile(
        household=household,
        accounts=accounts,
        goals=goals,
        tax_return=tax,
        tax_lines=tax.lines(),
        estimated=list(household.estimated),
        total_assets=sum(line.amount for line in accounts),
    )
