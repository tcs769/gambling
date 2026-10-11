# Household-type study

300 synthetic households (50 of each of six types), all fictional. For each, the planner searched
its strategy menu on 400 simulated futures and the winner was scored against both advisors on 1,000 fresh
futures it never saw (the planner searched at risk aversion 1; risk-adjusted figures are at risk aversion 3). Nothing was tuned; the households were drawn from fixed ranges
that make each a clear example of its type (see `backend/app/study/households.py`).

* **Median advantage**: difference in median after-tax wealth at the horizon, annualized as a growth-rate difference.
* **Risk-adjusted advantage**: the same on certainty-equivalent wealth (the planner's objective).
* Each cell is the **median across the households of that type** (with the 10th to 90th percentile across households).
  Dollar-weighted or pooled figures would differ; this is the typical household of the type.

## Against the good ria

A good traditional advisor: an age-based glide path from 80% to 50% stocks, the same mix in every account, breakpoint fees of 1.0% falling to 0.5%, fund-level loss harvesting in years stocks fall more than 10%, goals paid from the brokerage account, no Roth conversions and pro rata withdrawals.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +1.57% (+1.39% to +1.90%) | +0.38% (-0.52% to +0.67%) | 100% | 72% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.72% (+1.52% to +2.15%) | +0.61% (-0.18% to +0.95%) | 100% | 86% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.58% (+1.37% to +1.85%) | +0.46% (-0.27% to +0.87%) | 100% | 78% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +1.39% (+1.25% to +1.54%) | +0.28% (-0.05% to +0.59%) | 100% | 88% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.55% (+1.29% to +1.85%) | +0.33% (-0.96% to +0.72%) | 100% | 70% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +1.38% (+1.19% to +1.83%) | +0.23% (-1.98% to +0.68%) | 100% | 66% |
| **All 300 households** | 300 | **+1.54%** (+1.28% to +1.89%) | **+0.38%** (-0.58% to +0.77%) | 100% | 77% |

## Against the typical advisor

A typical advisor: a flat 1.0% fee at every balance, no tax-loss harvesting, every account managed separately with the same mix, an age-based glide path from 80% to 50% stocks, no Roth conversions and withdrawals taken proportionally.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +1.72% (+1.50% to +2.05%) | +0.41% (-0.42% to +0.72%) | 100% | 76% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.87% (+1.63% to +2.35%) | +0.70% (-0.04% to +0.99%) | 100% | 88% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.70% (+1.52% to +1.99%) | +0.53% (-0.09% to +0.96%) | 100% | 86% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +1.48% (+1.32% to +1.66%) | +0.31% (-0.02% to +0.63%) | 100% | 88% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.65% (+1.42% to +1.96%) | +0.38% (-0.77% to +0.76%) | 100% | 72% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +1.66% (+1.46% to +2.36%) | +0.39% (-1.60% to +0.95%) | 100% | 70% |
| **All 300 households** | 300 | **+1.68%** (+1.43% to +2.07%) | **+0.44%** (-0.42% to +0.90%) | 100% | 80% |

## What the planner chose, by type

Share of households of each type whose winning strategy uses each option.

| Type | Lowest stock share (50%) | Stock share 80%+ | Roth conversions | Private credit 15% | Direct indexing | Goal bonds | Roth 401(k) (any) | Borrow for goals |
|---|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 0% | 100% | 96% | 62% | 100% | 0% | 0% | 42% |
| Concentrated single stock (40%+ of investable assets, low basis) | 0% | 100% | 100% | 72% | 100% | 0% | 0% | 14% |
| Large unrealized gains (brokerage basis under 40% of value) | 0% | 100% | 92% | 72% | 100% | 0% | 0% | 24% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 100% | 40% | 90% | 70% | 0% | 2% | 0% |
| Large purchase within 3 years (25%+ of investable assets) | 0% | 100% | 98% | 46% | 100% | 2% | 0% | 98% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 0% | 100% | 100% | 70% | 100% | 0% | 0% | 2% |

## How much of the advantage is the tools, and how much is a different amount of equity

'Tools only' runs the plan's own choices (fee, asset location, conversions, withdrawal order, 401(k) type, goal funding, direct indexing) with the good RIA's allocation (80% stocks today falling to 50% from 70, no private credit), so it differs from the advisor in nothing else. The rest of the plan's advantage comes from its different stock share and private credit sleeve, which is a different amount of risk. Cells are medians across the households of the type; stocks are a share of the whole portfolio.

| Type | Plan: stocks today / from 70 | Plan: raw advantage | Tools only: raw advantage | From the allocation | Chance of running out: plan / tools only / good RIA |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 85% / 64% | +1.57% | +0.83% (+0.71% to +1.02%) | +0.77% | 1.6% / 1.1% / 2.2% |
| Concentrated single stock (40%+ of investable assets, low basis) | 85% / 64% | +1.72% | +0.86% (+0.71% to +1.03%) | +0.88% | 2.2% / 1.9% / 3.4% |
| Large unrealized gains (brokerage basis under 40% of value) | 85% / 64% | +1.58% | +0.81% (+0.68% to +0.97%) | +0.76% | 0.9% / 0.7% / 1.2% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 85% / 64% | +1.39% | +0.80% (+0.71% to +0.93%) | +0.58% | 1.4% / 0.9% / 1.4% |
| Large purchase within 3 years (25%+ of investable assets) | 90% / 68% | +1.55% | +0.83% (+0.65% to +1.04%) | +0.71% | 2.7% / 2.3% / 1.3% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 85% / 64% | +1.38% | +0.70% (+0.57% to +0.97%) | +0.67% | 2.6% / 2.1% / 3.7% |
| **All 300 households** | 85% / 64% | +1.54% | +0.81% (+0.65% to +1.01%) | +0.73% | 1.9% / 1.5% / 2.2% |


## If heirs paid a flat tax on pre-tax money at the horizon (sensitivity)

The app values a pre-tax balance at the horizon as if it were withdrawn evenly over 20 years beside Social Security, a low rate. A non-spouse heir must empty an inherited account within ten years. Median raw advantage over the good RIA with the balance taxed at a flat rate instead (median across the households of the type; the plan's choices are the ones the planner made under the app's rule).

| Type | As specified | Heirs at 24% | Heirs at 32% |
|---|---|---|---|
| Diversified, modest unrealized gains | +1.57% | +1.78% | +1.94% |
| Concentrated single stock (40%+ of investable assets, low basis) | +1.72% | +1.92% | +2.05% |
| Large unrealized gains (brokerage basis under 40% of value) | +1.58% | +1.81% | +1.99% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | +1.39% | +1.61% | +1.77% |
| Large purchase within 3 years (25%+ of investable assets) | +1.55% | +1.80% | +1.99% |
| High earners with large pre-tax balances ($3M+ projected at 70) | +1.38% | +1.43% | +1.47% |
| **All 300 households** | **+1.54%** | **+1.75%** | **+1.90%** |


## Reading these numbers

* **Underfunded households.** 0 of 300 households have a median after-tax wealth at the horizon below the $50,000 floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: Diversified 1.6% for the plan vs 2.2% for the good RIA, Concentrated single stock 2.2% for the plan vs 3.4% for the good RIA, Large unrealized gains 0.9% for the plan vs 1.2% for the good RIA, Early retirement 1.4% for the plan vs 1.4% for the good RIA, Large purchase within 3 years 2.7% for the plan vs 1.3% for the good RIA, High earners with large pre-tax balances 2.6% for the plan vs 3.7% for the good RIA.
* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.
* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).

