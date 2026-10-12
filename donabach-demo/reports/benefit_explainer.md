# What each strategy does, and what it did for the showcase household

Household: The Tanaka family. Plan: 6-year spending reserve, the rest in stocks, fill 24% bracket (every year), 15% private credit, direct indexing. Every number is the engine's, on 1,000 futures the strategy search never saw; the bars are annual growth-rate advantages of median after-tax wealth at 80 over the good RIA.

**Two attributions.** The *waterfall bar* switches the plan's strategies on one at a time in a fixed order, so a strategy that depends on another is credited with more or less depending on where it stands. The *Shapley share* averages a strategy's added advantage over every order, so it does not depend on the order. Both add up to the plan's whole advantage (+2.11% a year).

| Strategy | Waterfall bar (a year) | Shapley share (a year) | In dollars of median wealth (Shapley) |
|---|---|---|---|
| Lower, flat fee | +0.760% | +0.835% | +434,966 |
| Asset location | +0.256% | +0.135% | +75,139 |
| Highest-cost lots first | +0.095% | +0.079% | +38,523 |
| Loss harvesting stock by stock | -0.026% | +0.060% | +31,257 |
| 6-year spending reserve, the rest in stocks | +0.542% | +0.686% | +362,069 |
| 15% private credit | +0.206% | +0.130% | +80,893 |
| Roth conversions up to the 24% bracket | +0.246% | +0.226% | +121,363 |
| Tax-aware withdrawal order | +0.031% | -0.040% | -14,514 |

A strategy with a negative bar and a positive share (or the reverse) is one whose worth depends on what it is combined with.

## Lower, flat fee

**Mechanism, as implemented.** Each year, after taxes are paid, the fee is charged on the whole portfolio (every account pro rata); the slice of taxable stock sold to pay it realizes its gain, reported on the next year's return. Donabach charges one flat rate. The good RIA's rate falls with the balance; the typical advisor's is higher below $500,000.

**Formula.** fee = rate x total assets (Donabach); fee = sum over tiers of (marginal rate x the part of the balance in the tier) (the advisors).

**Key assumptions.** Donabach 0.35% flat; good RIA 1.0% to $1M, 0.8% to $3M, 0.6% to $5M, 0.5% above; typical advisor 1.15% to $500k, 1.00% to $1,000k, 0.90% to $2,000k, 0.75% to $5,000k, 0.60% above.

**The Tanaka family's numbers.** Waterfall bar +0.760% a year (+330,459 of median wealth at 80); Shapley share +0.835% a year (+434,966).

## Asset location

**Mechanism, as implemented.** At every rebalance the private credit sleeve fills the pre-tax account first (then the Roth, then taxable), bonds fill what is left of the pre-tax account, the Roth holds stocks, and the taxable account takes the stocks that remain. The advisors hold the same mix in every account.

**Formula.** The tax drag of an asset is its taxable yield times the marginal rate (bonds 3.5% of ordinary income, private credit the same, stocks 1.8% of qualified dividends plus realized gains); location puts the highest-yield holdings where that drag is not charged.

**Key assumptions.** Bond interest yield 3.5%; dividend yield 1.8%; tax brackets, deductions and the 0/15/20% gain rates of 2026 held constant in real dollars.

**The Tanaka family's numbers.** Waterfall bar +0.256% a year (+128,677 of median wealth at 80); Shapley share +0.135% a year (+75,139).

## Highest-cost lots first (and gain harvesting, and gifts of lots)

**Mechanism, as implemented.** Stock in the taxable account is a set of lots. A sale takes the lot bought at the highest price first (the advisors: the oldest first). A lot held a year or less has a short-term gain (a lot sold in the year it was bought is wholly short-term, one sold the next year half), taxed as ordinary income. Each year the plan also realizes gains up to the top of the 0% capital-gain bracket by selling the lowest-cost lots and buying them back at once, and a household that gives to charity gives the lots with the most gain instead of cash.

**Formula.** gain of a sale = sum over lots sold of units x (price - cost); gain harvested = min(room under the 0% bracket top, unrealized gain), at 0% tax; a gift of lots deducts the market value and realizes nothing.

**Key assumptions.** Short-term share of a lot's gain by its age: 1, 0.5, 0. The 0% bracket tops out at $98,900 of taxable income (married filing jointly, 2026). A gift of long-term stock is deducted at market value; a household that does not itemize may deduct $2,000 of cash gifts on top of the standard deduction.

**The Tanaka family's numbers.** Waterfall bar +0.095% a year (+50,358 of median wealth at 80); Shapley share +0.079% a year (+38,523).

## Loss harvesting stock by stock (direct indexing)

**Mechanism, as implemented.** The taxable stock is 100 stocks, each moving with the market and with its own random movement (volatility 25% a year); a lot whose cost is more than 1% above its stock's price is sold at a loss and bought back at once (a lot with a new cost). The loss offsets gains, then $3,000 of income a year, and the rest carries forward.

**Formula.** loss harvested in a year = sum over lots with cost > (1 + threshold) x price of units x (cost - price); tax saved = marginal gain rate x loss, with the carryforward valued by the same engine at the horizon.

**Key assumptions.** Idiosyncratic volatility 25% (an assumption read from published figures for single US stocks); harvest threshold 1%; no wash-sale rule is modelled (a section 12.9 check); no trading costs.

**The Tanaka family's numbers.** Waterfall bar -0.026% a year (-14,031 of median wealth at 80); Shapley share +0.060% a year (+31,257).

## Spending reserve, the rest in stocks

**Mechanism, as implemented.** Bonds and private credit hold the next N years of retirement spending net of Social Security (the goals of those years are in the goal bucket) and everything else is in stocks. In a year stocks fell, spending and goals are paid from the bonds and private credit of every account first, and nothing is sold to refill the reserve; in other years the rebalance refills it.

**Formula.** safe share = max(sum over the next N years of need / portfolio, private credit share); stock share = 1 - safe share.

**Key assumptions.** Equity return 5.5% after inflation, volatility 16%; bonds 1.5% and 5%; correlations 0.1 (stocks-bonds), 0.5 (stocks-private credit). The liability-matched style chooses N under a limit of 2% of futures with a forced sale in a falling year.

**The Tanaka family's numbers.** Waterfall bar +0.542% a year (+312,063 of median wealth at 80); Shapley share +0.686% a year (+362,069).

## Private credit sleeve

**Mechanism, as implemented.** A share of the portfolio in private credit (return 3.5% a year after inflation, volatility 8%, correlation 0.5 with stocks), counted toward the reserve and held in the pre-tax account first, so its income is untaxed until withdrawal.

**Formula.** return = mean + sd x z with z correlated with the stock return; the taxable yield is the mean plus inflation.

**Key assumptions.** Return 3.5% after inflation, volatility 8% (the assumption review's figures; sensitivity 2% to 5%).

**The Tanaka family's numbers.** Waterfall bar +0.206% a year (+131,975 of median wealth at 80); Shapley share +0.130% a year (+80,893).

## Roth conversions

**Mechanism, as implemented.** Each year (or in low-income years and retirement) pre-tax money is converted in kind to Roth up to the top of the chosen bracket, paying the tax from the taxable account, cash and spare wages (never from the converted dollars).

**Formula.** converted = min(top of bracket + deduction - other ordinary income, pre-tax balance, funds / marginal rate); the tax on it is the engine's, with Illinois subtracting it from its base.

**Key assumptions.** Brackets are held constant in real dollars; the survivor, after the first death, files single (narrower brackets).

**The Tanaka family's numbers.** Waterfall bar +0.246% a year (+167,947 of median wealth at 80); Shapley share +0.226% a year (+121,363).

## Tax-aware withdrawal order

**Mechanism, as implemented.** Spending is paid from pre-tax money up to the bracket target first, then the taxable account, then the Roth (before 59 1/2: taxable, Roth, then pre-tax with the 10% penalty).

**Formula.** pre-tax drawn = min(need, bracket top + deduction - ordinary income so far).

**Key assumptions.** Retirement spending net of Social Security is taken to be what the household states; Social Security is taxed by the provisional-income formula.

**The Tanaka family's numbers.** Waterfall bar +0.031% a year (+22,247 of median wealth at 80); Shapley share -0.040% a year (-14,514).

## Gain harvesting in the 0% bracket (part of the lots step above)

Switched off on its own, the plan's advantage over the good RIA goes from +2.111% to +2.102% a year.

