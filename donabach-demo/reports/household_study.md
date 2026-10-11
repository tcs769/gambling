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

## The adaptive planner: four strategies, by type

On 200 of each household's held-out futures (the same futures for all four strategies), the **typical advisor**, the **good RIA**, the **best fixed strategy** (the winner above) and the **adaptive planner** (the year-by-year planner of spec part B, K = 32 rollouts per candidate, each proposed change re-tested on 64 fresh futures; 6.5 seconds per household on average). Advantage cells are the median across the households of the type, with the 10th to 90th percentile across households. The 10th-percentile outcome and lifetime taxes are medians across households (real 2026 dollars, at the household's horizon; taxes are those paid over the plan plus tax owed on the pre-tax balance at the end).
With only 200 futures per household the risk-adjusted figure of a single household is noisy (it is decided by whether one or two futures run out of money), so read the medians across households, not any one household.

| Type | Strategy | Median advantage over the typical advisor | Risk-adjusted advantage over the typical advisor | Median advantage over the good RIA | Risk-adjusted advantage over the good RIA | 10th-percentile outcome | Lifetime taxes |
|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | Typical advisor | baseline | baseline | n/a | n/a | $657,337 | $1,424,106 |
|  | Good RIA | +0.12% (+0.06% to +0.20%) | +0.06% (+0.01% to +0.14%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $696,143 | $1,439,266 |
|  | Best fixed strategy | +0.48% (+0.19% to +0.82%) | +2.23% (+0.99% to +3.64%) | +0.36% (+0.03% to +0.66%) | +2.13% (+0.89% to +3.53%) | $1,174,058 | $1,382,689 |
|  | Adaptive planner | +0.52% (+0.26% to +0.83%) | +2.33% (+1.04% to +3.83%) | +0.39% (+0.09% to +0.72%) | +2.25% (+0.97% to +3.63%) | $1,177,584 | $1,402,115 |
| Concentrated single stock (40%+ of investable assets, low basis) | Typical advisor | baseline | baseline | n/a | n/a | $524,999 | $1,236,646 |
|  | Good RIA | +0.13% (+0.05% to +0.27%) | +0.06% (+0.03% to +0.19%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $533,468 | $1,245,952 |
|  | Best fixed strategy | +0.56% (-0.01% to +1.38%) | +1.64% (+1.07% to +3.68%) | +0.41% (-0.16% to +1.16%) | +1.57% (+0.97% to +3.60%) | $900,368 | $1,243,744 |
|  | Adaptive planner | +0.56% (+0.04% to +1.40%) | +1.91% (+1.15% to +3.81%) | +0.44% (-0.11% to +1.19%) | +1.83% (+1.05% to +3.73%) | $914,165 | $1,239,233 |
| Large unrealized gains (brokerage basis under 40% of value) | Typical advisor | baseline | baseline | n/a | n/a | $730,210 | $796,994 |
|  | Good RIA | +0.12% (+0.05% to +0.22%) | +0.06% (+0.02% to +0.19%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $741,165 | $803,527 |
|  | Best fixed strategy | +0.64% (+0.03% to +1.29%) | +1.98% (+1.05% to +3.92%) | +0.57% (-0.13% to +1.21%) | +1.85% (+0.93% to +3.79%) | $1,074,907 | $850,599 |
|  | Adaptive planner | +0.66% (+0.11% to +1.35%) | +2.06% (+1.13% to +4.19%) | +0.58% (-0.07% to +1.24%) | +1.92% (+0.99% to +4.05%) | $1,093,309 | $857,247 |
| Early retirement (55 to 58 now, several low-income years before Social Security) | Typical advisor | baseline | baseline | n/a | n/a | $449,614 | $277,758 |
|  | Good RIA | +0.08% (+0.01% to +0.15%) | +0.03% (+0.01% to +0.11%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $457,564 | $279,803 |
|  | Best fixed strategy | +0.32% (-0.18% to +0.70%) | +2.89% (+1.44% to +4.77%) | +0.22% (-0.26% to +0.63%) | +2.84% (+1.38% to +4.62%) | $681,012 | $273,650 |
|  | Adaptive planner | +0.37% (-0.04% to +0.86%) | +3.36% (+1.51% to +4.99%) | +0.30% (-0.13% to +0.76%) | +3.30% (+1.45% to +4.97%) | $686,423 | $283,304 |
| Large purchase within 3 years (25%+ of investable assets) | Typical advisor | baseline | baseline | n/a | n/a | $670,828 | $1,617,462 |
|  | Good RIA | +0.11% (+0.03% to +0.18%) | +0.06% (+0.01% to +0.18%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $686,738 | $1,639,324 |
|  | Best fixed strategy | +0.67% (+0.20% to +1.09%) | +1.50% (+0.84% to +3.41%) | +0.57% (+0.09% to +0.97%) | +1.38% (+0.75% to +3.37%) | $1,067,647 | $1,528,656 |
|  | Adaptive planner | +0.71% (+0.30% to +1.11%) | +1.70% (+0.91% to +3.57%) | +0.61% (+0.17% to +1.01%) | +1.63% (+0.82% to +3.54%) | $1,071,885 | $1,532,353 |
| High earners with large pre-tax balances ($3M+ projected at 70) | Typical advisor | baseline | baseline | n/a | n/a | $1,445,600 | $6,772,776 |
|  | Good RIA | +0.31% (+0.20% to +0.46%) | +0.26% (+0.11% to +0.46%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $1,586,201 | $6,854,452 |
|  | Best fixed strategy | +0.58% (+0.24% to +1.11%) | +2.00% (+0.94% to +5.13%) | +0.29% (-0.05% to +0.78%) | +1.64% (+0.68% to +5.00%) | $2,631,180 | $6,643,794 |
|  | Adaptive planner | +0.59% (+0.29% to +1.13%) | +2.01% (+1.03% to +5.55%) | +0.29% (-0.04% to +0.80%) | +1.68% (+0.79% to +5.02%) | $2,647,617 | $6,631,627 |

## The value of judgment over time, by type

The adaptive planner against the best fixed strategy it continues, on the same futures: what choosing each year's decisions after seeing that year's returns adds.

| Type | Median advantage over the best fixed strategy | Risk-adjusted advantage over the best fixed strategy | Households where it is ahead (median / risk-adjusted) | Decision-years where it leaves the fixed strategy | Mostly changes |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | +0.04% (+0.01% to +0.11%) | +0.07% (+0.01% to +0.56%) | 96% / 92% | 10.5% | conversion (8.8%) |
| Concentrated single stock (40%+ of investable assets, low basis) | +0.02% (+0.00% to +0.08%) | +0.07% (+0.01% to +0.49%) | 90% / 94% | 11.7% | conversion (5.1%) |
| Large unrealized gains (brokerage basis under 40% of value) | +0.04% (+0.00% to +0.10%) | +0.06% (+0.02% to +0.38%) | 94% / 100% | 17.7% | conversion (9.1%) |
| Early retirement (55 to 58 now, several low-income years before Social Security) | +0.11% (+0.04% to +0.17%) | +0.11% (+0.04% to +0.55%) | 98% / 100% | 25.3% | conversion (13.1%) |
| Large purchase within 3 years (25%+ of investable assets) | +0.04% (+0.00% to +0.13%) | +0.06% (+0.02% to +0.38%) | 94% / 98% | 12.5% | conversion (10.2%) |
| High earners with large pre-tax balances ($3M+ projected at 70) | +0.01% (+0.00% to +0.07%) | +0.02% (+0.00% to +0.27%) | 82% / 98% | 7.7% | conversion (5.6%) |
| **All 300 households** | +0.03% (+0.00% to +0.13%) | +0.07% (+0.01% to +0.49%) | 92% / 97% | 14.2% | conversion (8.6%) |


## Reading these numbers

* **Underfunded households.** 0 of 300 households have a median after-tax wealth at the horizon below the $50,000 floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: Diversified 0.5% for the plan vs 2.2% for the good RIA, Concentrated single stock 1.1% for the plan vs 3.4% for the good RIA, Large unrealized gains 0.2% for the plan vs 1.2% for the good RIA, Early retirement 0.2% for the plan vs 1.4% for the good RIA, Large purchase within 3 years 0.3% for the plan vs 1.3% for the good RIA, High earners with large pre-tax balances 1.5% for the plan vs 3.7% for the good RIA.
* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.
* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).

