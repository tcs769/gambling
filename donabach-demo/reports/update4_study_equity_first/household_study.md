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
| Diversified, modest unrealized gains | 50 | +1.82% (+1.55% to +2.13%) | +0.23% (-0.46% to +0.55%) | 100% | 66% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.97% (+1.67% to +2.27%) | +0.53% (-0.19% to +0.94%) | 100% | 88% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.91% (+1.55% to +2.32%) | +0.30% (-0.41% to +0.78%) | 100% | 70% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +1.42% (+1.20% to +1.67%) | +0.66% (+0.16% to +1.04%) | 100% | 92% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.74% (+1.40% to +2.07%) | +0.31% (-0.79% to +0.69%) | 100% | 72% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +1.46% (+1.27% to +1.80%) | +0.02% (-1.29% to +0.50%) | 100% | 52% |
| **All 300 households** | 300 | **+1.69%** (+1.34% to +2.14%) | **+0.32%** (-0.61% to +0.83%) | 100% | 73% |

## Against the typical advisor

A typical advisor: a fee of 1.15% on the first $500,000 falling to 0.6% above $5 million, funds that charge 0.60% (stocks) and 0.45% (bonds) a year, 3% in cash, no tax-loss harvesting, every account managed separately with the same mix, an age-based glide path from 80% to 50% stocks, no Roth conversions, withdrawals taken proportionally and the oldest tax lots sold first. Its taxable funds are actively managed, so they pay out capital gains every year.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +2.69% (+2.24% to +3.09%) | +1.25% (+0.67% to +1.75%) | 100% | 100% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +2.92% (+2.52% to +3.48%) | +1.67% (+1.07% to +2.22%) | 100% | 100% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +2.70% (+2.28% to +3.28%) | +1.41% (+0.79% to +1.77%) | 100% | 100% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +2.23% (+2.04% to +2.54%) | +1.66% (+1.17% to +2.24%) | 100% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +2.49% (+2.04% to +3.01%) | +1.13% (+0.47% to +1.61%) | 100% | 94% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +2.33% (+1.96% to +3.23%) | +1.17% (+0.64% to +1.53%) | 100% | 94% |
| **All 300 households** | 300 | **+2.54%** (+2.08% to +3.24%) | **+1.33%** (+0.75% to +2.02%) | 100% | 98% |

## Against the do it yourself

Doing it yourself: the same age-based glide path in index funds with no advisory fee, no loss harvesting, no conversions, withdrawals taken proportionally and the oldest tax lots sold first, and the behavior gap the average investor shows (about half a point a year less than the funds earn).

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +1.20% (+0.92% to +1.39%) | -0.66% (-1.53% to -0.14%) | 100% | 2% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.31% (+1.00% to +1.50%) | -0.41% (-1.28% to +0.11%) | 100% | 24% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.29% (+0.88% to +1.62%) | -0.56% (-1.62% to +0.09%) | 100% | 20% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +0.70% (+0.50% to +0.96%) | -0.11% (-0.68% to +0.24%) | 100% | 36% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.16% (+0.85% to +1.40%) | -0.53% (-1.71% to +0.01%) | 100% | 10% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +0.96% (+0.87% to +1.17%) | -1.06% (-3.41% to +0.01%) | 100% | 14% |
| **All 300 households** | 300 | **+1.12%** (+0.75% to +1.43%) | **-0.48%** (-1.69% to +0.08%) | 100% | 18% |

## What the planner chose, by type

Share of households of each type whose winning strategy uses each option.

| Type | Lowest stock share (50%) | Stock share 80%+ | Roth conversions | Private credit 15% | Direct indexing | Goal bonds | Roth 401(k) (any) | Borrow for goals |
|---|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 0% | 100% | 94% | 98% | 98% | 0% | 0% | 54% |
| Concentrated single stock (40%+ of investable assets, low basis) | 0% | 100% | 90% | 98% | 94% | 0% | 0% | 38% |
| Large unrealized gains (brokerage basis under 40% of value) | 0% | 100% | 76% | 100% | 98% | 0% | 0% | 24% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 100% | 12% | 46% | 98% | 0% | 6% | 0% |
| Large purchase within 3 years (25%+ of investable assets) | 0% | 100% | 90% | 94% | 96% | 0% | 0% | 72% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 0% | 100% | 96% | 100% | 96% | 0% | 0% | 50% |

Spending reserve chosen, by type (years of expenses held in bonds and private credit, everything else in stocks):

| Type | 2 years | 4 years | 6 years |
|---|---|---|---|
| Diversified, modest unrealized gains | 12% | 12% | 76% |
| Concentrated single stock (40%+ of investable assets, low basis) | 20% | 4% | 76% |
| Large unrealized gains (brokerage basis under 40% of value) | 14% | 10% | 76% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 0% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 14% | 8% | 78% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 24% | 8% | 68% |

## The two valuations at 80, against both advisors

**Liquidated at 80**: everything is sold and taxed at the horizon. **Passed to heirs at 80**: a step-up in basis on the taxable account (no tax on its unrealized gain), the Roth as it stands, the pre-tax accounts after a flat 24% tax. Each cell is the median across the households of the type: the raw (median) advantage, then the risk-adjusted advantage. The plan was chosen under the liquidated valuation. 

| Type | Against | Liquidated: median | Liquidated: risk-adjusted | Heirs: median | Heirs: risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | Good RIA | +1.82% | +0.23% | +1.94% | +0.32% |
|  | Typical advisor (its funds pay distributions) | +2.69% | +1.25% | +2.79% | +1.35% |
|  | Typical advisor without distributions | +2.60% | +1.16% | +2.69% | +1.25% |
| Concentrated single stock (40%+ of investable assets, low basis) | Good RIA | +1.97% | +0.53% | +2.22% | +0.60% |
|  | Typical advisor (its funds pay distributions) | +2.92% | +1.67% | +3.18% | +1.75% |
|  | Typical advisor without distributions | +2.76% | +1.46% | +3.00% | +1.55% |
| Large unrealized gains (brokerage basis under 40% of value) | Good RIA | +1.91% | +0.30% | +2.04% | +0.44% |
|  | Typical advisor (its funds pay distributions) | +2.70% | +1.41% | +2.97% | +1.53% |
|  | Typical advisor without distributions | +2.62% | +1.23% | +2.84% | +1.38% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | Good RIA | +1.42% | +0.66% | +1.51% | +0.85% |
|  | Typical advisor (its funds pay distributions) | +2.23% | +1.66% | +2.40% | +1.83% |
|  | Typical advisor without distributions | +2.20% | +1.64% | +2.36% | +1.81% |
| Large purchase within 3 years (25%+ of investable assets) | Good RIA | +1.74% | +0.31% | +1.86% | +0.46% |
|  | Typical advisor (its funds pay distributions) | +2.49% | +1.13% | +2.71% | +1.29% |
|  | Typical advisor without distributions | +2.45% | +1.10% | +2.60% | +1.24% |
| High earners with large pre-tax balances ($3M+ projected at 70) | Good RIA | +1.46% | +0.02% | +1.64% | +0.03% |
|  | Typical advisor (its funds pay distributions) | +2.33% | +1.17% | +2.57% | +1.19% |
|  | Typical advisor without distributions | +2.22% | +0.98% | +2.42% | +0.99% |
| **All 300 households** | Good RIA | +1.69% | +0.32% | +1.85% | +0.45% |
|  | Typical advisor (its funds pay distributions) | +2.54% | +1.33% | +2.77% | +1.47% |
|  | Typical advisor without distributions | +2.47% | +1.21% | +2.66% | +1.34% |


## Reading these numbers

* **Underfunded households.** 0 of 300 households have a median after-tax wealth at the horizon below the $50,000 floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: Diversified 2.4% for the plan vs 1.7% for the good RIA, Concentrated single stock 1.8% for the plan vs 2.6% for the good RIA, Large unrealized gains 0.8% for the plan vs 0.9% for the good RIA, Early retirement 0.7% for the plan vs 1.1% for the good RIA, Large purchase within 3 years 1.9% for the plan vs 1.1% for the good RIA, High earners with large pre-tax balances 2.4% for the plan vs 3.0% for the good RIA.
* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.
* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).

