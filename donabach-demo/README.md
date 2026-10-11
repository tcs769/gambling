# Donabach demo

A clickable demo of **Donabach**, a wealth-management platform that gives every household private-bank
strategies and better judgment about when to use them. It is built to be screen-recorded for investors.

The flow: upload a household's documents, read the numbers off them, forecast income, recommend a strategy
with a year-by-year plan, compare it with a typical advisor, and run what-ifs.

> **Everything is fictional.** The household, documents, names, SSNs (`000-00-0000`) and accounts (`XXXX-1234`)
> are invented. The market is simulated. This is a prototype for illustration, not investment or tax advice.

Machine-learning models are built separately and plug in through the interfaces in `backend/app/ml/`: a strategy
recommender, an income forecaster, and a policy model and a value model that will speed up the year-by-year
planner's search. **Until they are connected the UI says "Model not connected" and never shows a stand-in
prediction.** Every other number on screen (tax, simulation, planner, comparison) is computed by the code, not
typed into the UI.

## Run it

Needs Python 3.11+ and Node 20+ (developed on Python 3.13, Node 22).

```bash
make install     # backend virtualenv + dependencies, frontend npm install
make backend     # API on http://localhost:8000   (interactive docs at /docs)
make frontend    # app on http://localhost:3000
```

Without `make`:

```bash
# backend
cd backend && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --port 8000

# frontend (second terminal)
cd frontend && npm install && npm run dev
```

The first start compiles the simulation kernels with numba (about 10 seconds, then cached in
`backend/.numba_cache/`); the API warms them up before it accepts requests, so the first plan is as fast as the
rest (measured on 4 cores: 10.6 s to start with an empty cache, 1.0 s with it, then about 1.3 s per plan). The browser talks to the
API through a same-origin proxy (`/api/*` to `http://localhost:8000`, see `frontend/next.config.ts`). To point it
elsewhere set `BACKEND_URL` before `npm run dev`, or before `npm run build` for a production build (Next bakes
rewrites in at build time).

**Demo mode** (the switch in the header, on by default) preloads the three sample documents and fixes the random
seed, so every run on camera produces identical numbers. Turn it off to draw a fresh set of futures each time.

## The seven screens

1. **Upload**: drop zone, plus "Use sample documents" so recording is reliable. Each file shows its upload and
   reading state.
2. **Review**: the extracted numbers grouped by document with confidence badges, next to the PDF. Click a field
   and the viewer jumps to its page and highlights the value. One field is deliberately flagged (the brokerage
   statement's holdings add up to $149,999 against a stated total of $150,000) so the demo can show a correction.
3. **A few questions**: tap-to-select chips for goals, with sensible defaults. Values the documents do not
   contain (Roth balance, cash, Social Security) are labelled *Estimated*.
4. **Household profile**: balances by account, this year's computed tax picture, goals.
5. **Forecast**: income fan chart (p10 to p90 band, median line). While the forecaster model is not connected
   it is labelled "Model not connected, placeholder forecast".
6. **Plan**: the recommended strategy in a sentence with a computed reason, the model panel (or its not-connected
   state), and a year-by-year table. The fixed plan appears at once; a "Refining plan…" state follows while the
   year-by-year (adaptive) plan is computed in the background (the demo household's is precomputed), and then the
   table can show either: the years where the planner departs from the fixed strategy are highlighted. Click a row for
   that year's decisions, full tax return and, for the adaptive plan, **"Why this year"**: the action chosen, the two
   next best alternatives and the score gap between them, from the rollout results.
7. **Compare**: the median and risk-adjusted advantage over a good RIA and over a typical advisor, fan chart with
   the two advisors, the best fixed strategy and the adaptive planner, the four strategies side by side, what judgment
   over time adds, "where the advantage comes from", and every strategy searched, ranked.

A **What-if** panel (from Plan and Compare) re-plans with preset events or edited inputs.

## How the numbers are produced

All dollars are **real 2026 dollars**; tax brackets are held constant in 2026 dollars.

| Piece | Where | What it does |
|---|---|---|
| Tax engine | `backend/app/tax/` | Federal MFJ and Illinois for tax year 2026. Every constant is in `params_2026.py` with its source. One scalar kernel is the single source of truth for both the simulator and the line-by-line breakdown. Cross-checked against PolicyEngine-US (below). |
| Documents | `backend/app/docs/`, `fixtures/` | `fixtures/demo_household.json` is the single source of truth for three generated PDFs (a 2026 1040 projection, a brokerage statement, a 401(k) statement). A pdfplumber parser reads them back with value, page, bounding box and rule-based confidence, plus cross-checks. |
| Markets and income | `backend/app/sim/markets.py`, `income.py` | Correlated normal real returns (equity 5.5%/16%, bonds 1.5%/5%, private credit 3.5%/8%) from a fixed seed, shared by every strategy. Income is a **placeholder** life-cycle process until the ML forecaster plugs in. |
| Simulator | `backend/app/sim/simulate.py` | The 11-step yearly household loop (returns, harvesting, goals, spending, conversion, goal bucket, location and rebalancing, tax, fees, contributions) as one numba kernel run over every (strategy, future). |
| Planner | `backend/app/planner/` | Searches the strategies of a planning style on the same 400 futures, scoring each by certainty-equivalent after-tax wealth at 80 (CRRA, risk aversion 3, $50,000 floor). **Equity first** (the default): a spending reserve of 2, 4 or 6 years of expenses in bonds and private credit with everything else in stocks, crossed with Roth conversions x private credit sleeve x direct indexing x 401(k) type x goal funding (**1,008** strategies). **Balanced** (`planning_style: "balanced"`, the earlier default): a stock share with a glide path x the same choices x goal bonds (**4,032**). The search is staged: every strategy is scored on 100 of the futures and the best 150 go on to all 400 (about 1 s; `exhaustive=True` scores everything on everything, and a test checks both pick the same winner). |
| Baselines | `planner/baseline.py` | A **good RIA** (age-based 80% to 50% glide path, same mix in every account, breakpoint fees falling from 1.0% to 0.5%, fund-level harvesting, goals from brokerage, no conversions, pro rata withdrawals) and a **typical advisor** (flat 1.0% fee, no harvesting, accounts managed separately, 80% to 50% glide, no conversions, proportional withdrawals). Each is shown with its definition. |
| Year-by-year planner | `backend/app/sim/adaptive.py`, `planner/adaptive_plan.py`, `adaptive_service.py` | Each year, after that year's returns, scores candidate actions by rollouts and takes the best (below). |
| Explanations | `planner/explain.py` | The five-step "where the advantage comes from" (switch decisions on one at a time from the baseline, same futures) and, per year, the value of each decision found by re-running the plan with only that decision removed for that year. |

The simulation and the planner are explained in detail in the docstrings of `sim/simulate.py` and
`planner/strategies.py`.

## Plugging in the ML models

Drop trained models in `backend/models/` as `recommender.pkl`, `forecaster.pkl`, `policy.pkl` and `value.pkl`;
no restart is needed. The policy and value models are for the year-by-year planner's search: trained on what the
rollout search chose and the score it gave every candidate, they will propose candidate actions and estimate
their scores to speed the search up (nothing is trained here and they are not wired into the search yet; until a
file exists `GET /models/status` says so). The contracts, the exact feature vectors, a worked example and the
formats of the training data are in [`backend/models/README.md`](backend/models/README.md).

```bash
cd backend
python export_training_data.py --k 2000 --paths 150 --out data/training_data.parquet     # the household recommender
python export_training_data.py --decisions --k 500 --decision-paths 4 --decisions-dir data/decisions   # policy and value models
```

## Reports

The measurements behind the numbers are scripts, not hand-typed tables (run from `backend/`; the outputs are in `reports/`):

| Report | Command |
|---|---|
| Sample household after each change (`progress.md`) | `python -m app.study.measure --label "..." --out ../reports/progress/step_NN.json`, then `python -m app.study.progress` |
| Stock-share menu before and after (`stock_share_wins.md`) | `python -m app.study.winners --k 100 --paths 150 --out ../reports/stock_share_wins.md` |
| Risk aversion 2, 3, 5 (`risk_aversion.md`) | `python -m app.study.risk_aversion --out ../reports/risk_aversion.md` |
| Two assumptions against the research (`assumption_review.md`, `sensitivity.md`) | `python -m app.study.sensitivity --out ../reports/sensitivity.md` |
| 300 households of six types (`household_study.csv`, `.md`) | `python -m app.study.household_study --per-type 50 --adaptive-paths 200 --checkpoint /tmp/study.csv --out-dir ../reports` |
| Four-way evaluation and the value of judgment over time (`adaptive_evaluation.md`) | `python -m app.study.adaptive_evaluation --paths 2000 --out ../reports/adaptive_evaluation.md` |
| Decision quality of the year-by-year search (`adaptive_decision_quality.md`) | `python -m app.study.decision_quality --paths 80 --out ../reports/adaptive_decision_quality.md` |
| Is the plan holding too little equity? (`equity_share.md`) | `python -m app.study.equity_share --out ../reports/equity_share.md` |
| What would have to change to reach 2 to 3% a year (`path_to_2_3_percent.md`) | `python -m app.study.reach --out ../reports/path_to_2_3_percent.md` |
| The 300 households when the planner searches at risk aversion 3, 2 and 1, with each plan's tools alone at the advisor's allocation and a heirs'-tax sensitivity (`household_study_risk_aversion_N/`) | `python -m app.study.household_study --per-type 50 --risk-aversion 1 --measure-risk-aversion 3 --skill --heirs-rates 0.24 0.32 --out-dir ../reports/household_study_risk_aversion_1` |

## Regenerating things

```bash
make docs                       # rewrite fixtures/sample_docs/*.pdf from fixtures/demo_household.json
cd frontend && npm run gen:api  # refresh src/lib/api-schema.d.ts from the running API's OpenAPI document
```

The sample PDFs are committed and byte-reproducible; a test fails if they drift from the generator.

## API

Typed with Pydantic (`backend/app/api_models.py`); try it at http://localhost:8000/docs.

| Endpoint | Purpose |
|---|---|
| `POST /documents/sample` | load the three fictional PDFs, return document ids |
| `POST /documents/upload` | accept PDFs |
| `POST /documents/{id}/parse` | fields with bbox and confidence, plus the cross-checks |
| `GET /documents/{id}/file` | serve the PDF to the viewer |
| `POST /household` | build the household from confirmed fields plus answers (422 lists anything unreadable) |
| `POST /forecast` | the forecast, or `connected: false` plus the labelled placeholder |
| `POST /plan` | planner and recommender; everything the Plan and Compare screens need. `planning_style` is `equity_first` (the default) or `balanced`. Returns the fixed plan at once, with the year-by-year plan attached if it is already known (the demo household's is precomputed at startup) or a job id otherwise |
| `GET /plan/adaptive/{id}` | the year-by-year plan's job: status, progress, and the finished plan |
| `DELETE /plan/adaptive/{id}` | the viewer walked away from the plan: drop one watcher; when none is left the job stops (204, or 404 for an unknown id) |
| `POST /plan/year-detail` | decisions, tax return and value of each decision for one year of the fixed plan |
| `POST /plan/whatif` | apply presets and edits, re-plan (same fixed-then-adaptive behaviour) |
| `GET /models/status` | whether each of the four models is connected |

## Tests

```bash
make test                                   # backend, about 8 minutes on 4 cores (`pytest -q -x` stops at the first failure)
cd frontend && npx tsc --noEmit && npx eslint src
make e2e                                    # the whole demo in a real browser (needs both servers running)
```

`make e2e` drives the seven screens, the what-if flow and the unhappy paths (no tax form uploaded, a PDF the demo
does not read, demo mode off) in Chromium, and enforces the requirements that cut across screens on every one: no
console errors, no visible text under 14px, no horizontal overflow at 1440 wide, charts at least 300px tall, the
disclaimer footer on results screens, the "Model not connected" states, and identical numbers across fresh
sessions in demo mode. It writes screenshots to `.screenshots/`. Install a browser once with
`cd frontend && npx playwright-core install chromium`, or point `CHROMIUM_PATH` at one you already have.

* Tax engine: bracket math, Illinois, Roth conversions, capital-gain stacking, NIIT, child-credit phase-out and
  capital-loss carryforward, in both compiled and plain-Python modes.
* Optional cross-check against PolicyEngine-US (`pip install policyengine-us`, then
  `pytest tests/test_policyengine_compare.py`): twelve households match to the cent, including four filers 65
  and over (additional standard deduction and Illinois exemption). PolicyEngine's 2025-2028 senior deduction is
  switched off in the comparison (see above); a test documents what it would add.
* Simulator: each mechanism against hand calculations, a zero-return conservation identity (every dollar of
  change is a contribution, goal, spending, tax or fee), and a per-year recomputation of the simulator's taxes
  through the public tax engine.
* Parser: it recovers every fixture value from the generated PDFs; defects injected into scratch copies were all
  caught.
* A subprocess test forces numba's unsafe `workqueue` threading layer and fires overlapping plans, to protect
  the API from a process abort that overlapping requests would otherwise cause on some machines. The kernel lock
  has two priorities (a request waiting for its plan goes ahead of the adaptive planner's background chunks) and
  has its own tests.
* Year-by-year planner (`tests/test_adaptive.py`): **no look-ahead** (changing every return and wage after year t changes
  nothing about the decisions already taken, scores included, and the rollout random streams are disjoint from the
  evaluation streams); **consistency** (forcing the continuation action every year reproduces the fixed strategy
  exactly, for several policies and households); **sanity** (a retiree with no income, a huge pre-tax balance and room
  in the low brackets converts, and changes the tax timing, not the portfolio's risk); **determinism** (the same
  inputs give identical results whatever the threads or chunking, and in demo mode across API runs);
  **guardrails** (borrowing stays inside its limits and conversion tax is never paid from the converted dollars);
  importance weights unbiased; confirmation on fresh futures; serial and parallel kernels agree.
* Training data and the policy/value interfaces (`tests/test_decision_data.py`, `tests/test_ml.py`): the state
  features never see the future, every candidate the search scored is exported with the chosen one flagged, and a
  missing, broken or contract-violating model is reported as "not connected", never replaced by a made-up prediction.

## Modeling choices and known simplifications

Stated in the app footer: income tax only (no payroll taxes), standard deduction only, no AMT, no state tax
credits. Beyond that, choices made where the spec was silent, so they are not a surprise:

* **Age basis.** The household's age is the primary earner's; both spouses retire in the same year; the spouse's
  age only drives their wage growth. The 10% early-withdrawal penalty applies before age 59 1/2 on that basis.
* **Horizon.** Plans run to age 80 (42 years for the demo household) and are scored on after-tax wealth at 80
  with the same valuation as before: pre-tax balances taxed as if withdrawn evenly over 20 years beside Social
  Security, unrealized gains at 15%. A 20-year spread is long for an 80-year-old, so pre-tax balances are, if
  anything, valued a little too generously.
* **Required minimum distributions** start at 75 for anyone born in 1960 or later (73 for 1951 to 1959),
  computed on the household's combined pre-tax balance from the prior year-end with the IRS Uniform Lifetime
  Table (`tax/params_2026.py`, source in the comment) and the primary earner's age. An RMD is spent first on
  goals and spending; the rest is reinvested in the taxable account.
* **65 and over.** Each spouse aged 65+ adds the $1,650 additional standard deduction (IRS Rev. Proc. 2025-32)
  and Illinois' additional $1,000 exemption. The separate $6,000 senior deduction of the 2025 budget law is left
  out on purpose: it expires after 2028, long before this household reaches 65.
* **Not modeled: survivor years and heirs' taxes.** After the first spouse dies the survivor files as a single
  taxpayer with narrower brackets, and heirs pay tax on inherited pre-tax accounts. Both generally favor Roth
  conversions, so conversion strategies are, if anything, understated. The app footer says so too.
* **Private credit.** The sleeve is 0, 5, 10 or 15% of long-term money; the stock share is applied to the
  rest (with a spending reserve the sleeve counts toward the reserve). It goes in the pre-tax account first, overflows to the Roth, then to the taxable account, where its
  income is taxed each year as ordinary interest (5.5%: its 3.5% real return plus the 2% of inflation the bond
  assumptions imply). The bond / private-credit correlation (0.1) is assumed; the spec gives only the equity pairs.
* **Asset location.** Private credit, then bonds, fill the pre-tax account first; the Roth holds stocks (after
  any private credit); the brokerage account takes the remainder (including overflow bonds).
* **Cash and goals.** Cash joins brokerage bonds. The goal bucket holds the next four years of goals, funded and
  released each year; without it goals are paid from brokerage pro rata.
* **Spending reserve** (the equity-first planning style, the default). Bonds and private credit hold the next 2, 4 or 6
  years of retirement spending net of Social Security (the private credit sleeve counts toward it); the goals of those
  years sit in the taxable goal bucket (pre-tax money would cost a 10% penalty before 59 1/2); every other dollar is in
  stocks, with no glide. Expenses, taxes and required distributions are paid from bonds and private credit before stocks
  inside each account, and in a year stocks fell nothing is sold to build or refill the reserve or the bucket. The account
  order and the asset location are unchanged, so the reserve's bonds sit in the pre-tax account first, where retirement
  withdrawals draw first. A strategy with no reserve gives exactly the results it gave before the reserve existed (pinned in
  `tests/test_reserve.py`). Returns in the model do not mean-revert, so *when* the reserve is refilled moves the median
  advantage by only 0.00 to 0.06 points; what the reserve does is let the plan keep 85 to 100% of the portfolio in stocks
  through retirement without selling them to pay expenses.
* **Fees** are taken pro rata from every account; gains realized to pay tax or fees are reported the next year.
* **Borrowing for goals** (a box-spread loan against the taxable account). Real rate 2.82%: the 1-year Treasury
  yield (4.52%, FRED week ending 2026-10-02) plus 0.30%, less the 2% of inflation the market assumptions imply
  (`tax/params_2026.py`). Interest accrues to the loan and is booked as a capital loss each year (real box spreads
  fall under IRC section 1256, 60% long-term and 40% short-term; treating it all as long-term is a simplification).
  The loan never exceeds 30% of the taxable account (stocks, bonds, private credit; the goal-bond bucket is not
  counted); if a market drop takes it above 40%, assets are sold to bring it back to 30%. It is repaid from the
  year's savings first, and in later low-tax years by selling holdings up to the top of the 0% gain bracket.
* **Conversions** can be paid for from the taxable account (cash included) and from that year's spare wages:
  wages after the tax on them, 401(k) saving, the 10% brokerage saving and normal spending. The documents do not say
  what the household spends today, so normal spending before retirement is taken to be its planned retirement
  spending. The tax is never paid out of the converted dollars. Spare wages are used only for conversion tax;
  as before, wages not saved are consumed.
* **"Advantage" figures** are reported two ways, always together: the difference in **median** after-tax wealth at
  80 and the difference in **certainty-equivalent** wealth (the planner's own objective: CRRA, risk aversion 3, wealth
  below $50,000 counting as $50,000), each annualized as a growth-rate difference, `(plan / baseline)^(1/years) - 1`,
  measured on futures the strategy search never saw, with a 90% range over resamples of those futures. The
  certainty equivalent is dominated by the few futures in which money runs out (the plan's chance of that is about
  0.5%, the good RIA's about 2%): read the risk-adjusted advantage as mostly a statement about that tail.
* **The year-by-year planner** (spec part B) decides each year after that year's returns are known, using only what
  the household could know then (balances by account and asset class, basis, loss carryforward, any loan, age,
  this year's income and goals, recent returns). Candidate actions: stock share (50 to 100%, with the strategy's
  glide path applied), Roth conversion (none or fill the 12/22/24% bracket), private credit (0/5/10/15%), 401(k) type,
  how a goal due this year is paid (sell or borrow) and realizing gains up to the 0% bracket. Each candidate is scored
  by simulating K = 32 fresh futures from the household's current state, applying the candidate for the rest of the year and
  then following the best fixed strategy to age 80, scored by the same certainty equivalent. **Search: coordinate
  search**, the first of the two options in the spec (start from the continuation's action, improve one decision
  at a time holding the others fixed, two passes, at most about 35 candidates a year): it needs no second, cheaper
  scoring model, and its cost is predictable. Pruning with a cheap first score would need that model.
  Two things were added because measurement showed the plain search *lowers* the planner's own objective when its choices
  are re-scored on independent futures (`reports/adaptive_decision_quality.md`): the best of a dozen candidates on the same 32
  rollouts is flattered by luck, and 32 rollouts almost never contain the futures in which money runs out. So (1) half the
  rollouts are drawn from a market a quarter of a standard deviation a year worse and re-weighted (importance sampling: the
  estimates stay unbiased, the bad tail is represented), and (2) a change the search proposes is kept only if it also wins
  by 1.645 standard errors on 64 fresh futures it was not chosen on. The plan table and "Why this year" use one path, so they
  get 8 times the rollouts. See the report for what each step buys and what it costs.
* **No look-ahead.** The rollout futures come from a counter-based random stream keyed by (rollout seed, path, year) whose
  seed is a `SeedSequence` child disjoint from the ones behind the evaluation returns and incomes; the rollout wage
  process restarts from the path's wage level in the decision year; a decision in year t reads the path's inputs only up
  to year t. Tests change every later return and wage and check nothing already decided moves.
* **Running it.** `POST /plan` returns the fixed-strategy plan at once; the year-by-year plan is a background job (one
  worker thread, chunks of 12 paths at background priority, results cached) that the Plan and Compare screens poll, with a
  "Refining plan…" state until it lands. The demo household's plan is computed at startup (set `DONABACH_NO_PRECOMPUTE=1` to
  skip it), so on camera the Plan screen has it at once. What-ifs re-plan the same way. Measured on 4 cores: the fixed plan takes
  1.2 s; a full year-by-year plan (K = 32, 200 evaluation paths) takes **8.6 s**, of which the 200 evaluation paths take 7.4 s
  (0.037 s a path) and the single plan path 1.1 s, against the 10 s target (100 paths: 5.0 s; 400 paths: 15.6 s). A cold start (no numba cache)
  compiles the fixed kernels before the API answers (the 10.6 s above) and the year-by-year kernels in the background
  (about 40 s more, measured on a loaded machine); both are cached afterwards.

**What the numbers say** is whatever the engine produces; nothing is tuned toward a target (`reports/` has every
measurement and the command that regenerates it).

* **The advantage.** For the sample household the planner recommends the lowest stock share on the menu (50%, gliding
  down to 25% by age 70), a Roth conversion filling the 24% bracket every year and a 15% private credit sleeve. On 2,000
  futures it never saw it is ahead of a good RIA by **+0.27% a year in median wealth and +2.54% a year in
  certainty-equivalent wealth** (+0.40% and +2.60% over a typical advisor); the year-by-year planner on top makes it +0.29%
  and +2.60%. Across the 300-household study the typical household of each type is ahead of the good RIA by +0.14% to
  +0.55% a year (median) and +1.62% to +2.97% a year (risk-adjusted). The median advantage is a few tenths of a percent
  a year, not 2 to 3%: the lower fee (0.35% against 0.5 to 1.0%) and asset location are worth about 0.6% a year of median
  wealth, and the lower-risk allocation gives it back (next point) before Roth timing adds a quarter of a percent.
* **Why not 2 to 3%, and what it would take** (`reports/equity_share.md`, `reports/path_to_2_3_percent.md`). The planner's
  objective (risk aversion 3, a $50,000 floor) is decided by the futures in which money runs out, so it picks the lowest stock
  share on the menu: 42.5% of the portfolio falling to 21%, against the good RIA's 80% falling to 50% (with a private credit
  sleeve the stock share is of the money outside it). That costs median wealth; more equity buys it back at about +0.25 points a
  year of median advantage for every 10 points of stock share and costs risk-adjusted advantage. Sample household, over the
  good RIA (median / risk-adjusted): the app (risk aversion 3) +0.27% / +2.54%; risk aversion 2 +0.53% / +1.70%; risk aversion 1
  +1.54% / +0.22% (85% stocks, the same 0.6% chance of running out of money as the advisor, a 10th percentile of $1.49M against
  $0.94M); the most median wealth anything on the menu gives, +1.60% (100% stocks, 1.1% chance of running out). Donabach's tools
  alone at the advisor's own allocation are worth +0.83% (+0.78% for the typical household of the 300): the rest of any larger
  figure is more equity, which an advisor could hold too. **Nothing on the menu reaches 2%.** From the ceiling, 2% takes one of
  these (each an assumption or more risk; none is in the app): an equity return of 7.0% real instead of 5.5% (9.1% for 2.5%,
  11.1% for 3%); a fee near zero; pre-tax money at 80 taxed at a flat 32% (heirs) instead of the specified rate of about 13%
  (+0.37 points); or an advisor holding 70% falling to 40% rather than 80% to 50%. A 0.25% fee and a 32% heirs' rate together
  reach it. The household studies at risk aversion 3, 2 and 1 are in `reports/household_study_risk_aversion_N/`.
* **Why the two measures differ.** Switching the decisions on one at a time from the good RIA: the lower fee and asset
  location add +0.63% a year of median wealth; moving to 50% stocks and a private credit sleeve *costs* 0.6% a year of median
  wealth but lifts the risk-adjusted advantage from +0.85% to +2.52% a year, because certainty-equivalent wealth is
  dominated by the few futures in which money runs out (the plan runs out in 0.1% of futures, the good RIA in 0.6%); Roth
  timing then adds +0.24% a year of median wealth. So most of the risk-adjusted advantage is risk reduction, not extra return,
  and it rests on the private credit assumption (3.5% real net of fees, 8% volatility, no defaults), which the research review calls
  generous in its tails: with no private credit the sample household's figures are -0.09% and +1.51%
  (`reports/sensitivity.md`, `reports/assumption_review.md`).
* **What judgment over time adds.** Not much on top of a well-chosen fixed plan. For the sample household the year-by-year
  planner adds +0.01% a year (median) and +0.06% (risk-adjusted), indistinguishable from nothing in the first and small in
  the second; for the typical household of each type +0.01% to +0.11% (median) and +0.02% to +0.11% (risk-adjusted), most for
  early retirees, whose low-income years are what judgment over time can use (`reports/household_study.md`). The fixed strategy
  already uses the main tools every year, returns do not mean-revert in the model, and the action space is the six decisions in
  the spec: stock share, Roth conversion, private credit, 401(k) type, how a goal is paid and realizing gains. The search matters: a plain
  rollout search raises the median (+0.15% a year) while lowering the planner's own objective (-0.91%), which is why importance
  sampling and re-testing on fresh futures are in (`reports/adaptive_decision_quality.md` has every variant, per decision and
  on whole paths).
* **After a 30% market fall** (the what-if preset) the fixed search's recommendation changes (it adds goal bonds ahead of the
  home purchase) and the year-by-year plan changes with it; the planner's own year-by-year choices do not change systematically.

## Layout

```
backend/app/         main.py (API), api_models.py, schemas.py, builder.py, forecast.py, whatif.py, store.py
  tax/               params_2026.py, engine.py, picture.py
  docs/              generate.py, parse.py, models.py
  sim/               markets.py, income.py, simulate.py, adaptive.py (the year-by-year planner's kernel)
  planner/           strategies.py, search.py, baseline.py, explain.py, guided.py, plan.py,
                     adaptive_plan.py, adaptive_service.py (background jobs, cache), decision_data.py (training data)
  study/             the measurement scripts behind reports/ (households, household_study, adaptive_evaluation, ...)
  ml/                interfaces.py, adapters.py
backend/models/      drop recommender.pkl, forecaster.pkl, policy.pkl, value.pkl here
reports/             measurements: progress, household study, adaptive evaluation, assumption review, ...
backend/tests/       pytest suite
backend/export_training_data.py
fixtures/            demo_household.json, sample_docs/*.pdf
frontend/src/        app/ (the seven routes), components/, lib/ (API client, store, formatting)
```
