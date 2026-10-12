# Household-type study

300 synthetic households (50 of each of six types), all fictional. For each, the planner searched
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
| Diversified, modest unrealized gains | 50 | +1.82% (+1.55% to +2.13%) | +0.21% (-0.45% to +0.56%) | 100% | 66% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.96% (+1.65% to +2.30%) | +0.51% (-0.27% to +0.97%) | 100% | 88% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.90% (+1.55% to +2.29%) | +0.30% (-0.54% to +0.78%) | 100% | 70% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +1.43% (+1.23% to +1.66%) | +0.84% (+0.16% to +1.22%) | 100% | 92% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.75% (+1.40% to +2.10%) | +0.30% (-0.82% to +0.70%) | 100% | 70% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +1.46% (+1.27% to +1.85%) | +0.02% (-1.30% to +0.53%) | 100% | 52% |
| **All 300 households** | 300 | **+1.69%** (+1.35% to +2.15%) | **+0.33%** (-0.60% to +0.94%) | 100% | 73% |

## Against the typical advisor

A typical advisor: a fee of 1.15% on the first $500,000 falling to 0.6% above $5 million, funds that charge 0.60% (stocks) and 0.45% (bonds) a year, 3% in cash, no tax-loss harvesting, every account managed separately with the same mix, an age-based glide path from 80% to 50% stocks, no Roth conversions, withdrawals taken proportionally and the oldest tax lots sold first. Its taxable funds are actively managed, so they pay out capital gains every year.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +2.69% (+2.24% to +3.09%) | +1.21% (+0.74% to +1.78%) | 100% | 100% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +2.91% (+2.47% to +3.49%) | +1.65% (+1.05% to +2.22%) | 100% | 100% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +2.69% (+2.29% to +3.19%) | +1.40% (+0.79% to +1.78%) | 100% | 100% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +2.25% (+2.06% to +2.55%) | +1.89% (+1.16% to +2.44%) | 100% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +2.52% (+2.06% to +3.03%) | +1.14% (+0.47% to +1.66%) | 100% | 94% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +2.33% (+1.96% to +3.23%) | +1.17% (+0.59% to +1.54%) | 100% | 94% |
| **All 300 households** | 300 | **+2.54%** (+2.10% to +3.21%) | **+1.34%** (+0.76% to +2.10%) | 100% | 98% |

## Against the do it yourself

Doing it yourself: the same age-based glide path in index funds with no advisory fee, no loss harvesting, no conversions, withdrawals taken proportionally and the oldest tax lots sold first, and the behavior gap the average investor shows (about half a point a year less than the funds earn).

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +1.20% (+0.92% to +1.40%) | -0.71% (-1.49% to -0.14%) | 100% | 2% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.30% (+0.96% to +1.51%) | -0.42% (-1.28% to +0.16%) | 100% | 26% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.27% (+0.88% to +1.58%) | -0.56% (-1.62% to +0.09%) | 100% | 20% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +0.71% (+0.54% to +0.93%) | -0.01% (-0.57% to +0.45%) | 100% | 48% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.16% (+0.86% to +1.40%) | -0.53% (-1.65% to +0.03%) | 100% | 12% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +0.96% (+0.88% to +1.20%) | -1.06% (-3.41% to +0.02%) | 100% | 14% |
| **All 300 households** | 300 | **+1.11%** (+0.75% to +1.43%) | **-0.49%** (-1.69% to +0.15%) | 100% | 20% |

## What the planner chose, by type

Share of households of each type whose winning strategy uses each option.

| Type | Lowest stock share (50%) | Stock share 80%+ | Roth conversions | Private credit 15% | Direct indexing | Goal bonds | Roth 401(k) (any) | Borrow for goals |
|---|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 0% | 100% | 94% | 98% | 96% | 0% | 0% | 54% |
| Concentrated single stock (40%+ of investable assets, low basis) | 0% | 100% | 86% | 98% | 92% | 0% | 0% | 32% |
| Large unrealized gains (brokerage basis under 40% of value) | 0% | 100% | 76% | 98% | 92% | 0% | 0% | 30% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 100% | 10% | 50% | 88% | 0% | 6% | 0% |
| Large purchase within 3 years (25%+ of investable assets) | 0% | 100% | 90% | 94% | 94% | 0% | 0% | 68% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 0% | 100% | 96% | 100% | 84% | 0% | 0% | 44% |

Spending reserve chosen, by type (years of expenses held in bonds and private credit, everything else in stocks):

| Type | 2 years | 4 years | 6 years |
|---|---|---|---|
| Diversified, modest unrealized gains | 12% | 16% | 72% |
| Concentrated single stock (40%+ of investable assets, low basis) | 20% | 6% | 74% |
| Large unrealized gains (brokerage basis under 40% of value) | 12% | 10% | 78% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 0% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 12% | 10% | 78% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 26% | 8% | 66% |

## The two valuations at 80, against both advisors

**Liquidated at 80**: everything is sold and taxed at the horizon. **Passed to heirs at 80**: a step-up in basis on the taxable account (no tax on its unrealized gain), the Roth as it stands, the pre-tax accounts after a flat 24% tax. Each cell is the median across the households of the type: the raw (median) advantage, then the risk-adjusted advantage. The plan was chosen under the liquidated valuation. 

| Type | Against | Liquidated: median | Liquidated: risk-adjusted | Heirs: median | Heirs: risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | Good RIA | +1.82% | +0.21% | +1.94% | +0.29% |
|  | Typical advisor (its funds pay distributions) | +2.69% | +1.21% | +2.79% | +1.29% |
|  | Typical advisor without distributions | +2.59% | +1.12% | +2.69% | +1.23% |
| Concentrated single stock (40%+ of investable assets, low basis) | Good RIA | +1.96% | +0.51% | +2.22% | +0.59% |
|  | Typical advisor (its funds pay distributions) | +2.91% | +1.65% | +3.18% | +1.75% |
|  | Typical advisor without distributions | +2.73% | +1.43% | +3.00% | +1.55% |
| Large unrealized gains (brokerage basis under 40% of value) | Good RIA | +1.90% | +0.30% | +2.02% | +0.43% |
|  | Typical advisor (its funds pay distributions) | +2.69% | +1.40% | +2.93% | +1.51% |
|  | Typical advisor without distributions | +2.61% | +1.23% | +2.81% | +1.34% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | Good RIA | +1.43% | +0.84% | +1.53% | +0.99% |
|  | Typical advisor (its funds pay distributions) | +2.25% | +1.89% | +2.40% | +1.99% |
|  | Typical advisor without distributions | +2.21% | +1.86% | +2.36% | +1.96% |
| Large purchase within 3 years (25%+ of investable assets) | Good RIA | +1.75% | +0.30% | +1.87% | +0.45% |
|  | Typical advisor (its funds pay distributions) | +2.52% | +1.14% | +2.71% | +1.30% |
|  | Typical advisor without distributions | +2.48% | +1.07% | +2.61% | +1.23% |
| High earners with large pre-tax balances ($3M+ projected at 70) | Good RIA | +1.46% | +0.02% | +1.64% | +0.03% |
|  | Typical advisor (its funds pay distributions) | +2.33% | +1.17% | +2.56% | +1.20% |
|  | Typical advisor without distributions | +2.22% | +0.96% | +2.42% | +0.98% |
| **All 300 households** | Good RIA | +1.69% | +0.33% | +1.85% | +0.45% |
|  | Typical advisor (its funds pay distributions) | +2.54% | +1.34% | +2.76% | +1.47% |
|  | Typical advisor without distributions | +2.47% | +1.21% | +2.67% | +1.33% |


## Reading these numbers

* **Underfunded households.** 0 of 300 households have a median after-tax wealth at the horizon below the $50,000 floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: Diversified 2.4% for the plan vs 1.7% for the good RIA, Concentrated single stock 1.8% for the plan vs 2.6% for the good RIA, Large unrealized gains 0.8% for the plan vs 0.9% for the good RIA, Early retirement 0.7% for the plan vs 1.1% for the good RIA, Large purchase within 3 years 1.3% for the plan vs 1.1% for the good RIA, High earners with large pre-tax balances 2.3% for the plan vs 3.0% for the good RIA.
* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.
* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).

