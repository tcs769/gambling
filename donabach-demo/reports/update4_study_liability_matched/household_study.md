# Household-type study

300 synthetic households (50 of each of six types), all fictional. For each, the planner searched
its strategy menu on 400 simulated futures and the winner was scored against both advisors on 1,000 fresh
futures it never saw (risk aversion 3; planning style: liability matched, the reserve chosen to keep forced sales in falling years to 2% of futures and ruin no likelier than the advisor's). Nothing was tuned; the households were drawn from fixed ranges
that make each a clear example of its type (see `backend/app/study/households.py`).

* **Median advantage**: difference in median after-tax wealth at the horizon, annualized as a growth-rate difference.
* **Risk-adjusted advantage**: the same on certainty-equivalent wealth (the planner's objective).
* Each cell is the **median across the households of that type** (with the 10th to 90th percentile across households).
  Dollar-weighted or pooled figures would differ; this is the typical household of the type.

## Against the good ria

A good traditional advisor: an age-based glide path from 80% to 50% stocks, the same mix in every account, breakpoint fees of 1.0% falling to 0.5%, fund-level loss harvesting in years stocks fall more than 10%, goals paid from the brokerage account, no Roth conversions, pro rata withdrawals and the oldest tax lots sold first.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +1.76% (+1.45% to +2.01%) | +0.35% (-0.12% to +0.79%) | 100% | 86% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.96% (+1.63% to +2.21%) | +0.52% (+0.08% to +1.22%) | 100% | 92% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.94% (+1.62% to +2.32%) | +0.46% (-0.45% to +0.87%) | 100% | 72% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +1.25% (+0.99% to +1.69%) | +0.98% (+0.12% to +2.47%) | 100% | 92% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.25% (+1.07% to +1.80%) | +0.45% (-0.08% to +1.04%) | 100% | 88% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +1.32% (+1.04% to +1.60%) | -0.10% (-0.93% to +0.48%) | 100% | 44% |
| **All 300 households** | 300 | **+1.62%** (+1.10% to +2.09%) | **+0.43%** (-0.38% to +1.25%) | 100% | 79% |

## Against the typical advisor

A typical advisor: a fee of 1.15% on the first $500,000 falling to 0.6% above $5 million, funds that charge 0.60% (stocks) and 0.45% (bonds) a year, 3% in cash, no tax-loss harvesting, every account managed separately with the same mix, an age-based glide path from 80% to 50% stocks, no Roth conversions, withdrawals taken proportionally and the oldest tax lots sold first. Its taxable funds are actively managed, so they pay out capital gains every year.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +2.54% (+2.20% to +3.00%) | +1.38% (+0.85% to +2.03%) | 100% | 100% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +2.94% (+2.53% to +3.35%) | +1.83% (+1.05% to +2.92%) | 100% | 100% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +2.73% (+2.34% to +3.17%) | +1.37% (+0.75% to +2.29%) | 100% | 98% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +2.09% (+1.86% to +2.51%) | +2.10% (+1.14% to +3.47%) | 100% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +2.01% (+1.71% to +2.58%) | +1.49% (+0.77% to +2.08%) | 100% | 100% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +2.18% (+2.00% to +2.68%) | +1.05% (+0.49% to +2.27%) | 100% | 96% |
| **All 300 households** | 300 | **+2.43%** (+1.91% to +3.11%) | **+1.51%** (+0.74% to +2.51%) | 100% | 99% |

## Against the do it yourself

Doing it yourself: the same age-based glide path in index funds with no advisory fee, no loss harvesting, no conversions, withdrawals taken proportionally and the oldest tax lots sold first, and the behavior gap the average investor shows (about half a point a year less than the funds earn).

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +1.17% (+0.78% to +1.31%) | -0.37% (-1.16% to -0.07%) | 100% | 4% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.28% (+0.97% to +1.46%) | -0.32% (-1.21% to +0.31%) | 100% | 24% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.30% (+0.99% to +1.63%) | -0.34% (-1.55% to +0.17%) | 100% | 20% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +0.53% (+0.27% to +1.03%) | +0.22% (-0.81% to +1.88%) | 98% | 58% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +0.71% (+0.46% to +1.14%) | -0.27% (-0.92% to +0.17%) | 100% | 20% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +0.88% (+0.48% to +1.09%) | -0.96% (-2.23% to -0.33%) | 96% | 0% |
| **All 300 households** | 300 | **+1.03%** (+0.47% to +1.38%) | **-0.35%** (-1.50% to +0.32%) | 99% | 21% |

## What the planner chose, by type

Share of households of each type whose winning strategy uses each option.

| Type | Lowest stock share (50%) | Stock share 80%+ | Roth conversions | Private credit 15% | Direct indexing | Goal bonds | Roth 401(k) (any) | Borrow for goals |
|---|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 0% | 100% | 94% | 84% | 56% | 0% | 6% | 70% |
| Concentrated single stock (40%+ of investable assets, low basis) | 0% | 100% | 98% | 86% | 38% | 0% | 16% | 34% |
| Large unrealized gains (brokerage basis under 40% of value) | 0% | 100% | 94% | 82% | 56% | 0% | 10% | 26% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 100% | 42% | 44% | 28% | 0% | 12% | 0% |
| Large purchase within 3 years (25%+ of investable assets) | 0% | 100% | 40% | 40% | 14% | 0% | 10% | 88% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 0% | 100% | 74% | 58% | 26% | 0% | 44% | 56% |

Spending reserve chosen, by type (years of expenses held in bonds and private credit, everything else in stocks):

| Type | 2 years | 4 years | 6 years |
|---|---|---|---|
| Diversified, modest unrealized gains | 2% | 0% | 30% |
| Concentrated single stock (40%+ of investable assets, low basis) | 2% | 2% | 20% |
| Large unrealized gains (brokerage basis under 40% of value) | 12% | 2% | 18% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 0% | 12% |
| Large purchase within 3 years (25%+ of investable assets) | 0% | 0% | 4% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 2% | 2% | 10% |

## The two valuations at 80, against both advisors

**Liquidated at 80**: everything is sold and taxed at the horizon. **Passed to heirs at 80**: a step-up in basis on the taxable account (no tax on its unrealized gain), the Roth as it stands, the pre-tax accounts after a flat 24% tax. Each cell is the median across the households of the type: the raw (median) advantage, then the risk-adjusted advantage. The plan was chosen under the liquidated valuation. 

| Type | Against | Liquidated: median | Liquidated: risk-adjusted | Heirs: median | Heirs: risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | Good RIA | +1.76% | +0.35% | +1.83% | +0.50% |
|  | Typical advisor (its funds pay distributions) | +2.54% | +1.38% | +2.75% | +1.50% |
|  | Typical advisor without distributions | +2.50% | +1.30% | +2.64% | +1.42% |
| Concentrated single stock (40%+ of investable assets, low basis) | Good RIA | +1.96% | +0.52% | +2.11% | +0.65% |
|  | Typical advisor (its funds pay distributions) | +2.94% | +1.83% | +3.14% | +1.93% |
|  | Typical advisor without distributions | +2.81% | +1.58% | +2.96% | +1.72% |
| Large unrealized gains (brokerage basis under 40% of value) | Good RIA | +1.94% | +0.46% | +2.02% | +0.56% |
|  | Typical advisor (its funds pay distributions) | +2.73% | +1.37% | +2.94% | +1.58% |
|  | Typical advisor without distributions | +2.64% | +1.25% | +2.80% | +1.45% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | Good RIA | +1.25% | +0.98% | +1.37% | +1.24% |
|  | Typical advisor (its funds pay distributions) | +2.09% | +2.10% | +2.33% | +2.25% |
|  | Typical advisor without distributions | +2.06% | +2.04% | +2.26% | +2.18% |
| Large purchase within 3 years (25%+ of investable assets) | Good RIA | +1.25% | +0.45% | +1.34% | +0.53% |
|  | Typical advisor (its funds pay distributions) | +2.01% | +1.49% | +2.16% | +1.58% |
|  | Typical advisor without distributions | +1.96% | +1.40% | +2.08% | +1.51% |
| High earners with large pre-tax balances ($3M+ projected at 70) | Good RIA | +1.32% | -0.10% | +1.45% | +0.04% |
|  | Typical advisor (its funds pay distributions) | +2.18% | +1.05% | +2.37% | +1.12% |
|  | Typical advisor without distributions | +2.08% | +0.85% | +2.23% | +0.94% |
| **All 300 households** | Good RIA | +1.62% | +0.43% | +1.71% | +0.55% |
|  | Typical advisor (its funds pay distributions) | +2.43% | +1.51% | +2.59% | +1.67% |
|  | Typical advisor without distributions | +2.34% | +1.37% | +2.49% | +1.52% |


## Reading these numbers

* **Underfunded households.** 0 of 300 households have a median after-tax wealth at the horizon below the $50,000 floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: Diversified 1.2% for the plan vs 1.7% for the good RIA, Concentrated single stock 1.9% for the plan vs 2.6% for the good RIA, Large unrealized gains 0.7% for the plan vs 0.9% for the good RIA, Early retirement 0.5% for the plan vs 1.1% for the good RIA, Large purchase within 3 years 0.7% for the plan vs 1.1% for the good RIA, High earners with large pre-tax balances 3.4% for the plan vs 3.0% for the good RIA.
* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.
* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).

