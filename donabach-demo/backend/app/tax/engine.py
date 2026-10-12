"""Federal + Illinois income tax for a married-filing-jointly household, tax year 2026.

`tax_core` is a scalar kernel (JIT-compiled when numba is available) and the single source of
truth: the simulator calls it directly in its inner loop, and `compute_return` wraps it with a
line-by-line breakdown for the UI and the generated documents.

Conventions
-----------
* `wages` are W-2 box 1 wages, i.e. after pre-tax 401(k) deferrals.
* `ordinary_dividends` is the 1040 line 3b total and *includes* the qualified dividends (3a).
* Capital gains are long-term unless `short_term_gain` says part of `net_capital_gain` is short-term (held a year or
  less): that part is ordinary income. `net_capital_gain` is the net of both and may be negative; short-term and
  long-term losses offset each other before anything is taxed (IRC section 1222).
* `capital_loss_carryforward` is a positive number of dollars of loss brought in.
* `aged_spouses` is how many of the two spouses are 65 or older (0, 1 or 2); each adds the
  additional standard deduction of $1,650 (IRS Rev. Proc. 2025-32).
* `cash_gift` and `stock_gift` are charitable gifts of the year (cash, and long-term stock at its market value). The
  household takes the larger of the standard deduction plus the cash allowance for those who do not itemize, and gifts
  alone as itemized deductions (see `params_2026`).
* Amounts are real 2026 dollars; brackets are never indexed.
"""

from __future__ import annotations

import math
from collections import namedtuple

from pydantic import BaseModel, Field

from app.jit import jit
from app.tax import params_2026 as P

# --------------------------------------------------------------------------------------------
# Scalar kernels
# --------------------------------------------------------------------------------------------

CoreReturn = namedtuple(
    "CoreReturn",
    [
        "taxable_social_security",
        "cap_gain_line",
        "cap_loss_deducted",
        "cap_loss_carryforward_out",
        "total_income",
        "agi",
        "taxable_income",
        "preferential_income",
        "ordinary_taxable_income",
        "ordinary_tax",
        "capital_gains_tax",
        "niit",
        "ctc_available",
        "ctc_used",
        "early_withdrawal_penalty",
        "federal_total",
        "il_base_income",
        "il_exemptions",
        "il_taxable_income",
        "illinois_tax",
        "total_tax",
        "marginal_federal_rate",
        "short_term_ordinary",
        "deduction",
        "charitable_deduction",
        "itemized",
    ],
)


@jit
def ordinary_tax(taxable: float, single: float = 0.0) -> float:
    """Tax on ordinary taxable income from the married-filing-jointly bracket table (the single table when `single`)."""
    tops = P.BRACKET_TOPS_SINGLE if single > 0.5 else P.BRACKET_TOPS
    rates = P.BRACKET_RATES_SINGLE if single > 0.5 else P.BRACKET_RATES
    tax = 0.0
    lower = 0.0
    for i in range(tops.shape[0]):
        top = tops[i]
        if taxable > lower:
            tax += (min(taxable, top) - lower) * rates[i]
        lower = top
    return tax


@jit
def marginal_rate(ordinary_taxable: float, single: float = 0.0) -> float:
    """Statutory rate on the next dollar of ordinary income (a filled bracket moves up)."""
    tops = P.BRACKET_TOPS_SINGLE if single > 0.5 else P.BRACKET_TOPS
    rates = P.BRACKET_RATES_SINGLE if single > 0.5 else P.BRACKET_RATES
    n = tops.shape[0]
    for i in range(n):
        if ordinary_taxable < tops[i]:
            return rates[i]
    return rates[n - 1]


@jit
def bracket_top(mfj_top: float, single: float = 0.0) -> float:
    """The top of the same bracket for a single filer, given the top of a married-filing-jointly bracket (the targets of the
    Roth conversion and withdrawal strategies are named by the joint table)."""
    if single < 0.5 or mfj_top <= 0.0:
        return mfj_top
    for i in range(P.BRACKET_TOPS.shape[0]):
        if abs(P.BRACKET_TOPS[i] - mfj_top) < 1.0:
            return P.BRACKET_TOPS_SINGLE[i]
    return mfj_top


@jit
def standard_deduction(aged_spouses: float = 0.0, single: float = 0.0) -> float:
    """Standard deduction, married filing jointly, including the extra for each spouse 65 or older (single: the single filer's)."""
    if single > 0.5:
        return P.STANDARD_DEDUCTION_SINGLE + P.STANDARD_DEDUCTION_AGED_SINGLE * min(1.0, aged_spouses)
    return P.STANDARD_DEDUCTION_MFJ + P.STANDARD_DEDUCTION_AGED_PER_SPOUSE * aged_spouses


@jit
def pretax_withdrawal_rate(balance: float, social_security: float, aged_spouses: float = 0.0) -> float:
    """Federal rate on a pre-tax balance withdrawn evenly over 20 years alongside Social Security.

    This is the incremental rate: (tax with the withdrawal - tax on Social Security alone) /
    withdrawal. It is how the after-tax wealth formula values a pre-tax balance.
    """
    if balance <= 0.0:
        return 0.0
    withdrawal = balance / P.PRETAX_WITHDRAWAL_YEARS
    deduction = standard_deduction(aged_spouses)
    base = ordinary_tax(max(0.0, taxable_social_security(social_security, 0.0) - deduction))
    full = ordinary_tax(max(0.0, withdrawal + taxable_social_security(social_security, withdrawal) - deduction))
    return (full - base) / withdrawal


@jit
def taxable_social_security(social_security: float, other_income: float, single: float = 0.0) -> float:
    """Taxable part of the benefits by the provisional-income formula (IRC section 86), married filing jointly. `other_income` is
    adjusted gross income without the benefits (wages, interest, dividends, the capital gain line, retirement withdrawals, conversions)."""
    if social_security <= 0.0:
        return 0.0
    base = P.SS_BASE_SINGLE if single > 0.5 else P.SS_BASE_MFJ
    additional = P.SS_ADDITIONAL_SINGLE if single > 0.5 else P.SS_ADDITIONAL_MFJ
    provisional = other_income + 0.5 * social_security
    if provisional <= base:
        return 0.0
    half = 0.5 * social_security
    if provisional <= additional:
        return min(0.5 * (provisional - base), half)
    first_tier = min(half, 0.5 * (additional - base))
    return min(P.SS_TAXABLE_SHARE * (provisional - additional) + first_tier, P.SS_TAXABLE_SHARE * social_security)


@jit
def tax_core(
    wages: float,
    interest: float,
    qualified_dividends: float,
    ordinary_dividends: float,
    net_capital_gain: float,
    retirement_distributions: float,
    roth_conversions: float,
    social_security: float,
    early_withdrawal_base: float,
    children_under_17: float,
    dependents: float,
    capital_loss_carryforward: float,
    aged_spouses: float = 0.0,
    short_term_gain: float = 0.0,
    cash_gift: float = 0.0,
    stock_gift: float = 0.0,
    single: float = 0.0,
):
    sg = single > 0.5
    qualified = min(qualified_dividends, ordinary_dividends)

    # Capital gains and losses: net against the carryforward; a net loss deducts up to $3,000.
    net = net_capital_gain - capital_loss_carryforward
    if net >= 0.0:
        cap_gain_line = net
        cap_loss_deducted = 0.0
        carry_out = 0.0
    else:
        cap_loss_deducted = min(P.CAP_LOSS_LIMIT, -net)
        cap_gain_line = -cap_loss_deducted
        carry_out = -net - cap_loss_deducted

    other_income = wages + interest + ordinary_dividends + cap_gain_line + retirement_distributions + roth_conversions
    taxable_ss = taxable_social_security(social_security, other_income, single)
    total_income = other_income + taxable_ss
    agi = total_income  # no above-the-line adjustments are modelled

    # The deduction: the standard one, plus the cash-gift allowance for a household that does not itemize, or its charitable
    # gifts alone when they come to more (no other itemized deductions are modelled).
    std = standard_deduction(aged_spouses, single)
    deduction = std
    charitable = 0.0
    itemized = 0.0
    if cash_gift > 0.0 or stock_gift > 0.0:
        base = max(0.0, agi)
        cash_allowed = min(cash_gift, P.CHARITY_CASH_LIMIT * base)
        stock_allowed = min(stock_gift, P.CHARITY_STOCK_LIMIT * base, max(0.0, P.CHARITY_CASH_LIMIT * base - cash_allowed))
        gifts = max(0.0, cash_allowed + stock_allowed - P.CHARITY_ITEMIZER_FLOOR * base)
        allowance = min(cash_gift, P.CHARITY_NON_ITEMIZER_SINGLE if sg else P.CHARITY_NON_ITEMIZER_MFJ)
        if gifts > std + allowance:
            deduction = gifts
            charitable = gifts
            itemized = 1.0
        else:
            deduction = std + allowance
            charitable = allowance
    taxable_income = max(0.0, agi - deduction)

    # The short-term part of a net gain is ordinary income. A net short-term loss and a long-term loss absorb
    # each other first, so what stays short-term is at most the net gain (`short_term_gain` is a part of
    # `net_capital_gain`, negative for a net short-term loss).
    short_term_ordinary = 0.0
    if net > 0.0 and short_term_gain > 0.0:
        short_term_ordinary = min(short_term_gain, net)

    # Qualified dividends and long-term gains are taxed at preferential rates and stack on top
    # of ordinary taxable income.
    preferential = min(taxable_income, qualified + max(0.0, cap_gain_line) - short_term_ordinary)
    ordinary_taxable = taxable_income - preferential
    ord_tax = ordinary_tax(ordinary_taxable, single)

    bottom = ordinary_taxable
    top = ordinary_taxable + preferential
    zero_top = P.CG_ZERO_TOP_SINGLE if sg else P.CG_ZERO_TOP
    fifteen_top = P.CG_FIFTEEN_TOP_SINGLE if sg else P.CG_FIFTEEN_TOP
    at_fifteen = max(0.0, min(top, fifteen_top) - max(bottom, zero_top))
    at_twenty = max(0.0, top - max(bottom, fifteen_top))
    cg_tax = P.CG_RATE_FIFTEEN * at_fifteen + P.CG_RATE_TWENTY * at_twenty

    # Net investment income tax on the lesser of NII or MAGI over the threshold.
    nii = max(0.0, interest + ordinary_dividends + cap_gain_line)
    niit = P.NIIT_RATE * min(nii, max(0.0, agi - (P.NIIT_THRESHOLD_SINGLE if sg else P.NIIT_THRESHOLD_MFJ)))

    # Child tax credit: $50 off per $1,000 (or fraction) of MAGI over the threshold; nonrefundable.
    ctc_available = P.CTC_PER_CHILD * children_under_17
    excess = max(0.0, agi - (P.CTC_PHASEOUT_START_SINGLE if sg else P.CTC_PHASEOUT_START_MFJ))
    steps = math.ceil(excess / P.CTC_PHASEOUT_STEP - 1e-9)
    ctc_available = max(0.0, ctc_available - P.CTC_PHASEOUT_REDUCTION * steps)
    ctc_used = min(ctc_available, ord_tax + cg_tax)

    penalty = P.EARLY_WITHDRAWAL_PENALTY_RATE * early_withdrawal_base
    federal_total = ord_tax + cg_tax - ctc_used + niit + penalty

    # Illinois: flat rate on AGI less federally taxed retirement income, less exemptions.
    il_base = max(0.0, agi - retirement_distributions - roth_conversions - taxable_ss)
    if agi > (P.IL_EXEMPTION_AGI_LIMIT_SINGLE if sg else P.IL_EXEMPTION_AGI_LIMIT_MFJ):
        il_exemptions = 0.0
    else:
        il_exemptions = P.IL_EXEMPTION_PER_PERSON * ((1.0 if sg else 2.0) + dependents) + P.IL_EXEMPTION_AGED_PER_PERSON * (min(1.0, aged_spouses) if sg else aged_spouses)
    il_taxable = max(0.0, il_base - il_exemptions)
    il_tax = P.IL_RATE * il_taxable

    return CoreReturn(
        taxable_ss,
        cap_gain_line,
        cap_loss_deducted,
        carry_out,
        total_income,
        agi,
        taxable_income,
        preferential,
        ordinary_taxable,
        ord_tax,
        cg_tax,
        niit,
        ctc_available,
        ctc_used,
        penalty,
        federal_total,
        il_base,
        il_exemptions,
        il_taxable,
        il_tax,
        federal_total + il_tax,
        marginal_rate(ordinary_taxable, single),
        short_term_ordinary,
        deduction,
        charitable,
        itemized,
    )


@jit
def liquidation_taxes(
    unrealized: float,
    deferred_gain: float,
    deferred_gain_short: float,
    deferred_withdrawals: float,
    pretax: float,
    carryforward: float,
    social_security: float,
    interest: float,
    dividends: float,
    aged_spouses: float,
    kids: float,
    deps: float,
    single: float = 0.0,
):
    """What the tax engine charges to liquidate a household's holdings: (tax on the pre-tax balance, tax on the gains).

    The valuation every strategy gets at the horizon (and today), so none is favored by the way it is valued. The pre-tax
    balance is withdrawn evenly over `PRETAX_WITHDRAWAL_YEARS` years and the unrealized gain realized evenly over
    `GAIN_REALIZATION_YEARS` years, in the same years as that withdrawal, alongside the household's other income: taxable
    Social Security, and the interest and dividends it earns. The gains stack on top of the withdrawals, the capital-loss
    carryforward offsets them year after year (what it does not use in the window is worth only the $3,000 a year of ordinary
    income it deducts), and every year's tax is `tax_core`'s own: brackets, the 0/15/20% gain rates, the 3.8% net investment
    income tax and Illinois. Gains already realized but not yet reported (selling to pay the last year's tax and fee) land in
    the first year, and so do pre-tax withdrawals already made to pay tax (`deferred_withdrawals`)."""
    zero = 0.0
    withdrawal = pretax / P.PRETAX_WITHDRAWAL_YEARS
    other = tax_core(zero, interest, dividends, dividends, zero, zero, zero, social_security, zero, kids, deps, zero, aged_spouses, zero, zero, zero, single).total_tax
    with_withdrawal = tax_core(zero, interest, dividends, dividends, zero, withdrawal, zero, social_security, zero, kids, deps, zero, aged_spouses, zero, zero, zero, single).total_tax
    tax_pretax = P.PRETAX_WITHDRAWAL_YEARS * (with_withdrawal - other)
    if deferred_withdrawals > 0.0:
        extra = tax_core(zero, interest, dividends, dividends, zero, withdrawal + deferred_withdrawals, zero, social_security, zero, kids, deps, zero, aged_spouses, zero, zero, zero, single).total_tax
        tax_pretax += extra - with_withdrawal
    tax_gains = 0.0
    carry = carryforward
    each = unrealized / P.GAIN_REALIZATION_YEARS
    for year in range(P.GAIN_REALIZATION_YEARS):
        gain = each
        short = 0.0
        if year == 0:
            gain += deferred_gain
            short = deferred_gain_short
        if gain == 0.0 and carry <= 0.0:
            continue
        with_gain = tax_core(zero, interest, dividends, dividends, gain, withdrawal, zero, social_security, zero, kids, deps, carry, aged_spouses, short, zero, zero, single)
        tax_gains += with_gain.total_tax - with_withdrawal
        carry = with_gain.cap_loss_carryforward_out
    return tax_pretax, tax_gains


# --------------------------------------------------------------------------------------------
# Typed wrapper
# --------------------------------------------------------------------------------------------


class TaxInputs(BaseModel):
    wages: float = Field(0.0, ge=0, description="W-2 box 1 wages, after pre-tax 401(k) deferrals")
    interest: float = Field(0.0, ge=0, description="Taxable interest (1040 line 2b)")
    qualified_dividends: float = Field(0.0, ge=0, description="Qualified dividends (line 3a)")
    ordinary_dividends: float = Field(
        0.0, ge=0, description="Ordinary dividends (line 3b), including the qualified portion"
    )
    net_capital_gain: float = Field(0.0, description="Net capital gain, short-term and long-term together; may be negative")
    short_term_gain: float = Field(
        0.0, description="The short-term part of net_capital_gain (taxed as ordinary income); negative for a net short-term loss"
    )
    retirement_distributions: float = Field(0.0, ge=0, description="Pre-tax IRA/401(k) withdrawals")
    roth_conversions: float = Field(0.0, ge=0, description="Pre-tax dollars converted to Roth")
    social_security: float = Field(0.0, ge=0, description="Gross Social Security benefits")
    early_withdrawal_base: float = Field(
        0.0, ge=0, description="Pre-tax withdrawals subject to the 10% early-withdrawal penalty"
    )
    children_under_17: int = Field(0, ge=0)
    dependents: int | None = Field(
        None, ge=0, description="Dependents for the Illinois exemption; defaults to the children"
    )
    capital_loss_carryforward: float = Field(0.0, ge=0, description="Loss carried in from prior years")
    aged_spouses: int = Field(
        0, ge=0, le=2, description="Spouses aged 65 or older; each adds the additional standard deduction"
    )
    cash_gifts: float = Field(0.0, ge=0, description="Charitable gifts of cash this year")
    stock_gifts: float = Field(0.0, ge=0, description="Charitable gifts of stock held over a year, at market value")
    single: bool = Field(False, description="File as a single taxpayer (a surviving spouse) instead of married filing jointly")


class TaxLine(BaseModel):
    label: str
    amount: float
    kind: str = "amount"  # "amount" | "rate" | "subtotal" | "total" | "note" (already counted in the line above)
    note: str | None = None


class TaxReturn(BaseModel):
    """Every line item of the computed return."""

    # Income
    wages: float
    interest: float
    qualified_dividends: float
    ordinary_dividends: float
    capital_gain_input: float
    capital_gain_line: float
    short_term_gain_ordinary: float  # the part of the capital gain line taxed as ordinary income (short-term)
    retirement_distributions: float
    roth_conversions: float
    social_security: float
    taxable_social_security: float
    total_income: float
    agi: float
    # Federal
    standard_deduction: float
    deduction_used: float = 0.0  # what was subtracted from AGI: the standard deduction, or the itemized gifts when they are more
    charitable_deduction: float = 0.0  # the part of it that is for charitable gifts
    itemized: bool = False
    taxable_income: float
    preferential_income: float
    ordinary_taxable_income: float
    ordinary_tax: float
    capital_gains_tax: float
    niit: float
    child_tax_credit_available: float
    child_tax_credit: float
    early_withdrawal_penalty: float
    federal_total: float
    # Illinois
    il_base_income: float
    il_exemptions: float
    il_taxable_income: float
    illinois_tax: float
    # Totals and rates
    grand_total: float
    marginal_federal_rate: float
    effective_federal_rate: float
    effective_total_rate: float
    # Capital losses
    capital_loss_carryforward_in: float
    capital_loss_deducted: float
    capital_loss_carryforward_out: float

    def _deduction_lines(self) -> list[TaxLine]:
        if self.itemized:
            return [TaxLine(label="Itemized deductions (charitable gifts)", amount=-self.deduction_used)]
        lines = [TaxLine(label="Standard deduction", amount=-self.standard_deduction)]
        if self.charitable_deduction > 0:
            lines.append(TaxLine(label="Charitable gifts of cash (without itemizing)", amount=-self.charitable_deduction))
        return lines

    def lines(self) -> list[TaxLine]:
        """The return as ordered display lines (used by the year-detail side panel)."""
        out = [
            TaxLine(label="Wages (after 401(k) deferrals)", amount=self.wages),
            TaxLine(label="Taxable interest", amount=self.interest),
            TaxLine(label="Ordinary dividends", amount=self.ordinary_dividends),
            TaxLine(label="Capital gain (loss), after $3,000 limit", amount=self.capital_gain_line),
            *(
                [TaxLine(label="of which short-term, taxed as ordinary income", amount=self.short_term_gain_ordinary, kind="note")]
                if self.short_term_gain_ordinary > 0
                else []
            ),
            TaxLine(label="Retirement account withdrawals", amount=self.retirement_distributions),
            TaxLine(label="Roth conversions", amount=self.roth_conversions),
            TaxLine(label="Taxable Social Security", amount=self.taxable_social_security),
            TaxLine(label="Adjusted gross income", amount=self.agi, kind="subtotal"),
            *self._deduction_lines(),
            TaxLine(label="Taxable income", amount=self.taxable_income, kind="subtotal"),
            TaxLine(label="Tax on ordinary income", amount=self.ordinary_tax),
            TaxLine(label="Tax on dividends and gains", amount=self.capital_gains_tax),
            TaxLine(label="Net investment income tax", amount=self.niit),
            TaxLine(label="Child tax credit", amount=-self.child_tax_credit),
            TaxLine(label="Early-withdrawal penalty", amount=self.early_withdrawal_penalty),
            TaxLine(label="Federal tax", amount=self.federal_total, kind="subtotal"),
            TaxLine(label="Illinois base income", amount=self.il_base_income),
            TaxLine(label="Illinois exemptions", amount=-self.il_exemptions),
            TaxLine(label="Illinois tax (4.95%)", amount=self.illinois_tax, kind="subtotal"),
            TaxLine(label="Total income tax", amount=self.grand_total, kind="total"),
            TaxLine(
                label="Marginal federal rate", amount=self.marginal_federal_rate, kind="rate"
            ),
        ]
        return out


def compute_return(inputs: TaxInputs) -> TaxReturn:
    dependents = (
        inputs.children_under_17 if inputs.dependents is None else inputs.dependents
    )
    r = tax_core(
        float(inputs.wages),
        float(inputs.interest),
        float(inputs.qualified_dividends),
        float(inputs.ordinary_dividends),
        float(inputs.net_capital_gain),
        float(inputs.retirement_distributions),
        float(inputs.roth_conversions),
        float(inputs.social_security),
        float(inputs.early_withdrawal_base),
        float(inputs.children_under_17),
        float(dependents),
        float(inputs.capital_loss_carryforward),
        float(inputs.aged_spouses),
        float(inputs.short_term_gain),
        float(inputs.cash_gifts),
        float(inputs.stock_gifts),
        1.0 if inputs.single else 0.0,
    )
    agi = r.agi
    return TaxReturn(
        wages=inputs.wages,
        interest=inputs.interest,
        qualified_dividends=min(inputs.qualified_dividends, inputs.ordinary_dividends),
        ordinary_dividends=inputs.ordinary_dividends,
        capital_gain_input=inputs.net_capital_gain,
        capital_gain_line=r.cap_gain_line,
        short_term_gain_ordinary=r.short_term_ordinary,
        retirement_distributions=inputs.retirement_distributions,
        roth_conversions=inputs.roth_conversions,
        social_security=inputs.social_security,
        taxable_social_security=r.taxable_social_security,
        total_income=r.total_income,
        agi=agi,
        standard_deduction=float(standard_deduction(float(inputs.aged_spouses), 1.0 if inputs.single else 0.0)),
        deduction_used=r.deduction,
        charitable_deduction=r.charitable_deduction,
        itemized=bool(r.itemized),
        taxable_income=r.taxable_income,
        preferential_income=r.preferential_income,
        ordinary_taxable_income=r.ordinary_taxable_income,
        ordinary_tax=r.ordinary_tax,
        capital_gains_tax=r.capital_gains_tax,
        niit=r.niit,
        child_tax_credit_available=r.ctc_available,
        child_tax_credit=r.ctc_used,
        early_withdrawal_penalty=r.early_withdrawal_penalty,
        federal_total=r.federal_total,
        il_base_income=r.il_base_income,
        il_exemptions=r.il_exemptions,
        il_taxable_income=r.il_taxable_income,
        illinois_tax=r.illinois_tax,
        grand_total=r.total_tax,
        marginal_federal_rate=r.marginal_federal_rate,
        effective_federal_rate=r.federal_total / agi if agi > 0 else 0.0,
        effective_total_rate=r.total_tax / agi if agi > 0 else 0.0,
        capital_loss_carryforward_in=inputs.capital_loss_carryforward,
        capital_loss_deducted=r.cap_loss_deducted,
        capital_loss_carryforward_out=r.cap_loss_carryforward_out,
    )
