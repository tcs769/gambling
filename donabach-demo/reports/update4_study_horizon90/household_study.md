# Household-type study

60 synthetic households (10 of each of six types), all fictional. For each, the planner searched
its strategy menu on 400 simulated futures and the winner was scored against both advisors on 1,000 fresh
futures it never saw (risk aversion 3; planning style: equity first, a spending reserve with everything else in stocks). Nothing was tuned; the households were drawn from fixed ranges
that make each a clear example of its type (see `backend/app/study/households.py`).

* **Median advantage**: difference in median after-tax wealth at the horizon, annualized as a growth-rate difference.
* **Risk-adjusted advantage**: the same on certainty-equivalent wealth (the planner's objective).
* Each cell is the **median across the households of that type** (with the 10th to 90th percentile across households).
  Dollar-weighted or pooled figures would differ; this is the typical household of the type.

## Against the good ria

A good traditional advisor: an age-based glide path from 80% to 50% stocks, the same mix in every account, breakpoint fees of 1.0% falling to 0.5%, fund-level loss harvesting in years stocks fall more than 10%, goals paid from the brokerage account, no Roth conversions, pro rata withdrawals and the oldest tax lots sold first.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 10 | +2.05% (+1.80% to +2.42%) | +0.50% (-0.03% to +0.65%) | 100% | 80% |
| Concentrated single stock (40%+ of investable assets, low basis) | 10 | +2.29% (+2.13% to +2.91%) | +0.64% (+0.11% to +0.90%) | 100% | 90% |
| Large unrealized gains (brokerage basis under 40% of value) | 10 | +2.01% (+1.65% to +2.54%) | +0.32% (-0.10% to +0.55%) | 100% | 60% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 10 | +1.77% (+1.44% to +1.96%) | +0.37% (+0.29% to +0.60%) | 100% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 10 | +2.08% (+1.62% to +2.87%) | +0.38% (-0.53% to +0.74%) | 100% | 70% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 10 | +1.98% (+1.61% to +3.59%) | +0.47% (+0.08% to +0.62%) | 100% | 90% |
| **All 60 households** | 60 | **+2.06%** (+1.60% to +2.77%) | **+0.45%** (-0.11% to +0.69%) | 100% | 82% |

## Against the typical advisor

A typical advisor: a fee of 1.15% on the first $500,000 falling to 0.6% above $5 million, funds that charge 0.60% (stocks) and 0.45% (bonds) a year, 3% in cash, no tax-loss harvesting, every account managed separately with the same mix, an age-based glide path from 80% to 50% stocks, no Roth conversions, withdrawals taken proportionally and the oldest tax lots sold first. Its taxable funds are actively managed, so they pay out capital gains every year.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 10 | +3.14% (+2.60% to +3.64%) | +1.13% (+0.93% to +1.46%) | 100% | 100% |
| Concentrated single stock (40%+ of investable assets, low basis) | 10 | +3.50% (+3.01% to +4.87%) | +1.43% (+1.26% to +1.66%) | 100% | 100% |
| Large unrealized gains (brokerage basis under 40% of value) | 10 | +2.90% (+2.36% to +3.63%) | +1.25% (+1.04% to +1.58%) | 100% | 100% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 10 | +2.72% (+2.15% to +3.06%) | +1.06% (+0.93% to +1.45%) | 100% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 10 | +2.90% (+2.28% to +4.99%) | +1.05% (+0.59% to +1.72%) | 100% | 100% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 10 | +2.60% (+0.00% to +4.06%) | +1.11% (+0.97% to +1.27%) | 80% | 100% |
| **All 60 households** | 60 | **+3.01%** (+2.29% to +3.95%) | **+1.18%** (+0.92% to +1.63%) | 97% | 100% |

## Against the do it yourself

Doing it yourself: the same age-based glide path in index funds with no advisory fee, no loss harvesting, no conversions, withdrawals taken proportionally and the oldest tax lots sold first, and the behavior gap the average investor shows (about half a point a year less than the funds earn).

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 10 | +1.24% (+1.18% to +1.63%) | -0.21% (-1.21% to +0.04%) | 100% | 20% |
| Concentrated single stock (40%+ of investable assets, low basis) | 10 | +1.50% (+1.38% to +1.79%) | -0.07% (-0.90% to +0.33%) | 100% | 50% |
| Large unrealized gains (brokerage basis under 40% of value) | 10 | +1.29% (+0.95% to +1.68%) | -0.31% (-1.09% to -0.11%) | 100% | 0% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 10 | +0.91% (+0.76% to +1.18%) | -0.22% (-0.40% to -0.08%) | 100% | 10% |
| Large purchase within 3 years (25%+ of investable assets) | 10 | +1.37% (+1.07% to +1.80%) | -0.47% (-1.81% to +0.31%) | 100% | 30% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 10 | +1.33% (+1.06% to +1.84%) | -0.01% (-0.92% to +0.20%) | 100% | 50% |
| **All 60 households** | 60 | **+1.36%** (+0.93% to +1.78%) | **-0.21%** (-1.09% to +0.18%) | 100% | 27% |

## What the planner chose, by type

Share of households of each type whose winning strategy uses each option.

| Type | Lowest stock share (50%) | Stock share 80%+ | Roth conversions | Private credit 15% | Direct indexing | Goal bonds | Roth 401(k) (any) | Borrow for goals |
|---|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 0% | 100% | 100% | 100% | 100% | 0% | 0% | 50% |
| Concentrated single stock (40%+ of investable assets, low basis) | 0% | 100% | 100% | 100% | 100% | 0% | 0% | 20% |
| Large unrealized gains (brokerage basis under 40% of value) | 0% | 100% | 70% | 100% | 100% | 0% | 0% | 10% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 100% | 20% | 70% | 100% | 0% | 0% | 0% |
| Large purchase within 3 years (25%+ of investable assets) | 0% | 100% | 90% | 100% | 90% | 0% | 0% | 50% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 0% | 100% | 100% | 100% | 70% | 0% | 10% | 40% |

Spending reserve chosen, by type (years of expenses held in bonds and private credit, everything else in stocks):

| Type | 2 years | 4 years | 6 years |
|---|---|---|---|
| Diversified, modest unrealized gains | 40% | 10% | 50% |
| Concentrated single stock (40%+ of investable assets, low basis) | 30% | 10% | 60% |
| Large unrealized gains (brokerage basis under 40% of value) | 40% | 0% | 60% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 10% | 0% | 90% |
| Large purchase within 3 years (25%+ of investable assets) | 50% | 10% | 40% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 100% | 0% | 0% |

## The two valuations at 80, against both advisors

**Liquidated at 80**: everything is sold and taxed at the horizon. **Passed to heirs at 80**: a step-up in basis on the taxable account (no tax on its unrealized gain), the Roth as it stands, the pre-tax accounts after a flat 24% tax. Each cell is the median across the households of the type: the raw (median) advantage, then the risk-adjusted advantage. The plan was chosen under the liquidated valuation. 

| Type | Against | Liquidated: median | Liquidated: risk-adjusted | Heirs: median | Heirs: risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | Good RIA | +2.05% | +0.50% | +2.15% | +0.56% |
|  | Typical advisor (its funds pay distributions) | +3.14% | +1.13% | +3.34% | +1.18% |
|  | Typical advisor without distributions | +3.06% | +1.09% | +3.24% | +1.15% |
| Concentrated single stock (40%+ of investable assets, low basis) | Good RIA | +2.29% | +0.64% | +2.50% | +0.69% |
|  | Typical advisor (its funds pay distributions) | +3.50% | +1.43% | +3.75% | +1.43% |
|  | Typical advisor without distributions | +3.30% | +1.34% | +3.49% | +1.34% |
| Large unrealized gains (brokerage basis under 40% of value) | Good RIA | +2.01% | +0.32% | +2.06% | +0.34% |
|  | Typical advisor (its funds pay distributions) | +2.90% | +1.25% | +3.09% | +1.32% |
|  | Typical advisor without distributions | +2.80% | +1.14% | +2.95% | +1.21% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | Good RIA | +1.77% | +0.37% | +1.83% | +0.43% |
|  | Typical advisor (its funds pay distributions) | +2.72% | +1.06% | +2.95% | +1.11% |
|  | Typical advisor without distributions | +2.69% | +1.04% | +2.91% | +1.10% |
| Large purchase within 3 years (25%+ of investable assets) | Good RIA | +2.08% | +0.38% | +2.04% | +0.42% |
|  | Typical advisor (its funds pay distributions) | +2.90% | +1.05% | +2.97% | +1.08% |
|  | Typical advisor without distributions | +2.86% | +1.02% | +2.90% | +1.04% |
| High earners with large pre-tax balances ($3M+ projected at 70) | Good RIA | +1.98% | +0.47% | +2.18% | +0.48% |
|  | Typical advisor (its funds pay distributions) | +2.60% | +1.11% | +2.83% | +1.11% |
|  | Typical advisor without distributions | +2.49% | +1.01% | +2.68% | +1.01% |
| **All 60 households** | Good RIA | +2.06% | +0.45% | +2.11% | +0.48% |
|  | Typical advisor (its funds pay distributions) | +3.01% | +1.18% | +3.16% | +1.25% |
|  | Typical advisor without distributions | +2.95% | +1.10% | +3.02% | +1.14% |


## Reading these numbers

* **Underfunded households.** 0 of 60 households have a median after-tax wealth at the horizon below the $50,000 floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: Diversified 3.9% for the plan vs 6.6% for the good RIA, Concentrated single stock 4.1% for the plan vs 8.1% for the good RIA, Large unrealized gains 2.2% for the plan vs 2.9% for the good RIA, Early retirement 4.9% for the plan vs 6.0% for the good RIA, Large purchase within 3 years 6.4% for the plan vs 7.0% for the good RIA, High earners with large pre-tax balances 10.0% for the plan vs 15.9% for the good RIA.
* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.
* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).

