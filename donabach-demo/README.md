# Donabach demo

A clickable demo of **Donabach**, a wealth-management platform that gives every household private-bank
strategies and better judgment about when to use them. It is built to be screen-recorded for investors.

The flow: upload a household's documents, read the numbers off them, forecast income, recommend a strategy
with a year-by-year plan, compare it with a typical advisor, and run what-ifs.

> **Everything is fictional.** The household, documents, names, SSNs (`000-00-0000`) and accounts (`XXXX-1234`)
> are invented. The market is simulated. This is a prototype for illustration, not investment or tax advice.

Two machine-learning models (a strategy recommender and an income forecaster) are built separately and plug in
through the interfaces in `backend/app/ml/`. **Until they are connected the UI says "Model not connected" and
never shows a stand-in prediction.** Every other number on screen (tax, simulation, planner, comparison) is
computed by the code, not typed into the UI.

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

The first start compiles the simulation kernels with numba (about 5 to 10 seconds, then cached in
`backend/.numba_cache/`); the API warms them up before it accepts requests, so the first plan is as fast as the
rest (measured on 4 cores: 5.8 s to start cold, 1.1 s warm, then about 0.2 s per plan). The browser talks to the
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
   state), and a year-by-year table. Click a row for that year's decisions, full tax return and the value of each
   decision.
7. **Compare**: stat cards, fan chart for both strategies, "where the advantage comes from", and every strategy
   searched, ranked.

A **What-if** panel (from Plan and Compare) re-plans with preset events or edited inputs.

## How the numbers are produced

All dollars are **real 2026 dollars**; tax brackets are held constant in 2026 dollars.

| Piece | Where | What it does |
|---|---|---|
| Tax engine | `backend/app/tax/` | Federal MFJ and Illinois for tax year 2026. Every constant is in `params_2026.py` with its source. One scalar kernel is the single source of truth for both the simulator and the line-by-line breakdown. Cross-checked against PolicyEngine-US (below). |
| Documents | `backend/app/docs/`, `fixtures/` | `fixtures/demo_household.json` is the single source of truth for three generated PDFs (a 2026 1040 projection, a brokerage statement, a 401(k) statement). A pdfplumber parser reads them back with value, page, bounding box and rule-based confidence, plus cross-checks. |
| Markets and income | `backend/app/sim/markets.py`, `income.py` | Correlated normal real returns (equity 5.5%/16%, bonds 1.5%/5%, private credit 3.5%/8%) from a fixed seed, shared by every strategy. Income is a **placeholder** life-cycle process until the ML forecaster plugs in. |
| Simulator | `backend/app/sim/simulate.py` | The 11-step yearly household loop (returns, harvesting, goals, spending, conversion, goal bucket, location and rebalancing, tax, fees, contributions) as one numba kernel run over every (strategy, future). |
| Planner | `backend/app/planner/` | Searches all **2,016** strategies (stock share x Roth conversions x private credit sleeve x direct indexing x goal bonds x 401(k) type) on the same 400 futures, scoring each by certainty-equivalent after-tax wealth at 80 (CRRA, risk aversion 3, $50,000 floor). The search is staged: every strategy is scored on 100 of the futures and the best 150 go on to all 400 (about 1 s; `exhaustive=True` scores everything on everything, and a test checks both pick the same winner). |
| Baseline | `planner/baseline.py` | A "good RIA": age-based 80% to 50% glide path, same mix in every account, breakpoint fees, fund-level harvesting, goals from brokerage, no conversions, pro rata withdrawals. |
| Explanations | `planner/explain.py` | The five-step "where the advantage comes from" (switch decisions on one at a time from the baseline, same futures) and, per year, the value of each decision found by re-running the plan with only that decision removed for that year. |

The simulation and the planner are explained in detail in the docstrings of `sim/simulate.py` and
`planner/strategies.py`.

## Plugging in the ML models

Drop trained models in `backend/models/` as `recommender.pkl` and `forecaster.pkl`; no restart is needed.
The contracts, the exact feature vector, a worked example and the training-data export are in
[`backend/models/README.md`](backend/models/README.md).

```bash
cd backend && python export_training_data.py --k 2000 --paths 150 --out data/training_data.parquet
```

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
| `POST /plan` | planner and recommender; everything the Plan and Compare screens need |
| `POST /plan/year-detail` | decisions, tax return and value of each decision for one year |
| `POST /plan/whatif` | apply presets and edits, re-plan |
| `GET /models/status` | whether each model is connected |

## Tests

```bash
make test                                   # backend, about 12 s
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
  the API from a process abort that overlapping requests would otherwise cause on some machines.

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
  rest. It goes in the pre-tax account first, overflows to the Roth, then to the taxable account, where its
  income is taxed each year as ordinary interest (5.5%: its 3.5% real return plus the 2% of inflation the bond
  assumptions imply). The bond / private-credit correlation (0.1) is assumed; the spec gives only the equity pairs.
* **Asset location.** Private credit, then bonds, fill the pre-tax account first; the Roth holds stocks (after
  any private credit); the brokerage account takes the remainder (including overflow bonds).
* **Cash and goals.** Cash joins brokerage bonds. The goal bucket holds the next four years of goals, funded and
  released each year; without it goals are paid from brokerage pro rata.
* **Fees** are taken pro rata from every account; gains realized to pay tax or fees are reported the next year.
* **Conversions** can be paid for from the taxable account (cash included) and from that year's spare wages:
  wages after the tax on them, 401(k) saving, the 10% brokerage saving and normal spending. The documents do not say
  what the household spends today, so normal spending before retirement is taken to be its planned retirement
  spending. The tax is never paid out of the converted dollars. Spare wages are used only for conversion tax;
  as before, wages not saved are consumed.
* **"Advantage" figures** are differences of medians (so the stat cards, the outcome cards and the attribution
  bars always agree).

What the numbers say is not tuned. For the sample household the engine's choice is conservative: 70% stocks (the
lowest option on the menu) and no Roth conversions. With risk aversion 3 the safest stock share on the menu often
wins (in a 100-household synthetic sample it was best for 66, against 12 for 100% stocks), and conversions at the
22% bracket or higher cost more tax up front than the model's 20-year withdrawal rate saves later. For the sample
household roughly three quarters of the advantage over the baseline (71% to 84% across 12 random seeds) is
simply the lower fee; the recommendation itself was the same in all 12.

## Layout

```
backend/app/         main.py (API), api_models.py, schemas.py, builder.py, forecast.py, whatif.py, store.py
  tax/               params_2026.py, engine.py, picture.py
  docs/              generate.py, parse.py, models.py
  sim/               markets.py, income.py, simulate.py
  planner/           strategies.py, search.py, baseline.py, explain.py, guided.py, plan.py
  ml/                interfaces.py, adapters.py
backend/models/      drop recommender.pkl / forecaster.pkl here
backend/tests/       pytest suite
backend/export_training_data.py
fixtures/            demo_household.json, sample_docs/*.pdf
frontend/src/        app/ (the seven routes), components/, lib/ (API client, store, formatting)
```
