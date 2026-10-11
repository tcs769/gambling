"""Federal + Illinois income tax for a married-filing-jointly household, tax year 2026.

`tax_core` is a scalar kernel (JIT-compiled when numba is available) and the single source of
truth: the simulator calls it directly in its inner loop, and `compute_return` wraps it with a
line-by-line breakdown for the UI and the generated documents.

Conventions
-----------
* `wages` are W-2 box 1 wages, i.e. after pre-tax 401(k) deferrals.
* `ordinary_dividends` is the 1040 line 3b total and *includes* the qualified dividends (3a).
* Capital gains are treated as long-term. `net_capital_gain` may be negative.
* `capital_loss_carryforward` is a positive number of dollars of loss brought in.
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
    ],
)


@jit
def ordinary_tax(taxable: float) -> float:
    """Tax on ordinary taxable income from the MFJ bracket table."""
    tax = 0.0
    lower = 0.0
    for i in range(P.BRACKET_TOPS.shape[0]):
        top = P.BRACKET_TOPS[i]
        if taxable > lower:
            tax += (min(taxable, top) - lower) * P.BRACKET_RATES[i]
        lower = top
    return tax


@jit
def marginal_rate(ordinary_taxable: float) -> float:
    """Statutory rate on the next dollar of ordinary income (a filled bracket moves up)."""
    n = P.BRACKET_TOPS.shape[0]
    for i in range(n):
        if ordinary_taxable < P.BRACKET_TOPS[i]:
            return P.BRACKET_RATES[i]
    return P.BRACKET_RATES[n - 1]


@jit
def pretax_withdrawal_rate(balance: float, social_security: float) -> float:
    """Federal rate on a pre-tax balance withdrawn evenly over 20 years alongside Social Security.

    This is the incremental rate: (tax with the withdrawal - tax on Social Security alone) /
    withdrawal. It is how the after-tax wealth formula values a pre-tax balance.
    """
    if balance <= 0.0:
        return 0.0
    withdrawal = balance / P.PRETAX_WITHDRAWAL_YEARS
    taxable_ss = P.SS_TAXABLE_SHARE * social_security
    base = ordinary_tax(max(0.0, taxable_ss - P.STANDARD_DEDUCTION_MFJ))
    full = ordinary_tax(max(0.0, withdrawal + taxable_ss - P.STANDARD_DEDUCTION_MFJ))
    return (full - base) / withdrawal


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
):
    qualified = min(qualified_dividends, ordinary_dividends)
    taxable_ss = P.SS_TAXABLE_SHARE * social_security

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

    total_income = (
        wages
        + interest
        + ordinary_dividends
        + cap_gain_line
        + retirement_distributions
        + roth_conversions
        + taxable_ss
    )
    agi = total_income  # no above-the-line adjustments are modelled
    taxable_income = max(0.0, agi - P.STANDARD_DEDUCTION_MFJ)

    # Qualified dividends and long-term gains are taxed at preferential rates and stack on top
    # of ordinary taxable income.
    preferential = min(taxable_income, qualified + max(0.0, cap_gain_line))
    ordinary_taxable = taxable_income - preferential
    ord_tax = ordinary_tax(ordinary_taxable)

    bottom = ordinary_taxable
    top = ordinary_taxable + preferential
    at_fifteen = max(0.0, min(top, P.CG_FIFTEEN_TOP) - max(bottom, P.CG_ZERO_TOP))
    at_twenty = max(0.0, top - max(bottom, P.CG_FIFTEEN_TOP))
    cg_tax = P.CG_RATE_FIFTEEN * at_fifteen + P.CG_RATE_TWENTY * at_twenty

    # Net investment income tax on the lesser of NII or MAGI over the threshold.
    nii = max(0.0, interest + ordinary_dividends + cap_gain_line)
    niit = P.NIIT_RATE * min(nii, max(0.0, agi - P.NIIT_THRESHOLD_MFJ))

    # Child tax credit: $50 off per $1,000 (or fraction) of MAGI over the threshold; nonrefundable.
    ctc_available = P.CTC_PER_CHILD * children_under_17
    excess = max(0.0, agi - P.CTC_PHASEOUT_START_MFJ)
    steps = math.ceil(excess / P.CTC_PHASEOUT_STEP - 1e-9)
    ctc_available = max(0.0, ctc_available - P.CTC_PHASEOUT_REDUCTION * steps)
    ctc_used = min(ctc_available, ord_tax + cg_tax)

    penalty = P.EARLY_WITHDRAWAL_PENALTY_RATE * early_withdrawal_base
    federal_total = ord_tax + cg_tax - ctc_used + niit + penalty

    # Illinois: flat rate on AGI less federally taxed retirement income, less exemptions.
    il_base = max(0.0, agi - retirement_distributions - roth_conversions - taxable_ss)
    if agi > P.IL_EXEMPTION_AGI_LIMIT_MFJ:
        il_exemptions = 0.0
    else:
        il_exemptions = P.IL_EXEMPTION_PER_PERSON * (2.0 + dependents)
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
        marginal_rate(ordinary_taxable),
    )


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
    net_capital_gain: float = Field(0.0, description="Net long-term capital gain; may be negative")
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


class TaxLine(BaseModel):
    label: str
    amount: float
    kind: str = "amount"  # "amount" | "rate" | "subtotal" | "total"
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
    retirement_distributions: float
    roth_conversions: float
    social_security: float
    taxable_social_security: float
    total_income: float
    agi: float
    # Federal
    standard_deduction: float
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

    def lines(self) -> list[TaxLine]:
        """The return as ordered display lines (used by the year-detail side panel)."""
        out = [
            TaxLine(label="Wages (after 401(k) deferrals)", amount=self.wages),
            TaxLine(label="Taxable interest", amount=self.interest),
            TaxLine(label="Ordinary dividends", amount=self.ordinary_dividends),
            TaxLine(label="Capital gain (loss), after $3,000 limit", amount=self.capital_gain_line),
            TaxLine(label="Retirement account withdrawals", amount=self.retirement_distributions),
            TaxLine(label="Roth conversions", amount=self.roth_conversions),
            TaxLine(label="Taxable Social Security (85%)", amount=self.taxable_social_security),
            TaxLine(label="Adjusted gross income", amount=self.agi, kind="subtotal"),
            TaxLine(label="Standard deduction", amount=-self.standard_deduction),
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
    )
    agi = r.agi
    return TaxReturn(
        wages=inputs.wages,
        interest=inputs.interest,
        qualified_dividends=min(inputs.qualified_dividends, inputs.ordinary_dividends),
        ordinary_dividends=inputs.ordinary_dividends,
        capital_gain_input=inputs.net_capital_gain,
        capital_gain_line=r.cap_gain_line,
        retirement_distributions=inputs.retirement_distributions,
        roth_conversions=inputs.roth_conversions,
        social_security=inputs.social_security,
        taxable_social_security=r.taxable_social_security,
        total_income=r.total_income,
        agi=agi,
        standard_deduction=P.STANDARD_DEDUCTION_MFJ,
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
