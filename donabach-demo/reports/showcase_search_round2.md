# Showcase household search, round 2 (feasibility as a hard constraint)

Only the household varied. Engine and assumptions unchanged; direct indexing is charged its transition tax (funds sold, tax paid, basis reset).

Three separate sets of futures (`backend/app/study/showcase_final.py`):
- search: 300 futures for the quick scores and the climb (seed offset 4,000,039), plus the planner's own search (400) and validation (1,200) futures;
- finalist: 2,000 futures (offset 5,000,011), on which each household's strategy is chosen among the 170 or so the planner scored, subject to the hard limits, and on which households are ranked;
- final: 3,000 futures (offset 7,000,021) that nothing earlier used. Every reported number is from them.

Hard constraints, each checked on the finalist futures and again on the final futures: stock sales in a falling year at most 2%; ruin no higher than the advisor's; the advisor funds the household (median wealth at 80 at least 10 years of spending, ruin at most 10%); every plausibility check passes; at least one precomputed life change clearly changes "This year's moves" (a Roth conversion shown in the moves changes by at least $20,000, or the 401(k) ask by at least $5,000, with the plan held).

Scale: about 4,100 households scored on the search futures; 225 planned in full on the finalist futures (181 eligible with a visible change); 9 taken to the final futures.
