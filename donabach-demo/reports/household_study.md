# Household-type study

300 synthetic households (50 of each of six types), all fictional. For each, the planner searched
its strategy menu on 400 simulated futures and the winner was scored against both advisors on 1,000 fresh
futures it never saw (risk aversion 3). Nothing was tuned; the households were drawn from fixed ranges
that make each a clear example of its type (see `backend/app/study/households.py`).

* **Median advantage**: difference in median after-tax wealth at the horizon, annualized as a growth-rate difference.
* **Risk-adjusted advantage**: the same on certainty-equivalent wealth (the planner's objective).
* Each cell is the **median across the households of that type** (with the 10th to 90th percentile across households).
  Dollar-weighted or pooled figures would differ; this is the typical household of the type.

## Against the good ria

A good traditional advisor: an age-based glide path from 80% to 50% stocks, the same mix in every account, breakpoint fees of 1.0% falling to 0.5%, fund-level loss harvesting in years stocks fall more than 10%, goals paid from the brokerage account, no Roth conversions and pro rata withdrawals.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +0.36% (+0.02% to +0.67%) | +2.16% (+1.06% to +3.05%) | 96% | 100% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +0.41% (-0.11% to +1.21%) | +2.08% (+0.96% to +2.98%) | 80% | 100% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +0.55% (-0.11% to +1.17%) | +2.11% (+1.07% to +3.73%) | 76% | 100% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +0.14% (-0.09% to +0.64%) | +2.97% (+1.97% to +4.35%) | 78% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +0.54% (+0.06% to +0.94%) | +1.62% (+0.83% to +2.89%) | 98% | 100% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +0.26% (-0.02% to +0.82%) | +2.09% (+0.78% to +4.46%) | 82% | 100% |
| **All 300 households** | 300 | **+0.35%** (-0.06% to +0.95%) | **+2.19%** (+0.94% to +3.86%) | 85% | 100% |

## Against the typical advisor

A typical advisor: a flat 1.0% fee at every balance, no tax-loss harvesting, every account managed separately with the same mix, an age-based glide path from 80% to 50% stocks, no Roth conversions and withdrawals taken proportionally.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +0.45% (+0.19% to +0.85%) | +2.20% (+1.15% to +3.16%) | 100% | 100% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +0.59% (+0.11% to +1.34%) | +2.18% (+1.05% to +3.06%) | 90% | 100% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +0.59% (+0.04% to +1.27%) | +2.20% (+1.12% to +3.79%) | 90% | 100% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +0.23% (+0.03% to +0.69%) | +3.04% (+2.02% to +4.42%) | 92% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +0.60% (+0.22% to +1.06%) | +1.78% (+0.92% to +3.00%) | 100% | 100% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +0.59% (+0.26% to +1.17%) | +2.38% (+1.01% to +4.79%) | 100% | 100% |
| **All 300 households** | 300 | **+0.51%** (+0.12% to +1.15%) | **+2.26%** (+1.04% to +3.91%) | 95% | 100% |

## What the planner chose, by type

Share of households of each type whose winning strategy uses each option.

| Type | Lowest stock share (50%) | Stock share 80%+ | Roth conversions | Private credit 15% | Direct indexing | Goal bonds | Roth 401(k) (any) | Borrow for goals |
|---|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 56% | 6% | 74% | 100% | 86% | 18% | 0% | 22% |
| Concentrated single stock (40%+ of investable assets, low basis) | 42% | 22% | 78% | 98% | 100% | 20% | 0% | 20% |
| Large unrealized gains (brokerage basis under 40% of value) | 36% | 28% | 56% | 96% | 86% | 20% | 0% | 12% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 60% | 6% | 16% | 100% | 40% | 0% | 0% | 0% |
| Large purchase within 3 years (25%+ of investable assets) | 40% | 18% | 84% | 100% | 84% | 26% | 0% | 54% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 44% | 14% | 98% | 100% | 100% | 22% | 0% | 36% |

## Reading these numbers

* **Underfunded households.** 0 of 300 households have a median after-tax wealth at the horizon below the $50,000 floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: Diversified 0.5% for the plan vs 2.2% for the good RIA, Concentrated single stock 1.1% for the plan vs 3.4% for the good RIA, Large unrealized gains 0.2% for the plan vs 1.2% for the good RIA, Early retirement 0.2% for the plan vs 1.4% for the good RIA, Large purchase within 3 years 0.3% for the plan vs 1.3% for the good RIA, High earners with large pre-tax balances 1.5% for the plan vs 3.7% for the good RIA.
* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.
* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).

