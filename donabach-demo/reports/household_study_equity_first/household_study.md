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
| Diversified, modest unrealized gains | 50 | +1.66% (+1.45% to +1.95%) | +0.35% (-0.20% to +0.73%) | 100% | 84% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.91% (+1.65% to +2.26%) | +0.57% (-0.07% to +1.06%) | 100% | 84% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.73% (+1.50% to +2.06%) | +0.46% (-0.40% to +0.85%) | 100% | 82% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +1.37% (+1.21% to +1.57%) | +0.89% (+0.50% to +1.45%) | 100% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.63% (+1.37% to +1.91%) | +0.40% (-0.69% to +0.79%) | 100% | 78% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +1.52% (+1.32% to +1.99%) | +0.16% (-1.75% to +0.59%) | 100% | 58% |
| **All 300 households** | 300 | **+1.63%** (+1.33% to +2.03%) | **+0.46%** (-0.49% to +1.09%) | 100% | 81% |

## Against the typical advisor

A typical advisor: a flat 1.0% fee at every balance, no tax-loss harvesting, every account managed separately with the same mix, an age-based glide path from 80% to 50% stocks, no Roth conversions, withdrawals taken proportionally and the oldest tax lots sold first.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +1.76% (+1.57% to +2.11%) | +0.41% (-0.11% to +0.80%) | 100% | 86% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +2.06% (+1.82% to +2.45%) | +0.65% (-0.03% to +1.08%) | 100% | 88% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.85% (+1.57% to +2.21%) | +0.51% (-0.40% to +0.89%) | 100% | 82% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +1.48% (+1.29% to +1.65%) | +0.92% (+0.59% to +1.49%) | 100% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.73% (+1.46% to +2.06%) | +0.45% (-0.63% to +0.81%) | 100% | 80% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +1.84% (+1.60% to +2.55%) | +0.38% (-1.34% to +0.77%) | 100% | 64% |
| **All 300 households** | 300 | **+1.78%** (+1.46% to +2.26%) | **+0.55%** (-0.35% to +1.10%) | 100% | 83% |

## What the planner chose, by type

Share of households of each type whose winning strategy uses each option.

| Type | Lowest stock share (50%) | Stock share 80%+ | Roth conversions | Private credit 15% | Direct indexing | Goal bonds | Roth 401(k) (any) | Borrow for goals |
|---|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 0% | 100% | 86% | 98% | 70% | 0% | 0% | 34% |
| Concentrated single stock (40%+ of investable assets, low basis) | 0% | 100% | 86% | 100% | 92% | 0% | 2% | 26% |
| Large unrealized gains (brokerage basis under 40% of value) | 0% | 100% | 70% | 100% | 76% | 0% | 0% | 16% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 100% | 18% | 54% | 40% | 0% | 0% | 0% |
| Large purchase within 3 years (25%+ of investable assets) | 0% | 100% | 92% | 96% | 68% | 0% | 0% | 52% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 0% | 100% | 96% | 94% | 90% | 0% | 0% | 34% |

Spending reserve chosen, by type (years of expenses held in bonds and private credit, everything else in stocks):

| Type | 2 years | 4 years | 6 years |
|---|---|---|---|
| Diversified, modest unrealized gains | 16% | 16% | 68% |
| Concentrated single stock (40%+ of investable assets, low basis) | 28% | 4% | 68% |
| Large unrealized gains (brokerage basis under 40% of value) | 12% | 6% | 82% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 0% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 24% | 10% | 66% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 30% | 10% | 60% |

## The adaptive planner: four strategies, by type

On 200 of each household's held-out futures (the same futures for all four strategies), the **typical advisor**, the **good RIA**, the **best fixed strategy** (the winner above) and the **adaptive planner** (the year-by-year planner of spec part B, K = 32 rollouts per candidate, each proposed change re-tested on 64 fresh futures; 7.3 seconds per household on average). Advantage cells are the median across the households of the type, with the 10th to 90th percentile across households. The 10th-percentile outcome and lifetime taxes are medians across households (real 2026 dollars, at the household's horizon; taxes are those paid over the plan plus tax owed on the pre-tax balance at the end).
With only 200 futures per household the risk-adjusted figure of a single household is noisy (it is decided by whether one or two futures run out of money), so read the medians across households, not any one household.

| Type | Strategy | Median advantage over the typical advisor | Risk-adjusted advantage over the typical advisor | Median advantage over the good RIA | Risk-adjusted advantage over the good RIA | 10th-percentile outcome | Lifetime taxes |
|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | Typical advisor | baseline | baseline | n/a | n/a | $659,203 | $1,430,269 |
|  | Good RIA | +0.12% (+0.07% to +0.20%) | +0.06% (+0.01% to +0.14%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $694,625 | $1,445,980 |
|  | Best fixed strategy | +1.79% (+1.52% to +2.13%) | +0.52% (-0.14% to +1.48%) | +1.69% (+1.41% to +1.98%) | +0.44% (-0.29% to +1.41%) | $1,021,749 | $1,406,423 |
|  | Adaptive planner | +1.83% (+1.60% to +2.15%) | +0.55% (-0.18% to +1.58%) | +1.73% (+1.47% to +1.99%) | +0.48% (-0.34% to +1.52%) | $1,036,760 | $1,322,441 |
| Concentrated single stock (40%+ of investable assets, low basis) | Typical advisor | baseline | baseline | n/a | n/a | $525,394 | $1,258,710 |
|  | Good RIA | +0.13% (+0.05% to +0.28%) | +0.06% (+0.02% to +0.19%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $528,017 | $1,272,272 |
|  | Best fixed strategy | +2.05% (+1.73% to +2.48%) | +0.75% (+0.16% to +1.23%) | +1.91% (+1.61% to +2.26%) | +0.70% (+0.13% to +1.11%) | $812,176 | $1,018,458 |
|  | Adaptive planner | +2.07% (+1.83% to +2.50%) | +0.82% (+0.18% to +1.28%) | +1.97% (+1.73% to +2.30%) | +0.71% (+0.15% to +1.25%) | $820,175 | $1,015,401 |
| Large unrealized gains (brokerage basis under 40% of value) | Typical advisor | baseline | baseline | n/a | n/a | $734,543 | $813,335 |
|  | Good RIA | +0.12% (+0.05% to +0.22%) | +0.07% (+0.01% to +0.19%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $746,413 | $818,562 |
|  | Best fixed strategy | +1.83% (+1.55% to +2.22%) | +0.80% (+0.08% to +1.29%) | +1.75% (+1.46% to +2.05%) | +0.76% (+0.04% to +1.14%) | $942,818 | $747,375 |
|  | Adaptive planner | +1.92% (+1.72% to +2.22%) | +0.93% (+0.27% to +1.34%) | +1.83% (+1.56% to +2.07%) | +0.88% (+0.19% to +1.22%) | $954,310 | $746,829 |
| Early retirement (55 to 58 now, several low-income years before Social Security) | Typical advisor | baseline | baseline | n/a | n/a | $450,383 | $278,653 |
|  | Good RIA | +0.08% (+0.01% to +0.15%) | +0.03% (+0.00% to +0.10%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $458,439 | $280,247 |
|  | Best fixed strategy | +1.53% (+1.23% to +1.72%) | +1.16% (+0.53% to +2.02%) | +1.47% (+1.16% to +1.66%) | +1.10% (+0.44% to +1.94%) | $539,609 | $283,993 |
|  | Adaptive planner | +1.68% (+1.40% to +1.89%) | +1.37% (+0.57% to +2.35%) | +1.61% (+1.32% to +1.83%) | +1.36% (+0.49% to +2.29%) | $567,799 | $281,631 |
| Large purchase within 3 years (25%+ of investable assets) | Typical advisor | baseline | baseline | n/a | n/a | $677,486 | $1,619,841 |
|  | Good RIA | +0.11% (+0.03% to +0.18%) | +0.05% (+0.01% to +0.16%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $692,209 | $1,645,024 |
|  | Best fixed strategy | +1.70% (+1.47% to +2.16%) | +0.60% (+0.00% to +0.97%) | +1.62% (+1.36% to +1.97%) | +0.57% (-0.03% to +0.90%) | $1,026,570 | $1,487,339 |
|  | Adaptive planner | +1.75% (+1.52% to +2.19%) | +0.73% (+0.02% to +1.01%) | +1.67% (+1.42% to +2.02%) | +0.69% (-0.00% to +0.94%) | $1,050,086 | $1,467,574 |
| High earners with large pre-tax balances ($3M+ projected at 70) | Typical advisor | baseline | baseline | n/a | n/a | $1,449,170 | $6,789,690 |
|  | Good RIA | +0.31% (+0.20% to +0.46%) | +0.24% (+0.08% to +0.45%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $1,584,554 | $6,887,811 |
|  | Best fixed strategy | +1.79% (+1.56% to +2.44%) | +0.55% (-0.33% to +0.99%) | +1.50% (+1.29% to +1.87%) | +0.32% (-0.61% to +0.77%) | $2,161,611 | $7,059,604 |
|  | Adaptive planner | +1.80% (+1.59% to +2.44%) | +0.64% (-0.33% to +1.05%) | +1.52% (+1.30% to +1.87%) | +0.37% (-0.61% to +0.80%) | $2,160,850 | $7,062,157 |

## The value of judgment over time, by type

The adaptive planner against the best fixed strategy it continues, on the same futures: what choosing each year's decisions after seeing that year's returns adds.

| Type | Median advantage over the best fixed strategy | Risk-adjusted advantage over the best fixed strategy | Households where it is ahead (median / risk-adjusted) | Decision-years where it leaves the fixed strategy | Mostly changes |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | +0.03% (+0.00% to +0.16%) | +0.03% (+0.00% to +0.18%) | 94% / 96% | 16.2% | conversion (8.1%) |
| Concentrated single stock (40%+ of investable assets, low basis) | +0.02% (+0.00% to +0.11%) | +0.03% (+0.00% to +0.19%) | 88% / 96% | 13.8% | realize gains (8.3%) |
| Large unrealized gains (brokerage basis under 40% of value) | +0.07% (+0.00% to +0.19%) | +0.06% (+0.00% to +0.21%) | 96% / 94% | 21.9% | realize gains (11.9%) |
| Early retirement (55 to 58 now, several low-income years before Social Security) | +0.14% (+0.06% to +0.26%) | +0.18% (+0.04% to +0.38%) | 96% / 98% | 37.0% | realize gains (25.5%) |
| Large purchase within 3 years (25%+ of investable assets) | +0.02% (+0.00% to +0.15%) | +0.02% (+0.00% to +0.18%) | 90% / 100% | 15.2% | conversion (8.0%) |
| High earners with large pre-tax balances ($3M+ projected at 70) | +0.00% (-0.00% to +0.06%) | +0.00% (-0.00% to +0.09%) | 64% / 80% | 10.8% | conversion (10.4%) |
| **All 300 households** | +0.03% (+0.00% to +0.19%) | +0.04% (+0.00% to +0.24%) | 88% / 94% | 19.1% | realize gains (10.2%) |


## How much of the advantage is the tools, and how much is a different amount of equity

'Tools only' runs the plan's own choices (fee, asset location, conversions, withdrawal order, 401(k) type, goal funding, direct indexing) with the good RIA's allocation (80% stocks today falling to 50% from 70, no private credit), so it differs from the advisor in nothing else. The rest of the plan's advantage comes from its different stock share and private credit sleeve, which is a different amount of risk. Cells are medians across the households of the type; stocks are a share of the whole portfolio.

| Type | Plan: stocks today / from 70 | Plan: raw advantage | Tools only: raw advantage | From the allocation | Chance of running out: plan / tools only / good RIA |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 84% / 85% | +1.66% | +0.81% (+0.69% to +1.06%) | +0.82% | 1.6% / 1.1% / 2.1% |
| Concentrated single stock (40%+ of investable assets, low basis) | 84% / 85% | +1.91% | +0.85% (+0.67% to +1.12%) | +1.07% | 2.2% / 1.6% / 3.3% |
| Large unrealized gains (brokerage basis under 40% of value) | 85% / 85% | +1.73% | +0.81% (+0.68% to +0.95%) | +0.91% | 0.9% / 0.6% / 1.2% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 75% / 85% | +1.37% | +0.79% (+0.70% to +0.92%) | +0.62% | 0.9% / 0.9% / 1.4% |
| Large purchase within 3 years (25%+ of investable assets) | 85% / 85% | +1.63% | +0.84% (+0.60% to +1.03%) | +0.79% | 1.9% / 0.6% / 1.3% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 85% / 85% | +1.52% | +0.70% (+0.55% to +0.97%) | +0.81% | 2.8% / 2.1% / 3.7% |
| **All 300 households** | 84% / 85% | +1.63% | +0.80% (+0.64% to +1.01%) | +0.83% | 1.7% / 1.2% / 2.2% |


## If heirs paid a flat tax on pre-tax money at the horizon (sensitivity)

The app values a pre-tax balance at the horizon as if it were withdrawn evenly over 20 years beside Social Security, a low rate. A non-spouse heir must empty an inherited account within ten years. Median raw advantage over the good RIA with the balance taxed at a flat rate instead (median across the households of the type; the plan's choices are the ones the planner made under the app's rule).

| Type | As specified | Heirs at 24% | Heirs at 32% |
|---|---|---|---|
| Diversified, modest unrealized gains | +1.66% | +1.87% | +2.04% |
| Concentrated single stock (40%+ of investable assets, low basis) | +1.91% | +2.08% | +2.18% |
| Large unrealized gains (brokerage basis under 40% of value) | +1.73% | +1.96% | +2.10% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | +1.37% | +1.55% | +1.63% |
| Large purchase within 3 years (25%+ of investable assets) | +1.63% | +1.84% | +2.01% |
| High earners with large pre-tax balances ($3M+ projected at 70) | +1.52% | +1.57% | +1.59% |
| **All 300 households** | **+1.63%** | **+1.79%** | **+1.91%** |


## Reading these numbers

* **Underfunded households.** 0 of 300 households have a median after-tax wealth at the horizon below the $50,000 floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: Diversified 1.6% for the plan vs 2.1% for the good RIA, Concentrated single stock 2.2% for the plan vs 3.3% for the good RIA, Large unrealized gains 0.9% for the plan vs 1.2% for the good RIA, Early retirement 0.9% for the plan vs 1.4% for the good RIA, Large purchase within 3 years 1.9% for the plan vs 1.3% for the good RIA, High earners with large pre-tax balances 2.8% for the plan vs 3.7% for the good RIA.
* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.
* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).

