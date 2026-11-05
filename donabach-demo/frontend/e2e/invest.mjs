// Invest (/invest) as the design mockup draws it: the heading row with the five tabs (keyboard, hash), the summary strip, every tab
// against the API's plan (the drawn chart, mix, what goes where with its shading, this year's moves and Approve, holdings, taxes,
// retirement income, goals), no plan/model wording, the one disclaimer, and What changed (absent on the first portfolio).
import { isMain, runAlone, newPage, visibleText, dollarsWhole } from "./portal.mjs";
import {
  DISCLAIMER,
  wealthM,
  dash,
  pct0,
  pctTrim,
  tableRows,
  footRows,
  listRows,
  moveText,
  STATUS,
  planFromApi,
  toInvest,
  openTab,
} from "./invest-lib.mjs";

const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const ACCOUNT_TAB = { brokerage: "Brokerage", pretax: "401(k) and IRA", roth: "Roth IRA" };
const rgb = (s) => s.match(/\d+/g).slice(0, 3).map(Number);

export async function runInvest({ browser, base, check }) {
  const plan = await planFromApi(base);
  const pf = plan.portfolio;
  const { context, page, issues } = await newPage(browser);
  await toInvest(page, base);
  const text = (id) => page.getByTestId(id).innerText();
  const selectedTab = () =>
    page.getByRole("tablist", { name: "Invest sections" }).getByRole("tab", { selected: true }).innerText();

  // --- heading row and strip
  check((await page.locator("h1").innerText()) === "Invest", "the page title is Invest");
  const h1Box = await page.locator("h1").boundingBox();
  const listBox = await page.getByRole("tablist", { name: "Invest sections" }).boundingBox();
  check(listBox.x > h1Box.x + h1Box.width && Math.abs(listBox.y - h1Box.y) < 60, "the tabs sit right of the title");
  check(
    (await text("projected-wealth")) === wealthM(pf.summary.projected_wealth),
    `strip: projected wealth ${wealthM(pf.summary.projected_wealth)}`,
  );
  check((await text("invested-today")) === dollarsWhole(pf.summary.invested_today), "strip: total savings");
  check((await text("yearly-fee")) === dollarsWhole(pf.summary.fee_dollars), "strip: yearly fee dollars");
  check(
    (await text("fee-rate")) === `${pctTrim(pf.summary.fee_rate)} of managed accounts`,
    `strip: "${pctTrim(pf.summary.fee_rate)} of managed accounts"`,
  );
  check((await text("tax-saved")) === dollarsWhole(pf.summary.tax_saved), "strip: tax saved equals the API's");
  const labels = (await page.getByTestId("summary").innerText()).replace(/\s+/g, " ");
  for (const l of ["Projected at 80", "Total savings", "Yearly fee", "Tax saved this year", "estimated"])
    check(labels.includes(l), `strip label "${l}"`);
  const big = await page.getByTestId("projected-wealth").evaluate((el) => ({
    font: getComputedStyle(el).fontFamily,
    size: getComputedStyle(el).fontSize,
    color: getComputedStyle(el).color,
  }));
  check(
    /Cambria/.test(big.font) && big.size === "44px" && rgb(big.color).join() === "31,58,95",
    "the large figure: serif, 44px, navy",
  );
  check((await page.getByTestId("what-changed").count()) === 0, "no What changed block on the first portfolio");
  check(
    (await page.locator("[data-plan-id]").getAttribute("data-plan-id")) === plan.plan_id,
    "the page shows the API's plan",
  );

  // --- tabs: roles, arrow keys, hash
  const tabs = page.getByRole("tablist", { name: "Invest sections" }).getByRole("tab");
  check(
    eq(await tabs.allInnerTexts(), ["Overview", "Holdings", "Taxes", "Retirement income", "Goals"]),
    "five tabs: Overview, Holdings, Taxes, Retirement income, Goals",
  );
  await page.getByRole("tab", { name: "Overview" }).focus();
  await page.keyboard.press("ArrowRight");
  check((await selectedTab()) === "Holdings", "ArrowRight moves to Holdings");
  check((await page.evaluate(() => document.activeElement?.textContent)) === "Holdings", "and focus follows");
  await page.keyboard.press("End");
  check((await selectedTab()) === "Goals", "End goes to the last tab");
  await page.keyboard.press("ArrowRight");
  check((await selectedTab()) === "Overview", "ArrowRight wraps to Overview");
  await page.keyboard.press("ArrowLeft");
  check((await selectedTab()) === "Goals", "ArrowLeft wraps back");
  check(new URL(page.url()).hash === "#goals", "the tab is in the URL hash");
  check((await text("projected-wealth")) === wealthM(pf.summary.projected_wealth), "the strip stays above every tab");
  await page.getByRole("tab", { name: "Overview" }).click();

  // --- Overview: the drawn chart
  const ov = pf.overview;
  const chart = page.getByTestId("projection-chart");
  await chart.locator("svg").waitFor({ timeout: 5000 });
  check((await chart.locator("svg path").count()) === 1, "the chart draws one line");
  check((await chart.locator("svg circle").count()) === 1, "with one end dot");
  const bands = await chart.locator("rect[data-marker]").count();
  const lines = await chart.locator("line[data-marker]").count();
  check(
    bands === ov.markers.filter((m) => m.end_age !== null).length &&
      lines === ov.markers.filter((m) => m.end_age === null).length,
    `markers: ${bands} band(s), ${lines} dashed line(s)`,
  );
  const svgText = (await chart.locator("svg").evaluate((e) => e.textContent)).replace(/\s+/g, " ");
  const tagOf = (m) => (m.key === "retirement" ? `Retire at ${m.start_age}` : m.label);
  check(
    ov.markers.every((m) => svgText.includes(tagOf(m))),
    `each marker has its tag (${ov.markers.map(tagOf).join(", ")})`,
  );
  const ylabs = await chart
    .locator("svg text")
    .evaluateAll((els) => els.map((e) => e.textContent).filter((t) => /^\$/.test(t)));
  check(ylabs[0] === "$0" && ylabs.length >= 3, `y labels start at $0 (${ylabs.join(" ")})`);
  check(
    /^Projected wealth rising from/.test((await chart.locator("svg").getAttribute("aria-label")) ?? ""),
    "the chart has a text description",
  );
  await page.getByRole("button", { name: "View as table" }).click();
  const proj = await tableRows(page.getByRole("table", { name: "Projected wealth by age" }));
  check(
    eq(
      proj,
      ov.projection.map((p) => [String(p.age), wealthM(p.wealth)]),
    ),
    "the table twin equals the projection",
  );
  await page.getByRole("button", { name: "View as chart" }).click();
  check((await page.getByText("Typical outcome, after tax", { exact: true }).count()) === 1, "chart caption");

  // --- Overall mix
  const mixRows = await tableRows(page.getByTestId("mix-table"));
  check(
    eq(
      mixRows,
      ov.mix.rows.map((r) =>
        r.amount < 0.5
          ? [r.label, "–", "–", "–"]
          : [r.label, dollarsWhole(r.amount), pct0(r.share), pctTrim(r.expected_return)],
      ),
    ),
    "mix table equals the API's (all five classes; empty ones show a dash)",
  );
  const heads = (await page.getByTestId("mix-table").locator("thead th").allInnerTexts()).map((s) => s.trim());
  check(eq(heads, ["Asset class", "Amount", "Share", "Exp. return"]), "mix table headers as the mockup");
  const segs = await page.getByTestId("mix-bar").first().locator("span").count();
  check(
    segs === ov.mix.rows.filter((r) => r.share >= 0.0005).length,
    `the mix bar has ${segs} segments (classes with money)`,
  );
  const barH = await page
    .getByTestId("mix-bar")
    .first()
    .evaluate((e) => e.getBoundingClientRect().height);
  check(Math.round(barH) === 44, "the mix bar is 44px tall");
  const swatches = await page
    .getByTestId("mix-table")
    .locator("tbody th i")
    .evaluateAll((els) => els.map((e) => e.style.background));
  check(
    eq(swatches, ["var(--seg1)", "var(--seg5)", "var(--seg2)", "var(--seg3)", "var(--seg4)"]),
    "class colours: US seg1, International seg5, Bonds seg2, Private credit seg3, Cash seg4",
  );

  // --- What goes where (three columns, three shades)
  const loc = page.getByTestId("location-table");
  check(
    eq((await loc.locator("thead th").allInnerTexts()).map((s) => s.trim()).slice(1), [
      "Brokerage",
      "401(k) / IRA",
      "Roth IRA",
    ]),
    "what goes where: Brokerage, 401(k) / IRA, Roth IRA",
  );
  check(
    eq(
      await tableRows(loc),
      ov.location.rows.map((r) => [r.label, dash(r.brokerage), dash(r.pretax), dash(r.roth)]),
    ),
    "what goes where equals the API's (zeros as a dash)",
  );
  const t = ov.location.total;
  check(
    eq((await footRows(loc))[0], ["Total", dash(t.brokerage), dash(t.pretax), dash(t.roth)]),
    "and so does its total row",
  );
  const rule = await loc
    .locator("tfoot td")
    .first()
    .evaluate((e) => getComputedStyle(e).borderTopColor);
  check(rgb(rule).join() === "30,36,48", `the total row has a heavy top rule in ink (${rule})`);
  const cellInfo = await loc
    .locator("tbody td")
    .evaluateAll((cells) => cells.map((c) => ({ text: c.innerText.trim(), shade: c.getAttribute("data-shade") })));
  const biggest = Math.max(...ov.location.rows.flatMap((r) => [r.brokerage, r.pretax, r.roth]));
  const expectShade = (v) => (v < 0.5 ? null : v / biggest >= 0.35 ? "c3" : v / biggest >= 0.12 ? "c2" : "c1");
  const expected = ov.location.rows.flatMap((r) => [r.brokerage, r.pretax, r.roth]).map(expectShade);
  check(
    eq(
      cellInfo.map((c) => c.shade),
      expected,
    ),
    `location: shading c1/c2/c3 by size (${[...new Set(expected)].join(",")})`,
  );
  check(
    cellInfo.filter((c) => c.text === "–").every((c) => c.shade === null),
    "location: zero cells have no shade",
  );
  const alphas = await loc.locator("tbody td[data-shade]").evaluateAll((cells) =>
    cells.map((c) => {
      const m = getComputedStyle(c).backgroundColor.match(/rgba?\(([^)]+)\)/);
      const parts = m ? m[1].split(",").map(Number) : [0, 0, 0, 1];
      return [c.getAttribute("data-shade"), parts.length === 4 ? parts[3] : 1];
    }),
  );
  const alphaOf = (k) => alphas.filter(([s]) => s === k).map(([, a]) => a);
  check(
    !alphaOf("c3").length || !alphaOf("c1").length || Math.min(...alphaOf("c3")) > Math.max(...alphaOf("c1")),
    "darker shade for larger cells",
  );
  check(
    (await page.getByText("Darker cells hold more of each asset class.", { exact: true }).count()) === 1,
    "the shading caption",
  );

  // --- This year's moves
  const moves = page.getByTestId("moves-list");
  const moveRows = await listRows(moves);
  const expectMoves = ov.moves.map((m) => [
    STATUS[m.status],
    moveText(m).replace(/\s+/g, " "),
    m.status === "needs_ok" ? `${m.timing} Approve` : m.timing,
  ]);
  check(eq(moveRows, expectMoves), "this year's moves equal the API's (pill, description, when or Approve)");
  check((await page.getByText("Waramoug handles these for you", { exact: true }).count()) === 1, "the moves caption");
  const approveBtns = page.getByRole("button", { name: /^Approve/ });
  const needs = ov.moves.filter((m) => m.status === "needs_ok").length;
  check((await approveBtns.count()) === needs, `Approve shows on the ${needs} move(s) that need an OK`);

  // Approve persists
  const row = page.locator('[data-move="conversion"]');
  const conv = ov.moves.find((m) => m.key === "conversion");
  await row.getByRole("button", { name: /^Approve/ }).click();
  check((await row.locator("[data-status]").innerText()) === "Scheduled", "Approve changes the pill to Scheduled");
  check((await row.getByRole("button").count()) === 0, "and the button is gone");
  check((await row.locator("> span").last().innerText()) === conv.timing, "and the when text becomes the API's timing");
  check(
    (await page.locator('[role="status"]').first().innerText()).includes("scheduled"),
    "an aria-live line announces it",
  );
  await openTab(page, "Taxes");
  await openTab(page, "Overview");
  check(
    (await page.locator('[data-move="conversion"] [data-status]').innerText()) === "Scheduled",
    "the approval persists across tab switches",
  );
  await page.reload({ waitUntil: "networkidle" });
  check(
    (await page.locator('[data-move="conversion"] [data-status]').innerText()) === "Scheduled",
    "and across a reload",
  );

  // --- Holdings
  await openTab(page, "Holdings");
  const h = pf.holdings;
  check(
    eq(
      await page.getByRole("tablist", { name: "Accounts" }).getByRole("tab").allInnerTexts(),
      h.accounts.map((a) => ACCOUNT_TAB[a.key] ?? a.label),
    ),
    "account switcher: Brokerage, 401(k) and IRA, Roth IRA",
  );
  for (const acct of h.accounts) {
    await page.getByRole("tab", { name: ACCOUNT_TAB[acct.key] ?? acct.label, exact: true }).click();
    const panel = page.getByTestId(`account-${acct.key}`);
    check(
      (await panel.getByTestId("account-balance").innerText()) === dollarsWhole(acct.balance),
      `${acct.label}: balance`,
    );
    const meta = (await panel.getByTestId("account-meta").innerText()).replace(/\s+/g, " ");
    check(
      meta.includes(`${dollarsWhole(acct.balance)} balance`) && meta.includes(acct.taxation),
      `${acct.label}: balance and "${acct.taxation}"`,
    );
    if (acct.cost_basis !== null)
      check(
        meta.includes(`${dollarsWhole(acct.cost_basis)} cost basis`) &&
          meta.includes(`${dollarsWhole(acct.unrealized_gain)} unrealized gain`),
        `${acct.label}: cost basis and unrealized gain`,
      );
    else check(!/cost basis|unrealized/.test(meta), `${acct.label}: no cost basis`);
    const gainHead = acct.cost_basis !== null ? "Gain" : "Yield";
    check(
      eq(
        (await panel.getByTestId("holdings-table").locator("thead th").allInnerTexts()).map((s) => s.trim()),
        ["Holding", "Positions", "Value", gainHead, "Share"],
      ),
      `${acct.label}: columns end Value, ${gainHead}, Share`,
    );
    const rows = await tableRows(panel.getByTestId("holdings-table"));
    check(
      eq(
        rows,
        acct.holdings.map((r) => [
          r.name,
          r.positions > 0 ? String(r.positions) : "–",
          dollarsWhole(r.value),
          r.gain !== null ? dollarsWhole(r.gain) : r.yield_rate !== null ? pctTrim(r.yield_rate) : "–",
          pct0(r.share),
        ]),
      ),
      `${acct.label}: holdings table equals the API's`,
    );
  }
  check(
    (await page.getByTestId("largest-stocks").count()) === (h.largest_stocks ? 1 : 0),
    "largest stocks only when the API has them",
  );
  if (h.largest_stocks) {
    check(
      eq(
        await tableRows(page.getByTestId("largest-stocks")),
        h.largest_stocks.map((r) => [r.name, dollarsWhole(r.value), dollarsWhole(r.gain)]),
      ),
      "largest stocks equal the API's",
    );
    const held = Math.max(...h.accounts.find((a) => a.key === "brokerage").holdings.map((r) => r.positions));
    check(
      (await page.getByText(`Brokerage, ${held} held`, { exact: true }).count()) === 1,
      `caption "Brokerage, ${held} held"`,
    );
  }
  for (const [id, rows] of [
    ["bars-stocks-by-sector", h.sectors],
    ["bars-stocks-by-region", h.regions],
  ]) {
    const items = await page.getByTestId(id).locator("li").allInnerTexts();
    check(
      eq(
        items.map((s) => s.replace(/\s+/g, " ")),
        rows.map((r) => `${r.label} ${pct0(r.share)}`),
      ),
      `${id}: label and share equal the API's`,
    );
  }
  check(
    (await page.getByText("Illustrative", { exact: true }).count()) ===
      (h.illustrative ? 2 + (h.largest_stocks?.length ? 1 : 0) : 0),
    "an Illustrative tag on the sector bars, the region bars and (when shown) the largest stocks",
  );

  // --- Taxes
  await openTab(page, "Taxes");
  const tx = pf.taxes;
  const y = tx.this_year;
  const flat = (await page.getByTestId("taxes-year").innerText()).replace(/\s+/g, " ");
  const want = [
    ["Roth conversion", y.roth_conversion],
    ["Tax on the conversion", y.conversion_tax],
    ["Losses harvested", y.losses_harvested],
    ["Gains offset", y.gains_offset],
    ["Deducted from income", y.deducted_from_income],
    ["Interest kept out of taxable accounts", y.interest_kept_out],
    ["Estimated tax saved", y.tax_saved],
  ];
  check(
    want.every(([l, v]) => flat.includes(`${l} ${dollarsWhole(v)}`)),
    "taxes this year: every row equals the API's",
  );
  check(y.carried_forward > 0 === flat.includes("Carried forward"), "carried forward only when above 0");
  const totalRule = await page
    .getByTestId("taxes-saved")
    .evaluate((e) => getComputedStyle(e.parentElement).borderTopColor);
  check(rgb(totalRule).join() === "30,36,48", "the total row has a heavy top rule in ink");
  const filledIdx = tx.bracket.brackets.findIndex((b) => b.filled);
  const shownCount = Math.min(tx.bracket.brackets.length, filledIdx + 2);
  const filled = await page.locator('[data-testid="bracket-bar"] [data-filled]').getAttribute("data-rate");
  check(+filled === tx.bracket.brackets[filledIdx].rate, "the filled bracket is highlighted");
  const fillBg = await page
    .locator('[data-testid="bracket-bar"] [data-filled]')
    .evaluate((e) => getComputedStyle(e).backgroundColor);
  check(rgb(fillBg).join() === "31,58,95", "and navy");
  check(
    (await page.locator('[data-testid="bracket-bar"] > div').count()) === shownCount,
    `brackets drawn up to the one above the filled one (${shownCount})`,
  );
  const bv = (await page.getByTestId("bracket-values").innerText()).replace(/\s+/g, " ");
  const b = tx.bracket;
  check(
    [
      ["Taxable income before conversion", dollarsWhole(b.taxable_before)],
      [`Conversion fills the ${pctTrim(b.marginal_rate)} bracket to`, dollarsWhole(b.fills_to)],
      ["Federal marginal rate", pctTrim(b.marginal_rate)],
      ["Illinois tax on the conversion", dollarsWhole(b.illinois_tax_on_conversion)],
    ].every(([l, v]) => bv.includes(`${l} ${v}`)),
    "bracket values equal the API's",
  );
  if (tx.opportunities.length === 0)
    check(
      (await page.getByTestId("no-opportunities").innerText()) === "No positions below cost",
      "no opportunities: one line",
    );
  else
    check(
      eq(
        await tableRows(page.getByTestId("opportunities-table")),
        tx.opportunities.map((o) => [
          o.name,
          dollarsWhole(o.value),
          dollarsWhole(o.cost),
          dollarsWhole(o.loss),
          o.replacement,
        ]),
      ),
      "opportunities table equals the API's",
    );
  check(
    eq(
      await tableRows(page.getByTestId("conversions-table")),
      tx.conversions.map((c) => [
        String(c.year),
        String(c.age),
        dollarsWhole(c.amount),
        dollarsWhole(c.tax),
        `${pct0(c.bracket_rate)} bracket`,
      ]),
    ),
    "Roth conversions by year equal the API's (Year, Age, Convert, Tax, Fills)",
  );

  // --- Retirement income
  await openTab(page, "Retirement income");
  const rt = pf.retirement;
  check(
    eq(
      (await page.getByTestId("income-table").locator("thead th").allInnerTexts()).map((s) => s.trim()),
      ["Age", "Social Security", "From 401(k) / IRA", "From brokerage", "From Roth", "Tax", "Spending"],
    ),
    "income table columns as the mockup",
  );
  check(
    eq(
      await tableRows(page.getByTestId("income-table")),
      rt.rows.map((r) => [
        String(r.age),
        dash(r.social_security),
        dash(r.from_pretax),
        dash(r.from_taxable),
        dash(r.from_roth),
        dash(r.tax),
        dash(r.spending),
      ]),
    ),
    "income table equals the API's",
  );
  check(
    eq(await page.getByTestId("withdrawal-order").locator("li").allInnerTexts(), rt.withdrawal_order),
    "withdrawal order (a numbered list) equals the API's",
  );
  check((await page.getByTestId("withdrawal-order").evaluate((e) => e.tagName)) === "OL", "it is an ordered list");
  const req = (await page.getByTestId("required").innerText()).replace(/\s+/g, " ");
  const covered = rt.required.first_amount < 0.5 ? rt.required.note : rt.required.covered ? "Yes" : "No";
  check(
    req.includes(`Start at age ${rt.required.start_age}`) &&
      req.includes(`First required amount ${dash(rt.required.first_amount)}`) &&
      req.includes(`Already covered by planned withdrawals ${covered}`),
    `required withdrawals equal the API's (covered: ${covered})`,
  );

  // --- Goals
  await openTab(page, "Goals");
  const cards = await page
    .getByTestId("goal-cards")
    .locator("li")
    .evaluateAll((lis) =>
      lis.map((li) => ({
        label: li.querySelector("h2").innerText,
        timing: li.querySelector("p").innerText,
        target: li.querySelector("b").innerText,
        now: +li.querySelector('[role="progressbar"]').getAttribute("aria-valuenow"),
        status: li.querySelector("span[data-status]").innerText,
      })),
    );
  check(
    eq(
      cards.map((c) => [c.label, c.timing, c.target, c.now, c.status]),
      pf.goals.cards.map((c) => [c.label, c.timing, c.target_label, c.progress, c.status]),
    ),
    `${cards.length} goal cards equal the API's (label, timing, amount, progress, status)`,
  );
  const goalBoxes = await page
    .getByTestId("goal-cards")
    .locator("li")
    .evaluateAll((l) => l.map((e) => e.getBoundingClientRect().y));
  check(
    goalBoxes.every((y0) => Math.abs(y0 - goalBoxes[0]) < 2),
    "the goal cards are in one row",
  );

  // --- wording, disclaimer, layout
  await page.getByRole("tab", { name: "Overview" }).click();
  const { text: body, attrs, title } = await visibleText(page);
  const all = [body, ...attrs].join("\n").replace(DISCLAIMER, "");
  check(
    !/\bplans?\b|\bmodels?\b|simulat|donabach|gracchi|tanaka|\bAI\b|predict|learned|trained|checklist|to-do|todo/i.test(
      all,
    ),
    "no plan/model/simulation/checklist wording",
  );
  check(body.split(DISCLAIMER).length === 2, "exactly one disclaimer");
  check(title === "Waramoug", "tab title Waramoug");
  check(
    (await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 0,
    "no sideways scrolling at 1440",
  );
  check(issues.length === 0, `no console errors (${issues.join(" | ")})`);
  await page.setViewportSize({ width: 800, height: 900 });
  check(
    (await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 0,
    "no sideways scrolling at 800",
  );
  const cols = await page.getByTestId("mix-table").evaluate((e) => e.closest("section").getBoundingClientRect().width);
  check(cols > 500, "under 900px the two-column row stacks");
  await context.close();

  // --- What changed after job loss (a fresh customer: first portfolio, then a change)
  {
    const s = await newPage(browser);
    const p = s.page;
    await toInvest(p, base);
    await p.getByRole("button", { name: "Back" }).click();
    await p.waitForURL("**/goals");
    await p.getByRole("radio", { name: "Job loss next year" }).check();
    await p.getByRole("button", { name: "Invest", exact: true }).click();
    await p.waitForURL("**/invest");
    await p.getByTestId("what-changed").waitFor();
    const jl = await planFromApi(base, {
      patch: { income_change: "job_loss" },
      event: "job_loss",
      previous: plan.plan_id,
      label: "Income: job loss next year",
    });
    const wc = jl.what_changed;
    const w = (await p.getByTestId("what-changed").innerText()).replace(/\s+/g, " ");
    check(w.includes(wc.changed), `What changed names the change: ${wc.changed}`);
    const convLabel = `Roth conversion at ${wc.conversion_age}`;
    check(
      w.includes(`${convLabel} ${dollarsWhole(wc.conversion_before)} → ${dollarsWhole(wc.conversion_after)}`),
      `What changed: ${convLabel} ${dollarsWhole(wc.conversion_before)} → ${dollarsWhole(wc.conversion_after)}`,
    );
    check(
      w.includes(`Projected at 80 ${wealthM(wc.wealth_before)} → ${wealthM(wc.wealth_after)}`),
      "What changed: Projected at 80, before → after",
    );
    check(
      (await p.getByTestId("change-mix").count()) === wc.mix.filter((m) => m.moved).length,
      "no mix cells when no class moved",
    );
    // the move named like the conversion cell is not shown twice
    const shownMoves = wc.moves.filter((m) => m.title !== convLabel);
    check(
      (await p.getByTestId("change-move").count()) === shownMoves.length &&
        shownMoves.every((m) => w.includes(m.title)),
      "What changed: one cell per other changed move",
    );
    const bronze = await p.getByTestId("what-changed").evaluate((e) => {
      const st = getComputedStyle(e);
      return [st.borderTopWidth, st.borderTopColor, st.borderRadius];
    });
    check(
      bronze[0] === "2px" && bronze[1] === "rgb(138, 100, 64)" && bronze[2] === "16px",
      `the box: 2px bronze border, 16px radius (${bronze})`,
    );
    check(
      (await p
        .getByTestId("what-changed")
        .evaluate(
          (e) =>
            e.compareDocumentPosition(document.querySelector('[data-testid="summary"]')) &
            Node.DOCUMENT_POSITION_FOLLOWING,
        )) > 0,
      "What changed sits above the summary",
    );
    check(
      (await p.getByTestId("projected-wealth").innerText()) === wealthM(jl.portfolio.summary.projected_wealth),
      "the strip follows the rebuilt portfolio",
    );
    check(
      (await p.locator('[data-move="conversion_next"] [data-status]').innerText()) === "Needs your OK" &&
        (await p
          .locator('[data-move="conversion_next"]')
          .getByRole("button", { name: /^Approve/ })
          .count()) === 1,
      "the new, larger conversion needs your OK again (Approve visible)",
    );
    check(
      (await p.locator('[data-move="conversion_next"]').innerText()).includes(dollarsWhole(wc.conversion_after)),
      "its amount is the new one",
    );
    check(
      (await p
        .locator('[data-move="conversion_next"] span')
        .filter({ hasText: /^Changed$/ })
        .count()) === 1,
      "the changed move row carries a Changed tag",
    );
    check(
      (await p
        .locator('[data-move="conversion"] span')
        .filter({ hasText: /^Changed$/ })
        .count()) === 0,
      "an unchanged move does not",
    );
    check(s.issues.length === 0, `no console errors after the change (${s.issues.join(" | ")})`);
    await s.context.close();
  }
  // --- a change that moves the mix (retirement age 65): rows and bar segments carry marks
  {
    const s = await newPage(browser);
    const p = s.page;
    await toInvest(p, base);
    await p.getByRole("button", { name: "Back" }).click();
    await p.waitForURL("**/goals");
    await p.getByRole("radio", { name: "65", exact: true }).check();
    await p.getByRole("button", { name: "Invest", exact: true }).click();
    await p.waitForURL("**/invest");
    await p.getByTestId("what-changed").waitFor();
    const r = await planFromApi(base, {
      patch: { retirement_age: 65 },
      previous: plan.plan_id,
      label: "Retirement age: 65",
    });
    const moved = r.what_changed.mix.filter((m) => m.moved);
    check(
      (await p.getByTestId("change-mix").count()) === moved.length,
      `What changed lists the ${moved.length} class(es) that moved`,
    );
    check(
      (await p.locator('[data-testid="mix-bar"] [data-changed]').count()) === moved.length,
      "the moved mix segments are marked",
    );
    check(
      (await p.getByTestId("mix-table").locator("tbody tr").filter({ hasText: "Changed" }).count()) === moved.length &&
        (await p.getByTestId("location-table").locator("tbody tr").filter({ hasText: "Changed" }).count()) ===
          moved.length,
      "the moved mix rows are tagged Changed",
    );
    await s.context.close();
  }
}

if (isMain(import.meta.url)) await runAlone(runInvest, "invest");
