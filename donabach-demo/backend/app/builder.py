"""Build the household from parsed documents, the user's corrections and their answers.

Values come from the parsed documents unless the user corrected them (`overrides`). A value the
parser could not read, and the user did not supply, is reported rather than silently defaulted.
The Roth balance and cash are read from a Roth IRA statement and from the brokerage statement's cash
line when the documents have them; otherwise, like the Social Security estimate (never on a document),
they come from the answers and are labelled "Estimated".
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

# Plain-language names for the values the household cannot be built without, for the case where no
# uploaded document contained the field at all (so there is no parsed label to borrow).
REQUIRED_LABELS = {
    "taxpayer_age": "Taxpayer age",
    "spouse_age": "Spouse age",
    "child_age_1": "Age of child 1",
    "w2_wages_taxpayer": "Taxpayer W-2 wages (box 1)",
    "w2_wages_spouse": "Spouse W-2 wages (box 1)",
}


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
            label = field.label if field is not None else REQUIRED_LABELS.get(key, key.replace("_", " "))
            self.missing[key] = MissingField(key=key, label=label)
        return default

    def meta_text(self, key: str) -> str:
        """A text field's value ("" when absent), with the user's correction applied."""
        value = self.overrides.get(key)
        if value is None and key in self.by_key:
            value = self.by_key[key].value
        return str(value).strip() if value is not None else ""

    def equity_share(self, prefix: str) -> float | None:
        """Stock share of an allocation table (`alloc` or `roth_alloc`); None when there is none."""
        keys = [f"{prefix}_{i}_value" for i in range(1, 20) if self.has(f"{prefix}_{i}_value")]
        allocated = sum(self.number(k, required=False) for k in keys)
        if allocated <= 0:
            return None
        equity = sum(self.number(k, required=False) for k in keys if self.meta(k, "asset_class") == "equity")
        return min(1.0, max(0.0, equity / allocated))

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
    name = f.meta_text("taxpayer_name")
    people = [Person(name=name, age=primary_age or 18, wages=taxpayer_wages, pretax_401k=taxpayer_deferral)]
    if f.has("spouse_age"):
        spouse_deferral = f.number("k401_contrib_spouse", required=False)
        spouse_wages = f.number("w2_wages_spouse") + spouse_deferral
        people.append(Person(name="", age=int(f.number("spouse_age")), wages=spouse_wages, pretax_401k=spouse_deferral))

    # --- children
    n_children = int(f.number("children_under_17", required=False))
    child_age = int(f.number("child_age_1", required=n_children > 0)) if n_children else 0
    children = [child_age] * n_children

    # --- accounts
    pretax_total = f.number("k401_total_balance", required=False)
    pretax_share = f.equity_share("alloc")
    roth_from_docs = f.has("roth_total_balance")
    cash_from_docs = f.has("brokerage_cash")
    roth_share = f.equity_share("roth_alloc")
    accounts = Accounts(
        brokerage_value=f.number("brokerage_total_value", required=False),
        brokerage_basis=f.number("brokerage_cost_basis", required=False),
        pretax_balance=pretax_total,
        pretax_equity_share=0.75 if pretax_share is None else pretax_share,
        roth_balance=f.number("roth_total_balance", required=False) if roth_from_docs else answers.roth_balance,
        roth_equity_share=1.0 if roth_share is None else roth_share,
        cash=f.number("brokerage_cash", required=False) if cash_from_docs else answers.cash,
    )
    estimated = [
        *([] if roth_from_docs else ["roth_balance"]),
        *([] if cash_from_docs else ["cash"]),
        "social_security",
    ]

    # Without a tax form there is no reported income: leave the snapshot empty so the profile's tax
    # picture is estimated from the wages and balances (and says so) rather than shown as all zeros.
    snapshot = (
        IncomeSnapshot(
            wages_after_401k=f.number("wages_1a", required=False),
            interest=f.number("taxable_interest_2b", required=False),
            qualified_dividends=f.number("qualified_dividends_3a", required=False),
            ordinary_dividends=f.number("ordinary_dividends_3b", required=False),
            net_capital_gain=f.number("capital_gain_7", required=False),
        )
        if f.has("wages_1a")
        else None
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
        charitable_giving=answers.charitable_giving,
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
        estimated=estimated,
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
        AccountLine(
            label="Roth IRA",
            amount=a.roth_balance,
            estimated="roth_balance" in household.estimated,
            detail="Estimated" if "roth_balance" in household.estimated else f"{a.roth_equity_share * 100:.0f}% stocks, Roth",
        ),
        AccountLine(
            label="Cash",
            amount=a.cash,
            estimated="cash" in household.estimated,
            detail="Estimated" if "cash" in household.estimated else "From the brokerage statement",
        ),
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
        tax_estimated=household.snapshot is None,
        total_assets=sum(line.amount for line in accounts),
    )
