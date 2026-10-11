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

A good traditional advisor: an age-based glide path from 80% to 50% stocks, the same mix in every account, breakpoint fees of 1.0% falling to 0.5%, fund-level loss harvesting in years stocks fall more than 10%, goals paid from the brokerage account, no Roth conversions and pro rata withdrawals.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +1.65% (+1.44% to +1.94%) | +0.34% (-0.21% to +0.73%) | 100% | 82% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.87% (+1.60% to +2.27%) | +0.58% (-0.17% to +1.14%) | 100% | 84% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.72% (+1.48% to +2.02%) | +0.43% (-0.29% to +0.84%) | 100% | 82% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +1.37% (+1.22% to +1.58%) | +0.89% (+0.50% to +1.47%) | 100% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.62% (+1.36% to +1.91%) | +0.40% (-0.69% to +0.79%) | 100% | 78% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +1.50% (+1.31% to +1.97%) | +0.16% (-1.75% to +0.58%) | 100% | 58% |
| **All 300 households** | 300 | **+1.62%** (+1.33% to +2.00%) | **+0.46%** (-0.48% to +1.12%) | 100% | 81% |

## Against the typical advisor

A typical advisor: a flat 1.0% fee at every balance, no tax-loss harvesting, every account managed separately with the same mix, an age-based glide path from 80% to 50% stocks, no Roth conversions and withdrawals taken proportionally.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +1.75% (+1.56% to +2.09%) | +0.41% (-0.05% to +0.81%) | 100% | 86% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +2.00% (+1.73% to +2.52%) | +0.65% (-0.02% to +1.18%) | 100% | 88% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.83% (+1.55% to +2.21%) | +0.48% (-0.21% to +0.89%) | 100% | 82% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +1.48% (+1.29% to +1.65%) | +0.93% (+0.62% to +1.51%) | 100% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.72% (+1.46% to +2.07%) | +0.46% (-0.62% to +0.82%) | 100% | 80% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +1.82% (+1.58% to +2.52%) | +0.38% (-1.31% to +0.77%) | 100% | 64% |
| **All 300 households** | 300 | **+1.76%** (+1.45% to +2.21%) | **+0.54%** (-0.26% to +1.14%) | 100% | 83% |

## What the planner chose, by type

Share of households of each type whose winning strategy uses each option.

| Type | Lowest stock share (50%) | Stock share 80%+ | Roth conversions | Private credit 15% | Direct indexing | Goal bonds | Roth 401(k) (any) | Borrow for goals |
|---|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 0% | 100% | 84% | 98% | 72% | 0% | 0% | 32% |
| Concentrated single stock (40%+ of investable assets, low basis) | 0% | 100% | 84% | 98% | 80% | 0% | 2% | 26% |
| Large unrealized gains (brokerage basis under 40% of value) | 0% | 100% | 70% | 100% | 70% | 0% | 0% | 20% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 100% | 16% | 54% | 26% | 0% | 0% | 0% |
| Large purchase within 3 years (25%+ of investable assets) | 0% | 100% | 88% | 96% | 58% | 0% | 0% | 46% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 0% | 100% | 96% | 94% | 90% | 0% | 0% | 34% |

Spending reserve chosen, by type (years of expenses held in bonds and private credit, everything else in stocks):

| Type | 2 years | 4 years | 6 years |
|---|---|---|---|
| Diversified, modest unrealized gains | 16% | 16% | 68% |
| Concentrated single stock (40%+ of investable assets, low basis) | 32% | 2% | 66% |
| Large unrealized gains (brokerage basis under 40% of value) | 16% | 6% | 78% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 0% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 20% | 12% | 68% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 30% | 10% | 60% |

## The adaptive planner: four strategies, by type

On 200 of each household's held-out futures (the same futures for all four strategies), the **typical advisor**, the **good RIA**, the **best fixed strategy** (the winner above) and the **adaptive planner** (the year-by-year planner of spec part B, K = 32 rollouts per candidate, each proposed change re-tested on 64 fresh futures; 4.8 seconds per household on average). Advantage cells are the median across the households of the type, with the 10th to 90th percentile across households. The 10th-percentile outcome and lifetime taxes are medians across households (real 2026 dollars, at the household's horizon; taxes are those paid over the plan plus tax owed on the pre-tax balance at the end).
With only 200 futures per household the risk-adjusted figure of a single household is noisy (it is decided by whether one or two futures run out of money), so read the medians across households, not any one household.

| Type | Strategy | Median advantage over the typical advisor | Risk-adjusted advantage over the typical advisor | Median advantage over the good RIA | Risk-adjusted advantage over the good RIA | 10th-percentile outcome | Lifetime taxes |
|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | Typical advisor | baseline | baseline | n/a | n/a | $657,337 | $1,424,106 |
|  | Good RIA | +0.12% (+0.06% to +0.20%) | +0.06% (+0.01% to +0.14%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $696,143 | $1,439,266 |
|  | Best fixed strategy | +1.77% (+1.51% to +2.10%) | +0.48% (-0.12% to +1.49%) | +1.67% (+1.38% to +1.97%) | +0.41% (-0.17% to +1.42%) | $998,046 | $1,427,797 |
|  | Adaptive planner | +1.81% (+1.58% to +2.13%) | +0.55% (-0.18% to +1.61%) | +1.72% (+1.46% to +2.01%) | +0.48% (-0.36% to +1.53%) | $1,056,137 | $1,333,480 |
| Concentrated single stock (40%+ of investable assets, low basis) | Typical advisor | baseline | baseline | n/a | n/a | $524,999 | $1,236,646 |
|  | Good RIA | +0.13% (+0.05% to +0.27%) | +0.06% (+0.03% to +0.19%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $533,468 | $1,245,952 |
|  | Best fixed strategy | +2.01% (+1.69% to +2.50%) | +0.69% (+0.10% to +1.24%) | +1.89% (+1.57% to +2.24%) | +0.62% (-0.11% to +1.18%) | $780,296 | $1,021,330 |
|  | Adaptive planner | +2.05% (+1.78% to +2.50%) | +0.74% (+0.19% to +1.33%) | +1.96% (+1.66% to +2.27%) | +0.67% (+0.05% to +1.29%) | $790,654 | $1,023,135 |
| Large unrealized gains (brokerage basis under 40% of value) | Typical advisor | baseline | baseline | n/a | n/a | $730,210 | $796,994 |
|  | Good RIA | +0.12% (+0.05% to +0.22%) | +0.06% (+0.02% to +0.19%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $741,165 | $803,527 |
|  | Best fixed strategy | +1.82% (+1.53% to +2.24%) | +0.79% (+0.20% to +1.35%) | +1.72% (+1.45% to +2.06%) | +0.74% (+0.06% to +1.15%) | $932,949 | $769,431 |
|  | Adaptive planner | +1.91% (+1.70% to +2.27%) | +0.94% (+0.23% to +1.38%) | +1.82% (+1.56% to +2.12%) | +0.86% (+0.07% to +1.24%) | $952,320 | $780,662 |
| Early retirement (55 to 58 now, several low-income years before Social Security) | Typical advisor | baseline | baseline | n/a | n/a | $449,614 | $277,758 |
|  | Good RIA | +0.08% (+0.01% to +0.15%) | +0.03% (+0.01% to +0.11%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $457,564 | $279,803 |
|  | Best fixed strategy | +1.54% (+1.22% to +1.74%) | +1.17% (+0.54% to +2.04%) | +1.48% (+1.16% to +1.67%) | +1.11% (+0.44% to +1.94%) | $541,241 | $290,333 |
|  | Adaptive planner | +1.69% (+1.40% to +1.90%) | +1.39% (+0.57% to +2.49%) | +1.61% (+1.34% to +1.83%) | +1.38% (+0.49% to +2.34%) | $568,133 | $294,610 |
| Large purchase within 3 years (25%+ of investable assets) | Typical advisor | baseline | baseline | n/a | n/a | $670,828 | $1,617,462 |
|  | Good RIA | +0.11% (+0.03% to +0.18%) | +0.06% (+0.01% to +0.18%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $686,738 | $1,639,324 |
|  | Best fixed strategy | +1.70% (+1.44% to +2.15%) | +0.60% (+0.00% to +0.97%) | +1.61% (+1.29% to +1.97%) | +0.57% (-0.05% to +0.92%) | $963,993 | $1,596,408 |
|  | Adaptive planner | +1.75% (+1.52% to +2.17%) | +0.69% (+0.04% to +1.03%) | +1.66% (+1.42% to +2.02%) | +0.65% (+0.01% to +0.95%) | $1,041,811 | $1,546,478 |
| High earners with large pre-tax balances ($3M+ projected at 70) | Typical advisor | baseline | baseline | n/a | n/a | $1,445,600 | $6,772,776 |
|  | Good RIA | +0.31% (+0.20% to +0.46%) | +0.26% (+0.11% to +0.46%) | +0.00% (+0.00% to +0.00%) | +0.00% (+0.00% to +0.00%) | $1,586,201 | $6,854,452 |
|  | Best fixed strategy | +1.78% (+1.56% to +2.42%) | +0.56% (-0.32% to +1.02%) | +1.49% (+1.28% to +1.84%) | +0.32% (-0.62% to +0.78%) | $2,161,811 | $7,058,407 |
|  | Adaptive planner | +1.78% (+1.59% to +2.42%) | +0.64% (-0.31% to +1.06%) | +1.51% (+1.29% to +1.84%) | +0.36% (-0.61% to +0.79%) | $2,161,050 | $7,060,077 |

## The value of judgment over time, by type

The adaptive planner against the best fixed strategy it continues, on the same futures: what choosing each year's decisions after seeing that year's returns adds.

| Type | Median advantage over the best fixed strategy | Risk-adjusted advantage over the best fixed strategy | Households where it is ahead (median / risk-adjusted) | Decision-years where it leaves the fixed strategy | Mostly changes |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | +0.04% (+0.00% to +0.18%) | +0.03% (+0.00% to +0.24%) | 92% / 96% | 19.4% | realize gains (10.5%) |
| Concentrated single stock (40%+ of investable assets, low basis) | +0.03% (+0.00% to +0.10%) | +0.02% (+0.00% to +0.26%) | 90% / 96% | 21.4% | realize gains (15.8%) |
| Large unrealized gains (brokerage basis under 40% of value) | +0.07% (+0.01% to +0.20%) | +0.06% (+0.00% to +0.21%) | 100% / 96% | 27.6% | realize gains (18.1%) |
| Early retirement (55 to 58 now, several low-income years before Social Security) | +0.15% (+0.06% to +0.27%) | +0.19% (+0.06% to +0.37%) | 96% / 98% | 42.8% | realize gains (31.7%) |
| Large purchase within 3 years (25%+ of investable assets) | +0.03% (+0.00% to +0.18%) | +0.03% (+0.00% to +0.20%) | 94% / 100% | 18.8% | realize gains (10.0%) |
| High earners with large pre-tax balances ($3M+ projected at 70) | +0.00% (-0.01% to +0.06%) | +0.00% (-0.00% to +0.09%) | 64% / 80% | 11.1% | conversion (10.4%) |
| **All 300 households** | +0.04% (+0.00% to +0.19%) | +0.04% (+0.00% to +0.26%) | 89% / 94% | 23.5% | realize gains (14.4%) |


## How much of the advantage is the tools, and how much is a different amount of equity

'Tools only' runs the plan's own choices (fee, asset location, conversions, withdrawal order, 401(k) type, goal funding, direct indexing) with the good RIA's allocation (80% stocks today falling to 50% from 70, no private credit), so it differs from the advisor in nothing else. The rest of the plan's advantage comes from its different stock share and private credit sleeve, which is a different amount of risk. Cells are medians across the households of the type; stocks are a share of the whole portfolio.

| Type | Plan: stocks today / from 70 | Plan: raw advantage | Tools only: raw advantage | From the allocation | Chance of running out: plan / tools only / good RIA |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 84% / 85% | +1.65% | +0.79% (+0.65% to +1.02%) | +0.81% | 1.7% / 1.1% / 2.2% |
| Concentrated single stock (40%+ of investable assets, low basis) | 84% / 85% | +1.87% | +0.82% (+0.66% to +1.09%) | +1.05% | 2.2% / 1.8% / 3.4% |
| Large unrealized gains (brokerage basis under 40% of value) | 85% / 85% | +1.72% | +0.80% (+0.67% to +0.97%) | +0.91% | 1.0% / 0.6% / 1.2% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 75% / 85% | +1.37% | +0.79% (+0.72% to +0.91%) | +0.61% | 0.9% / 0.9% / 1.4% |
| Large purchase within 3 years (25%+ of investable assets) | 85% / 85% | +1.62% | +0.83% (+0.60% to +1.03%) | +0.78% | 2.0% / 0.6% / 1.3% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 85% / 85% | +1.50% | +0.70% (+0.54% to +0.97%) | +0.81% | 2.9% / 2.1% / 3.7% |
| **All 300 households** | 84% / 85% | +1.62% | +0.79% (+0.64% to +1.02%) | +0.82% | 1.8% / 1.2% / 2.2% |


## If heirs paid a flat tax on pre-tax money at the horizon (sensitivity)

The app values a pre-tax balance at the horizon as if it were withdrawn evenly over 20 years beside Social Security, a low rate. A non-spouse heir must empty an inherited account within ten years. Median raw advantage over the good RIA with the balance taxed at a flat rate instead (median across the households of the type; the plan's choices are the ones the planner made under the app's rule).

| Type | As specified | Heirs at 24% | Heirs at 32% |
|---|---|---|---|
| Diversified, modest unrealized gains | +1.65% | +1.86% | +2.03% |
| Concentrated single stock (40%+ of investable assets, low basis) | +1.87% | +2.05% | +2.15% |
| Large unrealized gains (brokerage basis under 40% of value) | +1.72% | +1.95% | +2.09% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | +1.37% | +1.55% | +1.63% |
| Large purchase within 3 years (25%+ of investable assets) | +1.62% | +1.83% | +2.00% |
| High earners with large pre-tax balances ($3M+ projected at 70) | +1.50% | +1.55% | +1.57% |
| **All 300 households** | **+1.62%** | **+1.76%** | **+1.86%** |


## Reading these numbers

* **Underfunded households.** 0 of 300 households have a median after-tax wealth at the horizon below the $50,000 floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: Diversified 1.7% for the plan vs 2.2% for the good RIA, Concentrated single stock 2.2% for the plan vs 3.4% for the good RIA, Large unrealized gains 1.0% for the plan vs 1.2% for the good RIA, Early retirement 0.9% for the plan vs 1.4% for the good RIA, Large purchase within 3 years 2.0% for the plan vs 1.3% for the good RIA, High earners with large pre-tax balances 2.9% for the plan vs 3.7% for the good RIA.
* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.
* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).

