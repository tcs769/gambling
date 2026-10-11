# Sensitivity of the sample household to the corrected A8 assumptions

**Analysis only: the app still uses the assumptions as specified.** Each row repeats the whole search on the
sample household with the correction applied, then scores the winner on 2,000 futures the search never saw,
against the good RIA, on the same futures as every other row (the corrections change the world the plan is
simulated in; the baseline lives in the same world). See `reports/assumption_review.md` for the evidence.

| Scenario | What changes | Recommendation (seed 2026) | Median advantage | Risk-adjusted advantage | Mean of 5 seeds (median / risk-adj.) |
|---|---|---|---|---|---|
| As specified | Every assumption as in the app today. | 50% stocks, fill 24% bracket (every year), 15% private credit | +0.27%/yr | +2.54%/yr | +0.35% / +2.62% |
| Direct indexing: evidence-based harvest | Harvest = min(35% of value, basis, 0.85 b0^3 x decline + 0.14 x value x b1^14), b = basis/value, plus a 0.20% a year fee premium on direct-indexed equity. | 50% stocks, fill 24% bracket (every year), 15% private credit | +0.27%/yr | +2.54%/yr | +0.35% / +2.62% |
| Direct indexing: evidence-based harvest, no fee premium | The same harvest rule alone. | 50% stocks, fill 24% bracket (every year), 15% private credit | +0.27%/yr | +2.54%/yr | +0.35% / +2.62% |
| Direct indexing forced on, as specified | The planner must use direct indexing (the sample household's winner does not use it once conversions are allowed, so the rows above cannot show what the assumption is worth). | 50% stocks, fill 24% bracket (every year), 15% private credit, direct indexing | +0.27%/yr | +2.54%/yr | +0.30% / +2.72% |
| Direct indexing forced on, evidence-based harvest and fee premium | The same, with the evidence-based harvest rule and the 0.20% fee premium. | 50% stocks, fill 24% bracket (every year), 15% private credit, direct indexing | +0.27%/yr | +2.54%/yr | +0.30% / +2.72% |
| Private credit: 2.5% real return | Return 1 point lower (the low end of the plausible 2-5% range); volatility and correlations as specified. | 50% stocks, fill 24% bracket (every year), 15% private credit | +0.11%/yr | +2.25%/yr | +0.20% / +2.22% |
| Private credit: 12% volatility, 0.7 correlation with stocks | The proposed values for levered or semi-liquid retail vehicles. | 50% stocks, fill 24% bracket (every year), 15% private credit, goal bonds | +0.21%/yr | +1.61%/yr | +0.27% / +1.92% |
| Private credit: equity-linked stress tails | Calm years N(4.9%, 6%); in a year stocks fall more than 1.28 standard deviations below their mean (about 1 in 10) private credit is N(-10%, 10%). Overall mean about 3.4%, volatility about 8%. | 50% stocks, fill 24% bracket (every year), 15% private credit | +0.29%/yr | +2.36%/yr | +0.40% / +2.47% |
| Both proposals together | Evidence-based harvest with the fee premium, and private credit with equity-linked stress tails. | 50% stocks, fill 24% bracket (every year), 15% private credit | +0.29%/yr | +2.36%/yr | +0.36% / +2.69% |
| Both proposals, lower and riskier private credit | Evidence-based harvest with the fee premium, and private credit at 2.5% return, 12% volatility, 0.7 correlation. | 50% stocks, fill 24% bracket (every year), 5% private credit | +0.14%/yr | +1.37%/yr | +0.23% / +1.83% |
| No private credit allowed | The planner may not hold any private credit (sleeve fixed at 0%); everything else as specified. | 50% stocks, no conversions, direct indexing | -0.09%/yr | +1.51%/yr | +0.14% / +1.99% |
