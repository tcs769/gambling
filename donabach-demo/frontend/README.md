# Donabach demo: frontend

Next.js (App Router) + TypeScript + Recharts. It talks to the Python API through a same-origin proxy
(`/api/*` -> `http://localhost:8000/*`, see `next.config.ts`; override with `BACKEND_URL`). The proxy waits up to five
minutes for the API (`experimental.proxyTimeout`; Next's default of 30 s cut off the liability-matched plan, which takes 6 to 8
seconds on an idle machine and several times that on a busy one).

    npm install        # also copies the pdf.js worker into public/
    npm run dev        # http://localhost:3000

`src/lib/api-schema.d.ts` is generated from the backend's OpenAPI document. Regenerate it after changing an
API model, with the backend running: `npm run gen:api`.

    npm run e2e        # walk the whole demo in Chromium and check it (API and app must be running)
                       # env: BASE_URL (default http://localhost:3000), OUT_DIR (screenshots), CHROMIUM_PATH
    npm run typecheck  # tsc --noEmit
    npm run check:colors  # the chart series colours: contrast on the panel and colour-blind separation, all four pairs, and the savings bar's neighbours

The PDF viewer loads pdf.js's legacy build (it bundles the polyfills pdf.js 6 needs); the matching worker is copied to
`public/pdf.worker.min.mjs` by `npm install` and is git-ignored.

The e2e reads its expectations from the API's own responses, including the year-by-year plan (below). The API keeps
finished year-by-year plans in memory, so against an API that has already planned the households the e2e uses, the
"Refining plan…" checks find the plan ready at once and say so in a note: start the API fresh (it precomputes the
demo household's plan at startup, which the e2e waits for, up to 60 s) to exercise them for real. A production build
(`BACKEND_URL=http://localhost:8000 npm run build && npm start`) is what the e2e is run against.

## The year-by-year plan

`POST /plan` and `POST /plan/whatif` answer with the fixed-strategy plan at once. Its year-by-year (adaptive) part
is either in the same response (`plan.adaptive`, when the API already has it: the demo household, repeated requests)
or a background job (`plan.adaptive_job`) that the app polls every 700 ms (`GET /plan/adaptive/{id}`). The state
lives in `src/lib/state.tsx`: each plan keeps its own year-by-year state (`ready`, `refining` with the job's
progress, `failed` with the API's error text), so a newer plan never shows an older plan's year-by-year part, and
polling a job stops as soon as the plan it belongs to is replaced (a new what-if, a reset, new answers). The app then
tells the API it no longer wants the job (`DELETE /plan/adaptive/{id}`, once per abandoned job, never for the job it
is following); the API stops a job when nobody is watching it any more, so a newer what-if does not queue behind it.

While a job runs the Plan and Comparison screens show the fixed plan and say "Refining plan…" (a pill beside the
title; on Comparison also a placeholder panel that holds the room of the panels that will replace it). The Plan
table switches between "Year-by-year plan" (the default once it is ready) and "Fixed strategy"; the years where the
planner changed something from the fixed strategy are tinted and tagged "Changed: …", and the year drawer shows
"Why this year" from the plan's own `decisions` and `year_details`. A what-if shows a "What changed in the plan"
panel against the plan it started from. `src/lib/adaptive.ts` holds the words and the before/after arithmetic.

The fourth chart colour (the adaptive planner, drawn dotted) and how it was chosen are documented next to the
series tokens in `src/app/globals.css`; `npm run check:colors` covers all four.

## The showcase flow (`/showcase`)

A separate three-step walk on one household, for showing the idea in a few minutes without any documents. The home page
(Upload) has an "Open the showcase" link; inside the flow the header shows three steps (Household, Strategies, Wealth) in
place of the demo's seven, with the brand still leading home, and every screen ends in a primary "next" button with a back
link beside it. The flow is light, like the rest of the demo, whatever the system asks for (`color-scheme: light` on `:root`).

1. **`/showcase`, the household card**: the household's name, type and tagline, who is in it (wages, children), annual income
   and total saved, where the savings are (a stacked bar of taxable / pre-tax / Roth / cash with a legend, and the taxable
   account's basis and unrealized gain called out), what they are saving for (home, college, retirement and Social Security
   on a line from today to the horizon age, each with the API's detail sentence) and what stands out (the API's notes).
2. **`/showcase/strategies`, the waterfall**: from a good advisor's result to Donabach's, one floating bar per strategy in the
   order the API switched them on, ending in a total bar. It is the **median advantage only**: no risk-adjusted number or
   word is on this screen (the API's waterfall has no such field). Every row writes both the percent a year and the dollars
   at the horizon, and a segmented control chooses which of the two the bar's length shows. Every strategy has a switch (a
   checkbox with the switch role, labelled with its name, with a button that opens the API's sentence on what it does).
   The total and the two medians are in large type above, the same numbers are a toggle away as a table, and the figure
   has a text alternative.
3. **`/showcase/wealth`, wealth over time**: the whole plan with every strategy on, and it says so under the title. It does
   not follow the switches and never asks the API for anything: it shows the household answer's `wealth` as it came. The
   median advantage and the risk-adjusted one (shown here once, with the API's label, figure, dollars and one-line explanation,
   word for word), then after-tax wealth by age for Donabach and the advisor as four lines (the typical future solid, the
   bad-market 10th percentile dashed, one colour for each entity), a tooltip with all four at an age, end labels, a table twin,
   the two 10th-percentile values at the horizon and the chance of running out of money for both.

The data is two calls. `GET /showcase` answers with the household, its card, the plan in words, the waterfall with every
strategy on (`waterfall`: median advantage only), the whole plan's wealth over time (`wealth`: both measures of the advantage,
worked out once) and the footer's note. `POST /showcase/analysis {enabled}` answers with the median-only waterfall for only
those strategies on. No number on these screens is typed in the app, and nothing about the household is: the e2e checks them
against the API's own answers, and it (and the screens) were run against households of other shapes (one earner or two, with
or without a taxable account or children, an early retirement, two goals in the same year, a short horizon, strategies that
cost a little, a strategy that does nothing once another is off).

**The footer.** Every showcase screen puts the API's `footer_note` on a line of its own at the top of the footer, ahead of the
disclaimers, and only once the household has loaded. It is written as the API sends it (the "typical household" figure in it
is the API's: the median of the 300-household study), and the app adds no number to it.

**Asking early.** The household is asked for once. The home page's "Open the showcase" link starts the request as soon as it is
on the page and again when it is hovered, focused or touched (that asks only if the answer never came or is over a minute old:
`prefetchShowcase` in `src/lib/showcase.tsx`), so by the time the link is followed the household is usually in hand and the
first screen draws with no placeholder; a flow opened without that (a reload, a link to a later screen) starts the request as
soon as it mounts. Inside the flow the other two screens' code is fetched at once (`router.prefetch`), so each screen opens
without waiting. There are no minimum times on the placeholders: they show only while something is actually on its way. The e2e
checks that, once the household is in, Household, Strategies, Wealth and Strategies again each show their content within a
second of the click with no placeholder.

**How the switches flow.** `src/lib/showcase.tsx` holds the flow's state (the household, which strategies are on, the waterfall
on screen) in a provider rendered by `src/app/showcase/layout.tsx`, so the strategies screen keeps what was chosen when you
go to the wealth screen and come back. The shell keeps one `main` for the whole flow (it keys the demo's `main` by route,
which would remount the provider and drop the choices), and each screen eases in by itself (`ShowcasePage`). Switching a
strategy moves its switch at once and asks the API for the new set (about half a second the first time, unless the API has
it ready). Until the answer arrives the bars and numbers stay on screen, dimmed, with "Recomputing…" and a polite announcement
for screen readers; when it arrives the bars glide to their new places and the recomputed total is announced. Answers are kept
by the set they are for, so switching a strategy back is instant. A change made while an answer is on its way drops that answer
(its request is aborted, and one that arrives anyway is ignored). If the API refuses a change, its message is shown and the
switches go back to what the numbers on screen are for. Moving to the wealth screen while a change is still being worked out
changes nothing there: it shows the whole plan at once, and the change lands on the strategies screen when it arrives.

`e2e/showcase.mjs` holds the checks, called at the end of `walkthrough.mjs`; run alone it takes a little over a minute
(`BASE_URL=... CHROMIUM_PATH=... node e2e/showcase.mjs`). They look at every screen at 390, 768 and 1280 (overflow, text size,
contrast of every piece of text, what spills out of its panel) and at 1280 with the system asking for dark (still light:
same colour scheme, page colour and tokens).

## Two valuations of wealth at 80

The API values wealth at the horizon two ways, each with its own label (`settings.liquidated_label` "Liquidated at 80" and
`settings.heirs_label` "Passed to heirs at 80"; the screens show the labels as they come). **Liquidated** is the app's
valuation, what the planner searches and scores on; **passed to heirs** values the estate with a step-up on the taxable account
and the pre-tax accounts at the heirs' rate (`settings.heirs_rate`, with `settings.heirs_note` saying what it assumes and why).

* **Comparison.** One line and a disclosure, "How these are valued" (the API's heirs note word for word, with the rate), open the
  screen. In "Donabach's advantage" every cell (two measures x two advisors) holds both valuations, each with its figure, its
  90% range and its dollars, on one axis per measure; in the cards (the plan's and both advisors') the typical outcome and the
  bad case are given under each label, and lifetime taxes and the chance of a shortfall (which have one value) follow under
  "Taxes and risks". Both valuations are on the screen at first sight, none behind a click. With a what-if on screen every
  figure of both valuations says how far it moved. The fan chart, "Where the advantage comes from", the four-way table and
  "What judgment over time adds" are liquidated by construction (the API has no heirs figure for them) and say so beside
  their titles.
* **Showcase wealth.** The headline and the lines are "Liquidated at 80" (said on the headline and the chart). Under the headline
  a compact "Passed to heirs at 80" block gives the two medians at the horizon and the median advantage a year and in dollars;
  the first sentence of the API's note (it states the rate) is on the screen, the rest behind "Why 24%, and what is left out".
  The API's heirs figures are the median only, so the risk-adjusted advantage is still shown once, on the headline. The waterfall
  is not touched.
* The footer's simplifications now read "the standard deduction (itemizing only for charitable gifts)".

## Charitable giving

`Answers.charitable_giving` (default 0) is a question on the Questions screen ("Charitable giving a year", with the preset
amounts $0, $2k, $5k and $10k and a custom amount that must be at least zero, and one line of help). It goes in the household
request beside `retirement_spending`. The Profile's goals list adds "Charitable giving" with "$X a year" only when the
household's `goals.charitable_giving` is above zero (the API's own goal lines leave it out), and the what-if panel has an edit
for it under retirement spending (`edits.charitable_giving`). The Profile's tax picture words its deduction note from
`itemized`, `deduction_used` and `charitable_deduction`, though the API's profile return never carries giving (see below).

## Planning styles (the Plan screen's switch)

`planning_style` is a `/plan` parameter: `equity_first` (the default and what the app plans with), `balanced` and
`liability_matched`. The Plan screen has a radio group, "Planning style": **Equity-first | Balanced | Liability-matched | All
three side by side**, with a line under it on what the chosen style is.

* **Equity-first** is the Plan screen as it was. **Balanced** and **Liability-matched** show that style's plan: the strategy card,
  a "How this plan does" panel (wealth, the advantage over the good RIA in both measures and both valuations, taxes and risks;
  for the liability-matched plan also its two limits), the fixed strategy's year table (the year-by-year planner runs for the
  equity-first plan only: the other styles are asked for with `adaptive: false`, so no background job starts for them) and the
  year drawer. The liability-matched plan has no model recommendation panel: the API says it does not consult the recommender.
* **All three side by side** puts the three plans in columns (one `/plan` call per style, the same household, shock and seed: the
  other two are asked for with the equity-first plan's `settings.seed`, so all three are measured on the same futures): the
  plan's label and its reserve and stock choices in words, the whole sentence behind a fold, median and 10th-percentile wealth
  (liquidated), the advantage over the good RIA (median and risk-adjusted, liquidated and passed to heirs, each with its 90% range
  and a dagger where the range includes zero), lifetime taxes, the chance of running out of money and of selling stocks in a
  falling year to pay for goals or spending (`stats.forced_sale_chance`) each beside the good RIA's. The liability-matched column
  adds the two limits it was chosen under: stocks sold in a falling year against `forced_sale_limit`, running out of money against
  the good RIA's, both on fresh futures and on the futures it was chosen on (which is what `feasible` is judged on), `feasible`
  in words, the reserve in years and the stock share by age. The sections line up across the columns where there is room (the
  columns are laid out by the room the panel has, 900px of it, and stack below that).
* **Loading and failure belong to the column.** The balanced search takes a few seconds and the liability-matched one longer: the
  column that is waiting says so (a spinner, `aria-busy`), the others are complete and usable, and a refusal is shown in its
  column with the API's message and a "Try again" for that column only.
* **Caching.** `src/lib/state.tsx` keeps the other styles' plans per equity-first plan (`stylePlans`), so toggling back is
  instant and asks for nothing. A what-if (or its reset) changes the household on screen: the other styles are asked for again
  on that household (a reset brings back the ones kept for the first household). The switch keeps its place while other screens
  are visited. The Comparison screen and the what-if edits stay on the equity-first plan (the Plan screen says so under a
  single style).

`e2e/valuations.mjs`, `e2e/giving.mjs` and `e2e/styles.mjs` hold the checks for all three, called at the end of `walkthrough.mjs`
(each runs alone too: `BASE_URL=... CHROMIUM_PATH=... node e2e/styles.mjs`; `e2e/lib.mjs` has what they share). They read every
expectation from what the API sent the browser.

## Known limits

* A failed year-by-year job is reported with the API's error text and the fixed plan stays fully usable, but there is
  no retry button (a new what-if, a reset or new answers start a new job).
* The year-by-year plan's decisions carry no dollar value of their own (the fixed plan's year detail does): the
  drawer says "not valued one by one". Its re-test scores are quoted only when a change was kept, and the "market fell
  this year" note exists only for the plan path's years (`facts.market_return`).
* The job's progress is one fraction; the API does not say whether it is still queued or has started.
* The Plan table and the chart's table twin scroll sideways inside their panels when the window is narrow (below
  about 700px for the table, about 960px of panel room for the twin); no heading word is cut off. The step
  navigation overflows the page below about 720px wide.
* In the showcase, a bad-market (10th percentile) future that runs out of money is a negative wealth in the API's lines, and
  the wealth chart's axis reaches below zero to show it (the API does not floor it).
* The liability-matched plan is judged on two sets of futures (`feasible` on the ones it was chosen on, the other figures on
  fresh ones), so a plan can be inside a limit on fresh futures and still be marked as not having met it; the screen says which
  figure is which. The Profile's "This year's tax picture" does not apply charitable giving (the API's `current_tax_return`
  passes no gifts), whereas the year drawer's returns do.
