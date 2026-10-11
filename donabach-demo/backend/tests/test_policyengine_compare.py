"""Optional cross-check of the tax engine against PolicyEngine-US (skipped when not installed).

    pip install policyengine-us        # large; kept out of requirements.txt on purpose
    python -m pytest tests/test_policyengine_compare.py -s

Results when this was written (policyengine-us 2.38.13, tax year 2026, Illinois): every
household below matches to the cent on AGI, taxable income, tax before credits, child tax
credit, NIIT, federal income tax and Illinois tax, except the one documented difference:

  * Age 65+ households. PolicyEngine adds the age-65 standard deduction increment ($1,650 per
    spouse) and the 2025-2028 "senior deduction" ($6,000 per spouse). The project spec uses the
    plain $32,200 standard deduction only, so this engine over-states tax for filers 65+ by the
    tax on $15,300 of income. The planner applies this equally to every strategy.
"""

from __future__ import annotations

import warnings

import pytest

from app.tax.engine import TaxInputs, compute_return

pytest.importorskip("policyengine_us")
from policyengine_us import Simulation  # noqa: E402

warnings.filterwarnings("ignore")
YEAR = "2026"
# Age 65+ additional standard deduction (2 x 1,650) + OBBBA senior deduction (2 x 6,000).
SENIOR_EXTRA_DEDUCTION = 3_300.0 + 12_000.0


def _situation(ages, children, person_income):
    people, members = {}, []
    for i, age in enumerate(ages):
        pid = "head" if i == 0 else "spouse"
        people[pid] = {"age": {YEAR: age}}
        members.append(pid)
    for j, age in enumerate(children):
        people[f"child{j}"] = {"age": {YEAR: age}}
        members.append(f"child{j}")
    for var, val in person_income.items():
        people["head"][var] = {YEAR: val}
    return {
        "people": people,
        "tax_units": {"tax_unit": {"members": members}},
        "spm_units": {"spm_unit": {"members": members}},
        "households": {"household": {"members": members, "state_name": {YEAR: "IL"}}},
        "marital_units": {"marital_unit": {"members": members[: len(ages)]}},
        "families": {"family": {"members": members}},
    }


# name -> (ages, children ages, PolicyEngine person income, our TaxInputs)
HOUSEHOLDS = {
    "demo household": (
        [38, 37],
        [8],
        dict(
            employment_income=201_000,
            taxable_interest_income=800,
            qualified_dividend_income=2_700,
            non_qualified_dividend_income=300,
            long_term_capital_gains=1_500,
        ),
        dict(
            wages=201_000,
            interest=800,
            qualified_dividends=2_700,
            ordinary_dividends=3_000,
            net_capital_gain=1_500,
            children_under_17=1,
        ),
    ),
    "high earners: NIIT and child-credit phase-out": (
        [45, 44],
        [10, 12],
        dict(
            employment_income=380_000,
            taxable_interest_income=20_000,
            qualified_dividend_income=10_000,
            non_qualified_dividend_income=5_000,
            long_term_capital_gains=60_000,
        ),
        dict(
            wages=380_000,
            interest=20_000,
            qualified_dividends=10_000,
            ordinary_dividends=15_000,
            net_capital_gain=60_000,
            children_under_17=2,
        ),
    ),
    "retirees: IRA withdrawals and gains, gains straddle the 0% bracket": (
        [64, 63],
        [],
        dict(taxable_ira_distributions=70_000, qualified_dividend_income=3_000, long_term_capital_gains=8_000),
        dict(
            retirement_distributions=70_000,
            qualified_dividends=3_000,
            ordinary_dividends=3_000,
            net_capital_gain=8_000,
        ),
    ),
    "early retirees: Social Security at 85% taxable": (
        [63, 62],
        [],
        dict(taxable_ira_distributions=80_000, social_security=50_000),
        dict(retirement_distributions=80_000, social_security=50_000),
    ),
    "Roth conversion year (Illinois subtracts it)": (
        [62, 61],
        [],
        dict(taxable_ira_distributions=40_000, taxable_roth_conversions=150_000),
        dict(retirement_distributions=40_000, roth_conversions=150_000),
    ),
    "net capital loss limited to $3,000": (
        [40, 40],
        [],
        dict(employment_income=100_000, long_term_capital_gains=-10_000),
        dict(wages=100_000, net_capital_gain=-10_000),
    ),
}


def _pe(sim, variable):
    return float(sim.calculate(variable, YEAR)[0])


def _compare(ages, children, pe_income, ours):
    sim = Simulation(situation=_situation(ages, children, pe_income))
    r = compute_return(TaxInputs(**ours))
    return sim, r


@pytest.mark.parametrize("name", list(HOUSEHOLDS))
def test_matches_policyengine(name):
    ages, children, pe_income, ours = HOUSEHOLDS[name]
    sim, r = _compare(ages, children, pe_income, ours)
    assert r.agi == pytest.approx(_pe(sim, "adjusted_gross_income"), abs=0.01)
    assert r.taxable_income == pytest.approx(_pe(sim, "taxable_income"), abs=0.01)
    assert r.ordinary_tax + r.capital_gains_tax == pytest.approx(_pe(sim, "income_tax_before_credits"), abs=0.01)
    assert r.child_tax_credit == pytest.approx(_pe(sim, "ctc"), abs=0.01)
    assert r.niit == pytest.approx(_pe(sim, "net_investment_income_tax"), abs=0.01)
    assert r.federal_total == pytest.approx(_pe(sim, "income_tax"), abs=0.01)
    assert r.illinois_tax == pytest.approx(_pe(sim, "il_income_tax"), abs=0.01)


def test_documented_difference_for_filers_over_65():
    """The spec's plain standard deduction ignores the age-65 and senior deductions."""
    ages, children, pe_income, ours = HOUSEHOLDS["early retirees: Social Security at 85% taxable"]
    sim, r = _compare([68, 67], children, pe_income, ours)
    assert r.agi == pytest.approx(_pe(sim, "adjusted_gross_income"), abs=0.01)
    assert r.taxable_income - _pe(sim, "taxable_income") == pytest.approx(SENIOR_EXTRA_DEDUCTION, abs=0.01)
    assert r.federal_total > _pe(sim, "income_tax")  # we are slightly conservative
    assert r.illinois_tax == pytest.approx(_pe(sim, "il_income_tax"), abs=0.01)
