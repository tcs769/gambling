# Household-type study

300 synthetic households (50 of each of six types), all fictional. For each, the planner searched
its strategy menu on 400 simulated futures and the winner was scored against both advisors on 1,000 fresh
futures it never saw (the planner searched at risk aversion 2; risk-adjusted figures are at risk aversion 3). Nothing was tuned; the households were drawn from fixed ranges
that make each a clear example of its type (see `backend/app/study/households.py`).

* **Median advantage**: difference in median after-tax wealth at the horizon, annualized as a growth-rate difference.
* **Risk-adjusted advantage**: the same on certainty-equivalent wealth (the planner's objective).
* Each cell is the **median across the households of that type** (with the 10th to 90th percentile across households).
  Dollar-weighted or pooled figures would differ; this is the typical household of the type.

## Against the good ria

A good traditional advisor: an age-based glide path from 80% to 50% stocks, the same mix in every account, breakpoint fees of 1.0% falling to 0.5%, fund-level loss harvesting in years stocks fall more than 10%, goals paid from the brokerage account, no Roth conversions and pro rata withdrawals.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +0.91% (+0.10% to +1.33%) | +1.39% (+0.70% to +2.34%) | 100% | 96% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.19% (+0.42% to +1.70%) | +1.25% (+0.69% to +2.33%) | 96% | 96% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.16% (+0.06% to +1.56%) | +1.26% (+0.61% to +2.90%) | 96% | 98% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +0.46% (+0.01% to +1.14%) | +2.46% (+0.95% to +3.70%) | 92% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.03% (+0.39% to +1.46%) | +1.05% (+0.33% to +2.50%) | 100% | 96% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +0.80% (+0.01% to +1.14%) | +1.42% (+0.56% to +2.80%) | 92% | 98% |
| **All 300 households** | 300 | **+0.94%** (+0.09% to +1.46%) | **+1.46%** (+0.54% to +3.01%) | 96% | 97% |

## Against the typical advisor

A typical advisor: a flat 1.0% fee at every balance, no tax-loss harvesting, every account managed separately with the same mix, an age-based glide path from 80% to 50% stocks, no Roth conversions and withdrawals taken proportionally.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +1.04% (+0.27% to +1.44%) | +1.50% (+0.81% to +2.47%) | 100% | 96% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.35% (+0.58% to +1.79%) | +1.35% (+0.72% to +2.40%) | 98% | 96% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.21% (+0.33% to +1.63%) | +1.30% (+0.69% to +2.99%) | 100% | 98% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +0.58% (+0.14% to +1.22%) | +2.49% (+1.01% to +3.76%) | 96% | 100% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.13% (+0.55% to +1.56%) | +1.13% (+0.45% to +2.58%) | 100% | 96% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +1.15% (+0.41% to +1.47%) | +1.77% (+0.80% to +3.19%) | 100% | 100% |
| **All 300 households** | 300 | **+1.12%** (+0.33% to +1.58%) | **+1.57%** (+0.69% to +3.07%) | 99% | 98% |

## What the planner chose, by type

Share of households of each type whose winning strategy uses each option.

| Type | Lowest stock share (50%) | Stock share 80%+ | Roth conversions | Private credit 15% | Direct indexing | Goal bonds | Roth 401(k) (any) | Borrow for goals |
|---|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 18% | 46% | 86% | 100% | 94% | 14% | 0% | 28% |
| Concentrated single stock (40%+ of investable assets, low basis) | 4% | 62% | 94% | 100% | 100% | 14% | 0% | 16% |
| Large unrealized gains (brokerage basis under 40% of value) | 12% | 64% | 74% | 100% | 98% | 16% | 0% | 10% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 28% | 36% | 22% | 100% | 44% | 0% | 0% | 0% |
| Large purchase within 3 years (25%+ of investable assets) | 12% | 54% | 90% | 100% | 92% | 18% | 0% | 62% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 22% | 48% | 96% | 100% | 100% | 14% | 0% | 20% |

## How much of the advantage is the tools, and how much is a different amount of equity

'Tools only' runs the plan's own choices (fee, asset location, conversions, withdrawal order, 401(k) type, goal funding, direct indexing) with the good RIA's allocation (80% stocks today falling to 50% from 70, no private credit), so it differs from the advisor in nothing else. The rest of the plan's advantage comes from its different stock share and private credit sleeve, which is a different amount of risk. Cells are medians across the households of the type; stocks are a share of the whole portfolio.

| Type | Plan: stocks today / from 70 | Plan: raw advantage | Tools only: raw advantage | From the allocation | Chance of running out: plan / tools only / good RIA |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 60% / 38% | +0.91% | +0.77% (+0.69% to +1.00%) | +0.02% | 0.6% / 1.0% / 2.2% |
| Concentrated single stock (40%+ of investable assets, low basis) | 68% / 47% | +1.19% | +0.86% (+0.72% to +1.11%) | +0.29% | 1.3% / 1.7% / 3.4% |
| Large unrealized gains (brokerage basis under 40% of value) | 68% / 47% | +1.16% | +0.82% (+0.70% to +0.95%) | +0.30% | 0.3% / 0.6% / 1.2% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 51% / 30% | +0.46% | +0.80% (+0.72% to +0.93%) | -0.39% | 0.2% / 0.9% / 1.4% |
| Large purchase within 3 years (25%+ of investable assets) | 68% / 47% | +1.03% | +0.82% (+0.64% to +0.99%) | +0.22% | 0.7% / 0.9% / 1.3% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 60% / 38% | +0.80% | +0.70% (+0.58% to +0.97%) | +0.03% | 1.5% / 2.1% / 3.7% |
| **All 300 households** | 68% / 47% | +0.94% | +0.80% (+0.65% to +0.99%) | +0.12% | 0.8% / 1.2% / 2.2% |


## If heirs paid a flat tax on pre-tax money at the horizon (sensitivity)

The app values a pre-tax balance at the horizon as if it were withdrawn evenly over 20 years beside Social Security, a low rate. A non-spouse heir must empty an inherited account within ten years. Median raw advantage over the good RIA with the balance taxed at a flat rate instead (median across the households of the type; the plan's choices are the ones the planner made under the app's rule).

| Type | As specified | Heirs at 24% | Heirs at 32% |
|---|---|---|---|
| Diversified, modest unrealized gains | +0.91% | +1.10% | +1.20% |
| Concentrated single stock (40%+ of investable assets, low basis) | +1.19% | +1.34% | +1.47% |
| Large unrealized gains (brokerage basis under 40% of value) | +1.16% | +1.37% | +1.48% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | +0.46% | +0.82% | +0.91% |
| Large purchase within 3 years (25%+ of investable assets) | +1.03% | +1.23% | +1.41% |
| High earners with large pre-tax balances ($3M+ projected at 70) | +0.80% | +0.83% | +0.88% |
| **All 300 households** | **+0.94%** | **+1.06%** | **+1.15%** |


## Reading these numbers

* **Underfunded households.** 0 of 300 households have a median after-tax wealth at the horizon below the $50,000 floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: Diversified 0.6% for the plan vs 2.2% for the good RIA, Concentrated single stock 1.3% for the plan vs 3.4% for the good RIA, Large unrealized gains 0.3% for the plan vs 1.2% for the good RIA, Early retirement 0.2% for the plan vs 1.4% for the good RIA, Large purchase within 3 years 0.7% for the plan vs 1.3% for the good RIA, High earners with large pre-tax balances 1.5% for the plan vs 3.7% for the good RIA.
* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.
* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).

