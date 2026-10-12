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
| Diversified, modest unrealized gains | 50 | +1.80% (+1.54% to +2.01%) | +0.35% (-0.30% to +0.68%) | 100% | 82% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.96% (+1.69% to +2.21%) | +0.49% (+0.12% to +1.10%) | 100% | 94% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.93% (+1.61% to +2.32%) | +0.44% (-0.42% to +0.87%) | 100% | 74% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +1.27% (+0.90% to +1.69%) | +0.84% (-0.01% to +2.01%) | 100% | 90% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +1.47% (+1.08% to +1.81%) | +0.38% (-0.57% to +0.91%) | 100% | 78% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +1.32% (+1.08% to +1.60%) | -0.10% (-1.12% to +0.48%) | 100% | 44% |
| **All 300 households** | 300 | **+1.67%** (+1.11% to +2.10%) | **+0.41%** (-0.45% to +1.18%) | 100% | 77% |

## Against the typical advisor

A typical advisor: a fee of 1.15% on the first $500,000 falling to 0.6% above $5 million, funds that charge 0.60% (stocks) and 0.45% (bonds) a year, 3% in cash, no tax-loss harvesting, every account managed separately with the same mix, an age-based glide path from 80% to 50% stocks, no Roth conversions, withdrawals taken proportionally and the oldest tax lots sold first. Its taxable funds are actively managed, so they pay out capital gains every year.

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +2.58% (+2.32% to +3.00%) | +1.36% (+0.76% to +1.96%) | 100% | 100% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +2.94% (+2.53% to +3.35%) | +1.72% (+1.06% to +2.88%) | 100% | 100% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +2.74% (+2.34% to +3.17%) | +1.35% (+0.78% to +2.29%) | 100% | 98% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +2.13% (+1.74% to +2.51%) | +1.89% (+1.10% to +3.13%) | 100% | 98% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +2.13% (+1.84% to +2.63%) | +1.19% (+0.63% to +1.98%) | 100% | 96% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +2.19% (+2.00% to +2.68%) | +1.05% (+0.54% to +2.14%) | 100% | 96% |
| **All 300 households** | 300 | **+2.46%** (+1.91% to +3.12%) | **+1.46%** (+0.72% to +2.54%) | 100% | 98% |

## Against the do it yourself

Doing it yourself: the same age-based glide path in index funds with no advisory fee, no loss harvesting, no conversions, withdrawals taken proportionally and the oldest tax lots sold first, and the behavior gap the average investor shows (about half a point a year less than the funds earn).

| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 50 | +1.18% (+0.96% to +1.33%) | -0.48% (-1.43% to -0.07%) | 100% | 2% |
| Concentrated single stock (40%+ of investable assets, low basis) | 50 | +1.28% (+1.00% to +1.46%) | -0.34% (-1.06% to +0.22%) | 100% | 24% |
| Large unrealized gains (brokerage basis under 40% of value) | 50 | +1.30% (+0.99% to +1.63%) | -0.38% (-1.53% to +0.17%) | 100% | 22% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 50 | +0.54% (+0.15% to +1.03%) | +0.02% (-0.81% to +1.20%) | 94% | 52% |
| Large purchase within 3 years (25%+ of investable assets) | 50 | +0.84% (+0.52% to +1.17%) | -0.38% (-1.42% to +0.06%) | 100% | 14% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 50 | +0.88% (+0.51% to +1.09%) | -0.97% (-2.20% to -0.33%) | 96% | 0% |
| **All 300 households** | 300 | **+1.07%** (+0.49% to +1.38%) | **-0.39%** (-1.53% to +0.20%) | 98% | 19% |

## What the planner chose, by type

Share of households of each type whose winning strategy uses each option.

| Type | Lowest stock share (50%) | Stock share 80%+ | Roth conversions | Private credit 15% | Direct indexing | Goal bonds | Roth 401(k) (any) | Borrow for goals |
|---|---|---|---|---|---|---|---|---|
| Diversified, modest unrealized gains | 0% | 100% | 96% | 84% | 56% | 0% | 2% | 60% |
| Concentrated single stock (40%+ of investable assets, low basis) | 0% | 100% | 100% | 88% | 38% | 0% | 14% | 30% |
| Large unrealized gains (brokerage basis under 40% of value) | 0% | 100% | 96% | 78% | 54% | 0% | 10% | 16% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 100% | 68% | 78% | 42% | 0% | 12% | 0% |
| Large purchase within 3 years (25%+ of investable assets) | 0% | 100% | 62% | 58% | 30% | 0% | 10% | 90% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 0% | 100% | 74% | 60% | 28% | 0% | 44% | 52% |

Spending reserve chosen, by type (years of expenses held in bonds and private credit, everything else in stocks):

| Type | 2 years | 4 years | 6 years |
|---|---|---|---|
| Diversified, modest unrealized gains | 2% | 6% | 32% |
| Concentrated single stock (40%+ of investable assets, low basis) | 2% | 2% | 16% |
| Large unrealized gains (brokerage basis under 40% of value) | 10% | 4% | 20% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | 0% | 0% | 8% |
| Large purchase within 3 years (25%+ of investable assets) | 4% | 0% | 8% |
| High earners with large pre-tax balances ($3M+ projected at 70) | 2% | 2% | 10% |

## The two valuations at 80, against both advisors

**Liquidated at 80**: everything is sold and taxed at the horizon. **Passed to heirs at 80**: a step-up in basis on the taxable account (no tax on its unrealized gain), the Roth as it stands, the pre-tax accounts after a flat 24% tax. Each cell is the median across the households of the type: the raw (median) advantage, then the risk-adjusted advantage. The plan was chosen under the liquidated valuation. 

| Type | Against | Liquidated: median | Liquidated: risk-adjusted | Heirs: median | Heirs: risk-adjusted |
|---|---|---|---|---|---|
| Diversified, modest unrealized gains | Good RIA | +1.80% | +0.35% | +1.88% | +0.47% |
|  | Typical advisor (its funds pay distributions) | +2.58% | +1.36% | +2.75% | +1.49% |
|  | Typical advisor without distributions | +2.54% | +1.28% | +2.65% | +1.39% |
| Concentrated single stock (40%+ of investable assets, low basis) | Good RIA | +1.96% | +0.49% | +2.11% | +0.63% |
|  | Typical advisor (its funds pay distributions) | +2.94% | +1.72% | +3.13% | +1.88% |
|  | Typical advisor without distributions | +2.81% | +1.51% | +2.96% | +1.62% |
| Large unrealized gains (brokerage basis under 40% of value) | Good RIA | +1.93% | +0.44% | +2.02% | +0.56% |
|  | Typical advisor (its funds pay distributions) | +2.74% | +1.35% | +2.94% | +1.55% |
|  | Typical advisor without distributions | +2.64% | +1.19% | +2.79% | +1.43% |
| Early retirement (55 to 58 now, several low-income years before Social Security) | Good RIA | +1.27% | +0.84% | +1.45% | +1.21% |
|  | Typical advisor (its funds pay distributions) | +2.13% | +1.89% | +2.36% | +2.19% |
|  | Typical advisor without distributions | +2.10% | +1.89% | +2.33% | +2.16% |
| Large purchase within 3 years (25%+ of investable assets) | Good RIA | +1.47% | +0.38% | +1.57% | +0.49% |
|  | Typical advisor (its funds pay distributions) | +2.13% | +1.19% | +2.27% | +1.28% |
|  | Typical advisor without distributions | +2.09% | +1.10% | +2.20% | +1.20% |
| High earners with large pre-tax balances ($3M+ projected at 70) | Good RIA | +1.32% | -0.10% | +1.45% | +0.02% |
|  | Typical advisor (its funds pay distributions) | +2.19% | +1.05% | +2.38% | +1.12% |
|  | Typical advisor without distributions | +2.08% | +0.85% | +2.23% | +0.94% |
| **All 300 households** | Good RIA | +1.67% | +0.41% | +1.75% | +0.52% |
|  | Typical advisor (its funds pay distributions) | +2.46% | +1.46% | +2.67% | +1.62% |
|  | Typical advisor without distributions | +2.40% | +1.34% | +2.55% | +1.47% |


## Reading these numbers

* **Underfunded households.** 0 of 300 households have a median after-tax wealth at the horizon below the $50,000 floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: Diversified 1.2% for the plan vs 1.7% for the good RIA, Concentrated single stock 1.9% for the plan vs 2.6% for the good RIA, Large unrealized gains 0.7% for the plan vs 0.9% for the good RIA, Early retirement 0.5% for the plan vs 1.1% for the good RIA, Large purchase within 3 years 0.8% for the plan vs 1.1% for the good RIA, High earners with large pre-tax balances 3.3% for the plan vs 3.0% for the good RIA.
* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.
* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).

