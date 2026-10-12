# Demo script: Tanaka, the advisor, Donabach, and two live changes (2 to 2½ minutes)

Numbers below are what the engine produces today (liability-matched plan, 2,000 simulated futures, 2026 dollars, liquidated at 80),
and they are the same on every take. Say "adapts" or "re-plans", not "predicts": the income forecast model is not connected.

| Time | Screen | Say | What the screen shows |
|---|---|---|---|
| 0:00 | Household card | "One earner, 50, a child of 10, earning $204,000, with $1.2 million saved, more than half of it in a taxable account with large unrealized gains." | $204,268 income, $1,193,283 saved: 54% taxable ($645,777), 36% pre-tax, 8% Roth, 2% cash |
| 0:15 | Wealth, advisor only | "Here is what a good advisor typically gets them: an age-based portfolio, standard fees, accounts managed separately. $1.30 million at 80 for the typical future, $280,000 in a bad market." | Advisor lines only: median $1,297,356, bad case (10th percentile) $280,009, chance of running out of money 3.9% |
| 0:40 | Press "See what Donabach does" → waterfall | "Donabach starts from the same household and adds private-bank tools. Each one adds this much a year: the lower fee 0.76 points, asset location 0.24, lot-level tax management 0.09, a spending reserve 0.56, private credit 0.20, Roth conversions 0.18." | Bars added one at a time; total +2.05% a year (+$1.09 million at 80) |
| 1:15 | Wealth, both lines | "Together, about 2% a year for this household: $2.38 million against $1.30 million, and the bad case is better too: $396,000 against $280,000." | Both lines; median advantage +2.05%, risk-adjusted +0.60% |
| 1:30 | "Change the household" → Job loss | "Say Tanaka loses their job next year, a year without pay. Watch the plan." | Year-51 Roth conversion $244,000 (it was $62,000), gains realized in the 0% bracket, advantage after the event +1.98% a year |
| 2:00 | Market drops 30% | "Or stocks fall 30% next year." | The plan's years that changed are highlighted; after the drop Donabach $1.07 million vs advisor $0.78 million, bad case $84,000 vs −$26,000 |
| 2:15 | Close | "Better tools, better judgment, for every household. We're raising a seed round." | |

## Things to get right (from what the engine measured)

* **The headline is +2.05% a year, not 2.2%.** 2.2% was the showcase household before the Update 4 audit; the engine now says 2.05% (equity-first 2.10%).
  Say "about 2%". Risk-adjusted it is +0.60%; the typical household of the 300 sees about 1.7%.
* **Job loss** (a year without wages, no unemployment insurance or severance modeled): the plan responds by converting far more to Roth in the
  year with no income ($244,000 against $62,000), which is the story you want. Donabach's advantage over the advisor in that world: +1.98% a year.
* **Market drop** is less flattering and you should know it before filming. The same 30% fall in every simulated future makes the plan's own
  liquidity rule (stock sales in falling years at most 2% of futures) bind, so planning again picks a 9-year reserve and a more cautious plan.
  Donabach's advantage over the advisor falls to **+1.08% a year** (risk-adjusted +0.58%), and planning again costs about 0.66 points a year of
  median wealth against keeping the original plan on those futures; in exchange the chance of running out of money is 7.0% against the advisor's
  11.3%. In the highlighted years the plan converts *less* to Roth after the fall (balances are lower), not more. Do not say "converts more while
  balances are low" on this scenario: the screen will show the opposite. A truthful line: "The plan gets more cautious: a bigger reserve and fewer
  conversions, and it still ends ahead of the advisor and with a better bad case."
* If you want a market-drop story with a larger advantage, that is a modeling choice (an unconstrained equity-first plan), not a presentation
  choice, and it would be a different plan than the one the rest of the demo shows.
* Take several takes. Everything is precomputed in demo mode, so the numbers are identical every run.
