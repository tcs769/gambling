# Sample household: recommendation and annualized advantage after each change

The sample household is the fictional demo household (two earners aged 38 and 37, $250,000 of wages,
$620,000 invested). For each step the planner searches its whole strategy menu on 400 simulated
futures (seed 2026, the app's defaults) and the winner is scored against the good-RIA baseline.

* **Median advantage**: the difference in median after-tax wealth at the horizon, annualized as a
  growth-rate difference, `(plan / baseline)^(1/years) - 1`.
* **Risk-adjusted advantage**: the same, using certainty-equivalent wealth (CRRA utility, risk
  aversion 3, $50,000 floor), the planner's own objective.
* The headline figures are measured on **held-out futures** (2,000 paths the search never saw), so
  picking the best of many strategies is not scored on the futures it was picked on. The in-sample
  figures (what the app showed before the review) are listed for comparison. "Mean of 5 seeds" repeats
  the whole search-then-score on seeds 2026 to 2030.
* Every step is one change; nothing is tuned toward a target. Rows are cumulative.


## Against the good RIA

| Step | Years | Recommendation (seed 2026) | Median adv. | Risk-adj. adv. | Mean of 5 seeds (median / risk-adj.) | In-sample (median / risk-adj.) | Chance of a shortfall: plan / baseline |
|---|---|---|---|---|---|---|---|
| Step 0: engine as shipped (horizon 70) | 32 | 70% stocks, no conversions, private credit, direct indexing | +0.62% | +0.86% | +0.61% / +0.78% | +0.62% / +0.76% | not recorded |
| A1: horizon 80, RMDs, 65+ deduction | 42 | 70% stocks, no conversions, private credit, direct indexing | +0.61% | +0.89% | +0.63% / +1.17% | +0.66% / +2.78% | not recorded |
| A2: stock-share menu 50-100% | 42 | 50% stocks, no conversions, private credit, direct indexing | -0.03% | +2.32% | +0.07% / +2.42% | +0.02% / +3.32% | not recorded |
| A3: private credit sleeve 0/5/10/15% | 42 | 50% stocks, no conversions, 15% private credit, direct indexing | -0.00% | +2.50% | +0.16% / +2.63% | +0.05% / +3.45% | not recorded |
| A4: conversion tax from cash, wages and brokerage | 42 | 50% stocks, fill 24% bracket (every year), 15% private credit | +0.27% | +2.54% | +0.30% / +2.73% | +0.34% / +3.61% | not recorded |
| A5: Roth vs pre-tax 401(k) | 42 | 50% stocks, fill 24% bracket (every year), 15% private credit | +0.27% | +2.54% | +0.30% / +2.73% | +0.34% / +3.61% | not recorded |
| A6: borrow against the portfolio for goals | 42 | 50% stocks, fill 24% bracket (every year), 15% private credit | +0.27% | +2.54% | +0.35% / +2.62% | +0.34% / +3.61% | not recorded |
| A7+A9: two measures, typical-advisor baseline, held-out evaluation | 42 | 50% stocks, fill 24% bracket (every year), 15% private credit | +0.27% | +2.54% | +0.35% / +2.62% | +0.34% / +3.61% | 0.1% / 0.6% |
| A11: spending reserve, equity-first planning style (the default) | 42 | 6-year spending reserve, the rest in stocks, fill 24% bracket (every year), 15% private credit | +1.61% | +0.14% | +1.66% / +0.04% | +1.67% / +0.10% | 0.8% / 0.6% |

## Against the typical advisor

| Step | Years | Recommendation (seed 2026) | Median adv. | Risk-adj. adv. | Mean of 5 seeds (median / risk-adj.) | In-sample (median / risk-adj.) | Chance of a shortfall: plan / baseline |
|---|---|---|---|---|---|---|---|
| A7+A9: two measures, typical-advisor baseline, held-out evaluation | 42 | 50% stocks, fill 24% bracket (every year), 15% private credit | +0.40% | +2.60% | +0.48% / +2.71% | +0.47% / +3.74% | 0.1% / 0.7% |
| A11: spending reserve, equity-first planning style (the default) | 42 | 6-year spending reserve, the rest in stocks, fill 24% bracket (every year), 15% private credit | +1.74% | +0.20% | +1.80% / +0.12% | +1.80% / +0.22% | 0.8% / 0.7% |

