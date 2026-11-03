# Showcase household search (John Smith)

Only the household varied; the engine and its assumptions were not touched. About 2,600 plausible households were scored (random draws, then a hill climb), the best 40 were planned in full with the direct-indexing transition tax counted (funds sold, tax charged, basis reset), and six distinct finalists were examined in detail (`showcase_search_finalists.json`). Code: `backend/app/study/showcase_search.py`, `showcase_finalists.py`.

Rules: every household passes 11 or 12 plausibility checks (income, retirement balances, financial assets against the SCF 2022 age-group net worth and income, cash, basis, saving rate, spending, retirement age, home, college, giving), the standard advisor must itself be able to fund the household (median wealth at 80 of at least 10 years of spending, ruin at most 10%), and the plan must meet the liability-matched limits (forced sale in at most about 2% of futures, ruin no higher than the advisor's). The SCF figures come from secondary summaries of the 2022 survey, because the Federal Reserve host was not reachable from the session.

Findings to state plainly:
- With the transition tax counted, direct indexing was chosen for 1 of the 40 planned households and for none of the six finalists. Switching it on for a finalist lowers median wealth at 80 by $190,000 to $610,000.
- Gifts of appreciated shares never raised the advantage: every top household has giving of $0 (giving reduces wealth). A household that gives uses the strategy and scores lower.
- The planner's own feasibility flag is false for four of the top six: their forced-sale share on the 2,000 held-out futures is 2.1% to 2.5%, against a 2% limit that the search met on its 1,600 futures. Ruin is below the advisor's in all six.
