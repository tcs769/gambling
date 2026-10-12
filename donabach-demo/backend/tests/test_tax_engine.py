"""M1: tax engine tests (federal MFJ + Illinois, tax year 2026)."""

from __future__ import annotations

import math

import pytest

from app.tax import params_2026 as P
from app.tax.engine import (
    TaxInputs,
    compute_return,
    marginal_rate,
    ordinary_tax,
    pretax_withdrawal_rate,
    tax_core,
)

APPROX = {"abs": 0.005}


def ret(**kw):
    return compute_return(TaxInputs(**kw))


# --- 1. Bracket math -----------------------------------------------------------------------


def test_bracket_math_168800_is_26560():
    # 24,800 x 10% + 76,000 x 12% + 68,000 x 22% = 2,480 + 9,120 + 14,960
    assert ordinary_tax(168_800.0) == pytest.approx(26_560.0, **APPROX)


def test_bracket_math_through_the_return():
    r = ret(wages=168_800 + P.STANDARD_DEDUCTION_MFJ)
    assert r.taxable_income == pytest.approx(168_800.0)
    assert r.ordinary_tax == pytest.approx(26_560.0, **APPROX)
    assert r.federal_total == pytest.approx(26_560.0, **APPROX)


@pytest.mark.parametrize(
    ("taxable", "expected"),
    [
        (0.0, 0.0),
        (24_800.0, 2_480.0),
        (100_800.0, 2_480.0 + 76_000 * 0.12),
        (211_400.0, 2_480.0 + 76_000 * 0.12 + 110_600 * 0.22),
        (403_550.0, 2_480.0 + 76_000 * 0.12 + 110_600 * 0.22 + 192_150 * 0.24),
        (
            768_700.0,
            2_480.0
            + 76_000 * 0.12
            + 110_600 * 0.22
            + 192_150 * 0.24
            + 108_900 * 0.32
            + 256_250 * 0.35,
        ),
        (
            1_000_000.0,
            2_480.0
            + 76_000 * 0.12
            + 110_600 * 0.22
            + 192_150 * 0.24
            + 108_900 * 0.32
            + 256_250 * 0.35
            + 231_300 * 0.37,
        ),
    ],
)
def test_bracket_boundaries(taxable, expected):
    assert ordinary_tax(taxable) == pytest.approx(expected, **APPROX)


def test_negative_or_zero_income_owes_nothing():
    r = ret()
    assert r.federal_total == 0.0
    assert r.illinois_tax == 0.0
    assert r.grand_total == 0.0


def test_below_standard_deduction_owes_nothing_federally():
    r = ret(wages=30_000)
    assert r.taxable_income == 0.0
    assert r.federal_total == 0.0


@pytest.mark.parametrize(
    ("ordinary_taxable", "rate"),
    [
        (0.0, 0.10),
        (24_799.99, 0.10),
        (24_800.0, 0.12),  # a filled bracket: the next dollar is taxed at the next rate
        (100_800.0, 0.22),
        (211_399.0, 0.22),
        (211_400.0, 0.24),
        (768_700.0, 0.37),
        (5_000_000.0, 0.37),
    ],
)
def test_marginal_rate(ordinary_taxable, rate):
    assert marginal_rate(ordinary_taxable) == rate


# --- 2. Illinois ---------------------------------------------------------------------------


def test_illinois_two_children_agi_120k():
    r = ret(wages=120_000, children_under_17=2)
    assert r.agi == pytest.approx(120_000.0)
    assert r.il_exemptions == pytest.approx(4 * 2_925.0)  # two taxpayers + two dependents
    assert r.il_base_income == pytest.approx(120_000.0)
    assert r.il_taxable_income == pytest.approx(108_300.0)
    assert r.illinois_tax == pytest.approx(5_360.85, **APPROX)


def test_illinois_dependents_can_differ_from_credit_children():
    # A 20-year-old college student is a dependent but no longer earns the child tax credit.
    r = ret(wages=120_000, children_under_17=0, dependents=1)
    assert r.il_exemptions == pytest.approx(3 * 2_925.0)
    assert r.child_tax_credit == 0.0


def test_illinois_exemptions_disallowed_above_500k_agi():
    at_limit = ret(wages=500_000, children_under_17=1)
    over = ret(wages=500_001, children_under_17=1)
    assert at_limit.il_exemptions == pytest.approx(3 * 2_925.0)
    assert over.il_exemptions == 0.0
    assert over.illinois_tax == pytest.approx(P.IL_RATE * 500_001, **APPROX)


def test_illinois_subtracts_retirement_income_and_social_security():
    r = ret(
        wages=50_000,
        retirement_distributions=40_000,
        roth_conversions=20_000,
        social_security=50_000,
    )
    taxable_ss = 0.85 * 50_000
    assert r.agi == pytest.approx(50_000 + 40_000 + 20_000 + taxable_ss)
    assert r.il_base_income == pytest.approx(50_000.0)  # wages only
    assert r.il_taxable_income == pytest.approx(50_000 - 2 * 2_925.0)


def test_illinois_taxes_investment_income():
    r = ret(interest=1_000, ordinary_dividends=3_000, qualified_dividends=2_700, net_capital_gain=5_000)
    assert r.il_base_income == pytest.approx(9_000.0)


# --- 3. Roth conversion --------------------------------------------------------------------


def test_roth_conversion_raises_federal_tax_but_not_illinois():
    base = ret(wages=150_000, children_under_17=1)
    conv = ret(wages=150_000, children_under_17=1, roth_conversions=60_000)
    assert conv.federal_total > base.federal_total
    assert conv.illinois_tax == pytest.approx(base.illinois_tax, abs=1e-9)
    assert conv.agi == pytest.approx(base.agi + 60_000)


def test_roth_conversion_is_taxed_as_ordinary_income():
    r = ret(roth_conversions=100_000)
    assert r.ordinary_taxable_income == pytest.approx(100_000 - P.STANDARD_DEDUCTION_MFJ)


# --- 4. Capital gains stacking -------------------------------------------------------------


def _gains_return(ordinary_taxable, gains):
    # wages chosen so that ordinary taxable income is exactly `ordinary_taxable`
    return ret(wages=ordinary_taxable + P.STANDARD_DEDUCTION_MFJ, net_capital_gain=gains)


def test_gains_entirely_in_zero_bracket():
    r = _gains_return(50_000, 10_000)
    assert r.capital_gains_tax == 0.0
    assert r.preferential_income == pytest.approx(10_000)


def test_gains_straddle_zero_fifteen_boundary():
    # Ordinary taxable income 90,000; gains stack 90,000 -> 110,000.
    # 8,900 fall under the 98,900 threshold (0%), 11,100 are taxed at 15%.
    r = _gains_return(90_000, 20_000)
    assert r.ordinary_tax == pytest.approx(ordinary_tax(90_000.0), **APPROX)
    assert r.capital_gains_tax == pytest.approx(0.15 * 11_100, **APPROX)


def test_gains_entirely_at_fifteen():
    r = _gains_return(150_000, 20_000)
    assert r.capital_gains_tax == pytest.approx(0.15 * 20_000, **APPROX)


def test_gains_straddle_fifteen_twenty_boundary():
    # Stack 600,000 -> 650,000: 13,700 at 15%, 36,300 at 20%.
    r = _gains_return(600_000, 50_000)
    assert r.capital_gains_tax == pytest.approx(0.15 * 13_700 + 0.20 * 36_300, **APPROX)


def _dividend_return(ordinary_taxable, qualified):
    # All dividends qualified; wages chosen so ordinary taxable income is `ordinary_taxable`.
    return ret(
        wages=ordinary_taxable + P.STANDARD_DEDUCTION_MFJ,
        ordinary_dividends=qualified,
        qualified_dividends=qualified,
    )


def test_qualified_dividends_stack_like_gains():
    # 20,000 of qualified dividends on top of 70,000 of ordinary income: 70,000 -> 90,000 sits
    # entirely inside the 0% zone.
    inside = _dividend_return(70_000, 20_000)
    assert inside.ordinary_taxable_income == pytest.approx(70_000.0)
    assert inside.capital_gains_tax == 0.0
    # On top of 90,000 the stack runs 90,000 -> 110,000: 11,100 above the 98,900 threshold.
    straddle = _dividend_return(90_000, 20_000)
    assert straddle.capital_gains_tax == pytest.approx(0.15 * 11_100, **APPROX)


def test_gains_with_low_income_use_remaining_zero_bracket():
    # AGI 60,000 -> taxable 27,800, of which 20,000 is gain: only 7,800 is ordinary income.
    r = ret(wages=40_000, net_capital_gain=20_000)
    assert r.ordinary_taxable_income == pytest.approx(7_800.0)
    assert r.ordinary_tax == pytest.approx(780.0, **APPROX)
    assert r.capital_gains_tax == 0.0
    assert r.federal_total == pytest.approx(780.0, **APPROX)


def test_stacking_moves_gains_up_when_ordinary_income_rises():
    low = _gains_return(50_000, 30_000)
    high = _gains_return(100_000, 30_000)
    assert low.capital_gains_tax == 0.0
    assert high.capital_gains_tax == pytest.approx(0.15 * 30_000, **APPROX)


# --- 5. NIIT -------------------------------------------------------------------------------


def test_niit_not_owed_at_or_below_250k():
    r = ret(wages=230_000, ordinary_dividends=20_000, qualified_dividends=20_000)
    assert r.agi == pytest.approx(250_000.0)
    assert r.niit == 0.0


def test_niit_applies_above_250k_on_the_excess():
    # MAGI 260,000 with 50,000 of investment income: 3.8% of the 10,000 excess.
    r = ret(wages=210_000, interest=20_000, ordinary_dividends=30_000, qualified_dividends=30_000)
    assert r.agi == pytest.approx(260_000.0)
    assert r.niit == pytest.approx(0.038 * 10_000, **APPROX)


def test_niit_limited_by_net_investment_income():
    # MAGI far above the threshold but only 20,000 of investment income.
    r = ret(wages=380_000, interest=20_000)
    assert r.niit == pytest.approx(0.038 * 20_000, **APPROX)


def test_niit_includes_capital_gains_and_roth_conversion_raises_magi_only():
    gains = ret(wages=240_000, net_capital_gain=30_000)
    assert gains.niit == pytest.approx(0.038 * 20_000, **APPROX)
    # A Roth conversion lifts MAGI but is not itself net investment income.
    conv = ret(wages=100_000, interest=10_000, roth_conversions=200_000)
    assert conv.niit == pytest.approx(0.038 * 10_000, **APPROX)


# --- 6. Child tax credit -------------------------------------------------------------------


def test_ctc_full_credit_up_to_threshold():
    r = ret(wages=400_000, children_under_17=2)
    assert r.child_tax_credit == pytest.approx(4_400.0)


@pytest.mark.parametrize(
    ("agi", "expected_credit"),
    [
        (400_000, 4_400.0),
        (400_001, 4_350.0),  # any fraction of $1,000 costs a full $50
        (400_999, 4_350.0),
        (401_000, 4_350.0),
        (401_001, 4_300.0),
        (420_000, 4_400.0 - 20 * 50),
        (487_999, 4_400.0 - 88 * 50),
        (488_000, 0.0),
        (600_000, 0.0),
    ],
)
def test_ctc_phaseout(agi, expected_credit):
    r = ret(wages=agi, children_under_17=2)
    assert r.child_tax_credit == pytest.approx(expected_credit, **APPROX)


def test_ctc_is_nonrefundable():
    # Tax before credits on 40,000 of wages is zero (below the standard deduction + 8k).
    r = ret(wages=36_000, children_under_17=2)
    assert r.taxable_income == pytest.approx(3_800.0)
    assert r.child_tax_credit == pytest.approx(380.0, **APPROX)  # limited to the 380 of tax
    assert r.federal_total == pytest.approx(0.0, abs=1e-9)


def test_ctc_does_not_offset_the_early_withdrawal_penalty():
    # Income tax is 380, fully absorbed by the credit; the 1,000 penalty is untouched.
    r = ret(wages=36_000, children_under_17=2, early_withdrawal_base=10_000)
    assert r.early_withdrawal_penalty == pytest.approx(1_000.0)
    assert r.child_tax_credit == pytest.approx(380.0, **APPROX)
    assert r.federal_total == pytest.approx(1_000.0, **APPROX)


def test_ctc_does_not_offset_niit():
    # MAGI 300,000 with 100,000 of interest: NIIT = 3.8% x 50,000 = 1,900 on top of income tax.
    r = ret(wages=200_000, interest=100_000, children_under_17=1)
    assert r.niit == pytest.approx(1_900.0, **APPROX)
    assert r.child_tax_credit == pytest.approx(2_200.0)
    assert r.federal_total == pytest.approx(r.ordinary_tax - 2_200.0 + 1_900.0, **APPROX)


# --- 7. Capital losses ---------------------------------------------------------------------


def test_ten_thousand_loss_deducts_three_and_carries_seven():
    r = ret(wages=100_000, net_capital_gain=-10_000)
    assert r.capital_loss_deducted == pytest.approx(3_000.0)
    assert r.capital_loss_carryforward_out == pytest.approx(7_000.0)
    assert r.capital_gain_line == pytest.approx(-3_000.0)
    assert r.agi == pytest.approx(97_000.0)


def test_carryforward_offsets_gains_first():
    r = ret(wages=100_000, net_capital_gain=10_000, capital_loss_carryforward=7_000)
    assert r.capital_gain_line == pytest.approx(3_000.0)
    assert r.capital_loss_carryforward_out == 0.0
    assert r.capital_loss_deducted == 0.0


def test_carryforward_larger_than_gain_continues_forward():
    r = ret(wages=100_000, net_capital_gain=2_000, capital_loss_carryforward=7_000)
    assert r.capital_loss_deducted == pytest.approx(3_000.0)
    assert r.capital_loss_carryforward_out == pytest.approx(2_000.0)


def test_small_loss_is_fully_deducted():
    r = ret(wages=100_000, net_capital_gain=-1_200)
    assert r.capital_loss_deducted == pytest.approx(1_200.0)
    assert r.capital_loss_carryforward_out == 0.0


def test_loss_carryforward_chain_over_three_years():
    carry = 0.0
    deducted = []
    for gain in (-10_000.0, 0.0, 0.0):
        r = ret(wages=100_000, net_capital_gain=gain, capital_loss_carryforward=carry)
        deducted.append(r.capital_loss_deducted)
        carry = r.capital_loss_carryforward_out
    assert deducted == [3_000.0, 3_000.0, 3_000.0]
    assert carry == pytest.approx(1_000.0)


# --- Other lines ---------------------------------------------------------------------------


def test_early_withdrawal_penalty_is_ten_percent_of_base():
    r = ret(retirement_distributions=40_000, early_withdrawal_base=40_000)
    assert r.early_withdrawal_penalty == pytest.approx(4_000.0)
    assert r.federal_total == pytest.approx(r.ordinary_tax + 4_000.0, **APPROX)


def test_social_security_is_taxed_by_the_provisional_income_formula_federally_and_not_by_illinois():
    # provisional income 40,000 + 25,000 = 65,000: 85% of the 21,000 over 44,000, plus the first tier (6,000)
    r = ret(wages=40_000, social_security=50_000)
    assert r.taxable_social_security == pytest.approx(0.85 * 21_000 + 6_000)
    assert r.agi == pytest.approx(40_000 + 23_850)
    assert r.il_base_income == pytest.approx(40_000.0)


@pytest.mark.parametrize(
    ("wages", "benefits", "taxable"),
    [
        (10_000, 30_000, 0.0),  # provisional 25,000, under the 32,000 base
        (25_000, 30_000, 4_000.0),  # provisional 40,000: half of the 8,000 over the base
        (29_000, 24_000, 4_500.0),  # provisional 41,000: half of 9,000, under half the benefits (12,000)
        (36_000, 20_000, 10_000.0),  # provisional 46,000: 0.85 x 2,000 + min(half the benefits = 10,000, 6,000) = 7,700 ... capped below
        (100_000, 50_000, 42_500.0),  # the 85% cap
    ],
)
def test_social_security_taxable_share_hand_cases(wages, benefits, taxable):
    r = ret(wages=wages, social_security=benefits)
    provisional = wages + 0.5 * benefits
    if provisional <= 32_000:
        expected = 0.0
    elif provisional <= 44_000:
        expected = min(0.5 * (provisional - 32_000), 0.5 * benefits)
    else:
        expected = min(0.85 * (provisional - 44_000) + min(0.5 * benefits, 6_000), 0.85 * benefits)
    assert r.taxable_social_security == pytest.approx(expected)
    if (wages, benefits) != (36_000, 20_000):
        assert r.taxable_social_security == pytest.approx(taxable)


def test_qualified_dividends_cannot_exceed_ordinary_dividends():
    r = ret(wages=150_000, ordinary_dividends=1_000, qualified_dividends=5_000)
    assert r.qualified_dividends == 1_000
    assert r.preferential_income == pytest.approx(1_000.0)


def test_demo_household_this_year():
    """The demo household's own return: the numbers that appear on the sample 1040."""
    r = ret(
        wages=140_000 + 110_000 - 49_000,
        interest=800,
        qualified_dividends=2_700,
        ordinary_dividends=3_000,
        net_capital_gain=1_500,
        children_under_17=1,
    )
    assert r.agi == pytest.approx(206_300.0)
    assert r.taxable_income == pytest.approx(174_100.0)
    assert r.preferential_income == pytest.approx(4_200.0)
    assert r.ordinary_taxable_income == pytest.approx(169_900.0)
    assert r.ordinary_tax == pytest.approx(2_480 + 9_120 + (169_900 - 100_800) * 0.22, **APPROX)
    assert r.capital_gains_tax == pytest.approx(0.15 * 4_200, **APPROX)
    assert r.niit == 0.0
    assert r.child_tax_credit == pytest.approx(2_200.0)
    assert r.federal_total == pytest.approx(25_232.0, **APPROX)
    assert r.marginal_federal_rate == 0.22


def test_effective_rates():
    r = ret(wages=201_000, children_under_17=1)
    assert r.effective_federal_rate == pytest.approx(r.federal_total / r.agi)
    assert r.effective_total_rate == pytest.approx(r.grand_total / r.agi)
    assert ret().effective_total_rate == 0.0


def test_lines_cover_the_return_in_order():
    r = ret(wages=201_000, children_under_17=1)
    lines = r.lines()
    labels = [line.label for line in lines]
    assert labels.index("Adjusted gross income") < labels.index("Taxable income")
    assert labels.index("Federal tax") < labels.index("Total income tax")
    total = next(line for line in lines if line.kind == "total")
    assert total.amount == pytest.approx(r.grand_total)


# --- Retirement balance valuation ----------------------------------------------------------


def test_pretax_withdrawal_rate_rises_with_the_balance():
    rates = [pretax_withdrawal_rate(b, 50_000.0) for b in (0.0, 200_000.0, 1_000_000.0, 3_000_000.0, 8_000_000.0)]
    assert rates[0] == 0.0
    assert all(a <= b for a, b in zip(rates, rates[1:], strict=False))
    assert 0.0 < rates[-1] < 0.37


def test_pretax_withdrawal_rate_matches_hand_calculation():
    # 1,000,000 / 20 = 50,000 a year beside 50,000 of benefits: provisional income 75,000 makes 0.85 x 31,000 + 6,000 = 32,350 of them
    # taxable (none are on their own: provisional income 25,000)
    withdrawal, taxable_ss = 50_000.0, 0.85 * 31_000 + 6_000
    with_w = ordinary_tax(withdrawal + taxable_ss - P.STANDARD_DEDUCTION_MFJ)
    assert pretax_withdrawal_rate(1_000_000.0, 50_000.0) == pytest.approx(with_w / withdrawal)


# --- Filers 65 and over, and required minimum distributions -------------------------------


def test_each_aged_spouse_adds_1650_to_the_standard_deduction():
    base = ret(wages=150_000)
    one = ret(wages=150_000, aged_spouses=1)
    two = ret(wages=150_000, aged_spouses=2)
    assert (base.standard_deduction, one.standard_deduction, two.standard_deduction) == (32_200, 33_850, 35_500)
    assert base.taxable_income - one.taxable_income == pytest.approx(1_650)
    assert base.taxable_income - two.taxable_income == pytest.approx(3_300)
    assert two.federal_total < one.federal_total < base.federal_total


def test_aged_deduction_is_not_the_senior_deduction():
    # The $6,000 senior deduction of the One Big Beautiful Bill Act is deliberately not modelled.
    assert P.STANDARD_DEDUCTION_AGED_PER_SPOUSE == 1_650.0
    assert ret(wages=150_000, aged_spouses=2).taxable_income == pytest.approx(150_000 - 35_500)


def test_illinois_adds_a_1000_exemption_per_aged_spouse():
    base = ret(interest=100_000)
    aged = ret(interest=100_000, aged_spouses=2)
    assert aged.il_exemptions - base.il_exemptions == pytest.approx(2_000)
    assert base.illinois_tax - aged.illinois_tax == pytest.approx(0.0495 * 2_000)
    # like every Illinois exemption, it disappears above $500,000 of AGI
    assert ret(interest=600_000, aged_spouses=2).il_exemptions == 0.0


def test_aged_deduction_lowers_the_rate_used_to_value_pre_tax_balances():
    plain = pretax_withdrawal_rate(2_000_000.0, 50_000.0)
    aged = pretax_withdrawal_rate(2_000_000.0, 50_000.0, 2.0)
    assert 0.0 < aged < plain
    # hand calculation: 100,000 withdrawn a year beside the Social Security it makes taxable (provisional income 125,000: the 85% cap, 42,500)
    deduction = 32_200 + 2 * 1_650
    expected = ordinary_tax(100_000 + 42_500 - deduction) / 100_000
    assert aged == pytest.approx(expected)


def test_rmd_start_age_follows_the_birth_year_under_current_law():
    assert P.rmd_start_age(1960) == 75 and P.rmd_start_age(1988) == 75 and P.rmd_start_age(2005) == 75
    assert P.rmd_start_age(1959) == 73 and P.rmd_start_age(1951) == 73
    assert P.rmd_start_age(1950) == 72


def test_uniform_lifetime_table_matches_irs_publication_590b():
    table = dict(zip(range(P.ULT_FIRST_AGE, P.ULT_LAST_AGE + 1), P.ULT_PERIODS.tolist(), strict=True))
    # spot values from IRS Publication 590-B, Table III (Uniform Lifetime), in effect since 2022
    assert table[72] == 27.4 and table[73] == 26.5 and table[75] == 24.6 and table[80] == 20.2
    assert table[85] == 16.0 and table[90] == 12.2 and table[95] == 8.9 and table[100] == 6.4
    assert table[110] == 3.5 and table[120] == 2.0
    assert P.ULT_LAST_AGE == 120 and len(P.ULT_PERIODS) == 49
    # the distribution period only ever falls as the owner ages, so the withdrawal share only rises
    assert all(a > b for a, b in zip(P.ULT_PERIODS, P.ULT_PERIODS[1:], strict=False))


# --- Kernel parity -------------------------------------------------------------------------


def test_compiled_kernel_matches_plain_python():
    py = getattr(tax_core, "py_func", tax_core)
    args = (201_000.0, 800.0, 2_700.0, 3_000.0, -1_500.0, 12_000.0, 30_000.0, 50_000.0, 5_000.0, 1.0, 1.0, 2_000.0)
    for aged in (0.0, 1.0, 2.0):
        fast, slow = tax_core(*args, aged), py(*args, aged)
        for a, b in zip(fast, slow, strict=True):
            assert a == pytest.approx(b, rel=1e-12, abs=1e-9)


def test_all_outputs_are_finite_on_extreme_inputs():
    r = tax_core(5e7, 1e6, 1e6, 1e6, 1e7, 1e6, 1e6, 1e5, 1e6, 3.0, 3.0, 0.0, 2.0)
    assert all(math.isfinite(x) for x in r)


# --- Charitable gifts ----------------------------------------------------------------------


def test_no_gifts_leave_the_deduction_alone():
    r = ret(wages=150_000.0)
    assert r.deduction_used == P.STANDARD_DEDUCTION_MFJ and r.charitable_deduction == 0.0 and not r.itemized
    assert ret(wages=150_000.0, cash_gifts=0.0, stock_gifts=0.0) == r


def test_a_household_that_does_not_itemize_deducts_up_to_2000_of_cash_gifts_on_top_of_the_standard_deduction():
    base = ret(wages=150_000.0)
    r = ret(wages=150_000.0, cash_gifts=1_500.0)
    assert r.deduction_used == pytest.approx(P.STANDARD_DEDUCTION_MFJ + 1_500.0) and not r.itemized
    assert r.taxable_income == pytest.approx(base.taxable_income - 1_500.0)
    big = ret(wages=150_000.0, cash_gifts=10_000.0)  # still under the standard deduction: only the allowance
    assert big.deduction_used == pytest.approx(P.STANDARD_DEDUCTION_MFJ + P.CHARITY_NON_ITEMIZER_MFJ) and not big.itemized
    assert big.charitable_deduction == pytest.approx(2_000.0)


def test_gifts_of_stock_get_no_allowance_when_the_household_does_not_itemize():
    r = ret(wages=150_000.0, stock_gifts=10_000.0)
    assert r.deduction_used == P.STANDARD_DEDUCTION_MFJ and r.charitable_deduction == 0.0 and not r.itemized
    assert r.grand_total == ret(wages=150_000.0).grand_total


def test_a_household_itemizes_when_its_gifts_beat_the_standard_deduction_after_the_half_percent_floor():
    wages = 200_000.0
    floor = P.CHARITY_ITEMIZER_FLOOR * wages
    r = ret(wages=wages, cash_gifts=50_000.0)
    assert r.itemized and r.deduction_used == pytest.approx(50_000.0 - floor) and r.charitable_deduction == r.deduction_used
    assert r.taxable_income == pytest.approx(wages - (50_000.0 - floor))
    # a dollar short of what itemizing needs, the allowance route is taken instead
    short = ret(wages=wages, cash_gifts=P.STANDARD_DEDUCTION_MFJ + P.CHARITY_NON_ITEMIZER_MFJ + floor - 1.0)
    assert not short.itemized and short.deduction_used == pytest.approx(P.STANDARD_DEDUCTION_MFJ + P.CHARITY_NON_ITEMIZER_MFJ)
    over = ret(wages=wages, cash_gifts=P.STANDARD_DEDUCTION_MFJ + P.CHARITY_NON_ITEMIZER_MFJ + floor + 1.0)
    assert over.itemized and over.deduction_used == pytest.approx(P.STANDARD_DEDUCTION_MFJ + P.CHARITY_NON_ITEMIZER_MFJ + 1.0)


def test_gifts_are_limited_by_agi_sixty_percent_for_cash_thirty_for_stock_sixty_together():
    wages = 200_000.0
    floor = P.CHARITY_ITEMIZER_FLOOR * wages
    assert ret(wages=wages, cash_gifts=500_000.0).deduction_used == pytest.approx(0.60 * wages - floor)
    assert ret(wages=wages, stock_gifts=500_000.0).deduction_used == pytest.approx(0.30 * wages - floor)
    # cash takes 100,000 of the 120,000 the two share, and stock the 20,000 left
    assert ret(wages=wages, cash_gifts=100_000.0, stock_gifts=100_000.0).deduction_used == pytest.approx(120_000.0 - floor)


def test_for_a_household_that_itemizes_cash_and_stock_gifts_are_worth_the_same():
    cash = ret(wages=300_000.0, cash_gifts=60_000.0)
    stock = ret(wages=300_000.0, stock_gifts=60_000.0)
    assert cash.itemized and stock.itemized and cash.grand_total == pytest.approx(stock.grand_total)


def test_illinois_tax_ignores_charitable_gifts():
    assert ret(wages=200_000.0, cash_gifts=50_000.0).illinois_tax == ret(wages=200_000.0).illinois_tax


def test_the_return_shows_the_deduction_that_was_used():
    labels = [line.label for line in ret(wages=200_000.0, cash_gifts=50_000.0).lines()]
    assert "Itemized deductions (charitable gifts)" in labels and "Standard deduction" not in labels
    labels = [line.label for line in ret(wages=150_000.0, cash_gifts=1_000.0).lines()]
    assert "Standard deduction" in labels and "Charitable gifts of cash (without itemizing)" in labels
    assert "Standard deduction" in [line.label for line in ret(wages=150_000.0).lines()]


def test_compiled_kernel_matches_plain_python_with_gifts():
    py = getattr(tax_core, "py_func", tax_core)
    args = (201_000.0, 800.0, 2_700.0, 3_000.0, -1_500.0, 12_000.0, 30_000.0, 50_000.0, 5_000.0, 1.0, 1.0, 2_000.0, 1.0, 500.0)
    for gifts in ((0.0, 0.0), (1_500.0, 0.0), (0.0, 20_000.0), (60_000.0, 40_000.0), (400_000.0, 400_000.0)):
        fast, slow = tax_core(*args, *gifts), py(*args, *gifts)
        for a, b in zip(fast, slow, strict=True):
            assert a == pytest.approx(b, rel=1e-12, abs=1e-9)
