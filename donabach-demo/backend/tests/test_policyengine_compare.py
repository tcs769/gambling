"""Optional cross-check of the tax engine against PolicyEngine-US (skipped when not installed).

    pip install policyengine-us        # large; kept out of requirements.txt on purpose
    python -m pytest tests/test_policyengine_compare.py -s

Every household below matches PolicyEngine-US (2.38.13, tax year 2026, Illinois) to the cent on AGI,
taxable income, tax before credits, child tax credit, NIIT, federal income tax and Illinois tax,
including filers 65 and over (the additional standard deduction of $1,650 per spouse and Illinois'
additional $1,000 exemption per spouse).

One deliberate difference: PolicyEngine also applies the 2025-2028 "senior deduction" of $6,000 per
spouse (One Big Beautiful Bill Act), which expires long before the households this app plans for
reach 65. The project spec leaves it out, so every comparison here switches it off in PolicyEngine
with a reform. `test_default_policyengine_adds_the_senior_deduction` documents what it would add.
"""

from __future__ import annotations

import warnings

import pytest

from app.tax.engine import TaxInputs, compute_return

pytest.importorskip("policyengine_us")
from policyengine_us import Simulation  # noqa: E402

warnings.filterwarnings("ignore")
YEAR = "2026"
SENIOR_DEDUCTION_PER_SPOUSE = 6_000.0  # OBBBA senior deduction, switched off below
NO_SENIOR_DEDUCTION = {"gov.irs.deductions.senior_deduction.amount": {"2026-01-01.2026-12-31": 0}}


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
    "update 4 audit: the advisor sells $1,000,000 of stock bought for $400,000 (NIIT, 20% bracket, Illinois without exemptions)": (
        [60, 59],
        [],
        dict(employment_income=150_000, qualified_dividend_income=5_000, long_term_capital_gains=600_000),
        dict(wages=150_000, qualified_dividends=5_000, ordinary_dividends=5_000, net_capital_gain=600_000),
    ),
    "update 4 audit: the same year without the sale": (
        [60, 59],
        [],
        dict(employment_income=150_000, qualified_dividend_income=5_000),
        dict(wages=150_000, qualified_dividends=5_000, ordinary_dividends=5_000),
    ),
    "survivor, single and 70: Social Security, IRA withdrawals and a long-term gain (single brackets and 0% gain bracket)": (
        [70],
        [],
        dict(taxable_ira_distributions=45_000, social_security=36_000, long_term_capital_gains=30_000, qualified_dividend_income=4_000, taxable_interest_income=2_000),
        dict(retirement_distributions=45_000, social_security=36_000, net_capital_gain=30_000, qualified_dividends=4_000, ordinary_dividends=4_000, interest=2_000, aged_spouses=1, single=True),
    ),
    "survivor, single and 66: a Roth conversion and gains (22% bracket, 15% gains, Social Security tiers)": (
        [66],
        [],
        dict(taxable_ira_distributions=20_000, taxable_roth_conversions=60_000, social_security=28_000, long_term_capital_gains=90_000),
        dict(retirement_distributions=20_000, roth_conversions=60_000, social_security=28_000, net_capital_gain=90_000, aged_spouses=1, single=True),
    ),
    "survivor, single and 72: income over $200,000 (net investment income tax, single threshold)": (
        [72],
        [],
        dict(taxable_ira_distributions=60_000, social_security=40_000, long_term_capital_gains=120_000, qualified_dividend_income=20_000),
        dict(retirement_distributions=60_000, social_security=40_000, net_capital_gain=120_000, qualified_dividends=20_000, ordinary_dividends=20_000, aged_spouses=1, single=True),
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
    "65+: both spouses aged (additional standard deduction and Illinois exemption)": (
        [66, 67],
        [],
        dict(
            employment_income=40_000,
            taxable_interest_income=2_000,
            taxable_ira_distributions=70_000,
            qualified_dividend_income=3_000,
            long_term_capital_gains=8_000,
        ),
        dict(
            wages=40_000,
            interest=2_000,
            retirement_distributions=70_000,
            qualified_dividends=3_000,
            ordinary_dividends=3_000,
            net_capital_gain=8_000,
            aged_spouses=2,
        ),
    ),
    "65+: only one spouse aged": (
        [66, 60],
        [],
        dict(employment_income=30_000, taxable_ira_distributions=50_000, long_term_capital_gains=12_000),
        dict(wages=30_000, retirement_distributions=50_000, net_capital_gain=12_000, aged_spouses=1),
    ),
    "65+: Social Security at 85%, an RMD-sized withdrawal and a Roth conversion": (
        [75, 74],
        [],
        dict(taxable_ira_distributions=40_000, taxable_roth_conversions=60_000, social_security=50_000),
        dict(retirement_distributions=40_000, roth_conversions=60_000, social_security=50_000, aged_spouses=2),
    ),
    "65+: Illinois base income with no retirement subtractions": (
        [69, 69],
        [],
        dict(taxable_interest_income=30_000, non_qualified_dividend_income=15_000, qualified_dividend_income=15_000,
             long_term_capital_gains=40_000),
        dict(interest=30_000, qualified_dividends=15_000, ordinary_dividends=30_000, net_capital_gain=40_000, aged_spouses=2),
    ),
}


def _pe(sim, variable):
    return float(sim.calculate(variable, YEAR)[0])


def _simulation(ages, children, pe_income, senior_deduction=False):
    situation = _situation(ages, children, pe_income)
    if senior_deduction:
        return Simulation(situation=situation)
    return Simulation(situation=situation, reform=NO_SENIOR_DEDUCTION)


def _compare(ages, children, pe_income, ours, senior_deduction=False):
    return _simulation(ages, children, pe_income, senior_deduction), compute_return(TaxInputs(**ours))


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
    assert r.il_exemptions == pytest.approx(_pe(sim, "il_total_exemptions"), abs=0.01)
    assert r.illinois_tax == pytest.approx(_pe(sim, "il_income_tax"), abs=0.01)


def test_aged_households_are_in_the_comparison():
    """The 65+ cases exercise both the federal and the Illinois age provisions (not vacuously)."""
    aged = [n for n, (_, _, _, ours) in HOUSEHOLDS.items() if ours.get("aged_spouses")]
    assert len(aged) >= 4
    for name in aged:
        _, _, _, ours = HOUSEHOLDS[name]
        r = compute_return(TaxInputs(**ours))
        assert r.standard_deduction == 32_200 + 1_650 * ours["aged_spouses"]
    # the Illinois additional exemption changes real tax in the case with Illinois base income
    ages, children, pe_income, ours = HOUSEHOLDS["65+: Illinois base income with no retirement subtractions"]
    r = compute_return(TaxInputs(**ours))
    assert r.il_taxable_income > 0
    assert r.il_exemptions == 2 * 2_925 + 2 * 1_000


def test_default_policyengine_adds_the_senior_deduction():
    """What the OBBBA senior deduction would change (it is off in every comparison above)."""
    ages, children, pe_income, ours = HOUSEHOLDS["65+: both spouses aged (additional standard deduction and Illinois exemption)"]
    with_senior, r = _compare(ages, children, pe_income, ours, senior_deduction=True)
    assert r.agi == pytest.approx(_pe(with_senior, "adjusted_gross_income"), abs=0.01)
    assert r.taxable_income - _pe(with_senior, "taxable_income") == pytest.approx(2 * SENIOR_DEDUCTION_PER_SPOUSE, abs=0.01)
    assert r.federal_total > _pe(with_senior, "income_tax")  # this engine is slightly higher
    assert r.illinois_tax == pytest.approx(_pe(with_senior, "il_income_tax"), abs=0.01)
