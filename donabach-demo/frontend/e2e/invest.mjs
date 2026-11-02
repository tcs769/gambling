// Invest (/invest): the summary strip, the five tabs (keyboard), every table against the API's plan, the location shading, Approve,
// no plan/model wording, the one disclaimer, and What changed (absent on the first portfolio, present after job loss).
import { isMain, runAlone, newPage, visibleText, dollarsWhole } from "./portal.mjs";
import {
  DISCLAIMER,
  wealthM,
  dash,
  pct0,
  pctTrim,
  feeLine,
  tableRows,
  footRows,
  planFromApi,
  toInvest,
  openTab,
} from "./invest-lib.mjs";

const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const STATUS = {
  done: "Done",
  ongoing: "Ongoing",
  scheduled: "Scheduled",
  needs_ok: "Needs your OK",
  your_step: "Your step",
};

export async function runInvest({ browser, base, check }) {
  const plan = await planFromApi(base);
  const pf = plan.portfolio;
  const { context, page, issues } = await newPage(browser);
  await toInvest(page, base);
  const text = (id) => page.getByTestId(id).innerText();

  // --- the strip
  check((await page.locator("h1").innerText()) === "Invest", "the page title is Invest");
  check(
    (await text("projected-wealth")) === wealthM(pf.summary.projected_wealth),
    `strip: projected wealth ${wealthM(pf.summary.projected_wealth)}`,
  );
  check(
    (await text("invested-today")) === dollarsWhole(pf.summary.invested_today),
    "strip: invested today equals the API's",
  );
  check(
    (await text("yearly-fee")) === feeLine(pf.summary.fee_dollars, pf.summary.fee_rate),
    `strip: yearly fee ${feeLine(pf.summary.fee_dollars, pf.summary.fee_rate)}`,
  );
  check((await text("tax-saved")) === dollarsWhole(pf.summary.tax_saved), "strip: tax saved equals the API's");
  const labels = await page.getByTestId("summary").innerText();
  for (const l of ["Projected wealth at 80", "Invested today", "Yearly fee", "Estimated tax saved this year"])
    check(labels.includes(l), `strip label "${l}"`);
  const serif = await page.getByTestId("projected-wealth").evaluate((el) => getComputedStyle(el).fontFamily);
  check(/Cambria/.test(serif), "the large figure is in the serif face");
  check((await page.getByTestId("what-changed").count()) === 0, "no What changed block on the first portfolio");
  check(
    (await page.locator("[data-plan-id]").getAttribute("data-plan-id")) === plan.plan_id,
    "the page shows the API's plan",
  );

  // --- tabs: roles, arrow keys, hash
  const tabs = page.getByRole("tab");
  check(
    eq(await tabs.allInnerTexts(), ["Overview", "Holdings", "Taxes", "Retirement income", "Goals"]),
    "five tabs: Overview, Holdings, Taxes, Retirement income, Goals",
  );
  await page.getByRole("tab", { name: "Overview" }).focus();
  await page.keyboard.press("ArrowRight");
  check(
    (await page.getByRole("tablist", { name: "Invest sections" }).getByRole("tab", { selected: true }).innerText()) ===
      "Holdings",
    "ArrowRight moves to Holdings",
  );
  check((await page.evaluate(() => document.activeElement?.textContent)) === "Holdings", "and focus follows");
  await page.keyboard.press("End");
  check(
    (await page.getByRole("tablist", { name: "Invest sections" }).getByRole("tab", { selected: true }).innerText()) ===
      "Goals",
    "End goes to the last tab",
  );
  await page.keyboard.press("ArrowRight");
  check(
    (await page.getByRole("tablist", { name: "Invest sections" }).getByRole("tab", { selected: true }).innerText()) ===
      "Overview",
    "ArrowRight wraps to Overview",
  );
  await page.keyboard.press("ArrowLeft");
  check(
    (await page.getByRole("tablist", { name: "Invest sections" }).getByRole("tab", { selected: true }).innerText()) ===
      "Goals",
    "ArrowLeft wraps back",
  );
  check(new URL(page.url()).hash === "#goals", "the tab is in the URL hash");
  check((await text("projected-wealth")) === wealthM(pf.summary.projected_wealth), "the strip stays above every tab");
  await page.getByRole("tab", { name: "Overview" }).click();

  // --- Overview
  const ov = pf.overview;
  check(
    (await page.getByTestId("projection-chart").locator("svg.recharts-surface").count()) > 0,
    "the wealth chart draws",
  );
  check((await page.locator(".recharts-line-curve").count()) === 1, "the chart has one line");
  const lines = await page.locator(".recharts-reference-line").count();
  const bands = await page.locator(".recharts-reference-area").count();
  check(
    bands === ov.markers.filter((m) => m.end_age !== null).length &&
      lines === ov.markers.filter((m) => m.end_age === null).length,
    `markers: ${bands} band(s), ${lines} line(s)`,
  );
  const chartText = await page.getByTestId("projection-chart").innerText();
  check(
    ov.markers.every((m) => chartText.includes(m.label)),
    "each marker has its label",
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

  const mixRows = await tableRows(page.getByTestId("mix-table"));
  check(
    eq(
      mixRows,
      ov.mix.rows.map((r) =>
        r.amount < 0.5
          ? [r.label, "—", "—", "—"]
          : [r.label, dollarsWhole(r.amount), pct0(r.share), pctTrim(r.expected_return)],
      ),
    ),
    "mix table equals the API's (empty classes show a dash)",
  );
  const segs = await page.getByTestId("mix-bar").first().locator("span").count();
  check(
    segs === ov.mix.rows.filter((r) => r.share >= 0.0005).length,
    `the mix bar has ${segs} segments (classes with money)`,
  );

  const loc = page.getByTestId("location-table");
  const locRows = await tableRows(loc);
  check(
    eq(
      locRows,
      ov.location.rows.map((r) => [r.label, dash(r.brokerage), dash(r.pretax), dash(r.roth), dash(r.total)]),
    ),
    "what goes where equals the API's",
  );
  const t = ov.location.total;
  check(
    eq((await footRows(loc))[0], ["Total", dash(t.brokerage), dash(t.pretax), dash(t.roth), dash(t.total)]),
    "and so does its total row",
  );
  const shades = await loc.locator("tbody td").evaluateAll((cells) =>
    cells.map((c) => {
      const m = getComputedStyle(c).backgroundColor.match(/rgba?\(([^)]+)\)/);
      const parts = m ? m[1].split(",").map(Number) : [0, 0, 0, 0];
      return { text: c.innerText.trim(), alpha: parts.length === 4 ? parts[3] : 1 };
    }),
  );
  const cells = shades.filter((_, i) => i % 4 !== 3);
  const dollars = cells.filter((c) => c.text !== "—");
  const biggest = dollars.reduce((a, b) => (+b.text.replace(/\D/g, "") > +a.text.replace(/\D/g, "") ? b : a));
  check(dollars.length > 0 && dollars.every((c) => c.alpha > 0), "location: every money cell is shaded");
  check(
    cells.filter((c) => c.text === "—").every((c) => c.alpha === 0),
    "location: $0 cells have no shade",
  );
  check(
    dollars.every((c) => c.alpha <= biggest.alpha) && biggest.alpha > 0.2,
    `location: the largest cell is the darkest (alpha ${biggest.alpha})`,
  );

  const moves = page.getByTestId("moves-table");
  const moveRows = await tableRows(moves);
  const expectMoves = ov.moves.map((m) => [
    m.title,
    m.amount === null ? "—" : `${dollarsWhole(m.amount)}${m.detail ?? ""}`,
    m.timing,
    STATUS[m.status],
  ]);
  const shown = moveRows.map((r) => r.map((c) => c.replace(/\s*Approve$/, "")));
  check(
    eq(
      shown.map((r) => [r[0], r[1].replace(/\s+/g, ""), r[2], r[3]]),
      expectMoves.map((r) => [r[0], r[1].replace(/\s+/g, ""), r[2], r[3]]),
    ),
    "this year's moves equal the API's (move, amount and detail, when, status)",
  );
  const approveBtns = page.getByRole("button", { name: /^Approve/ });
  const needs = ov.moves.filter((m) => m.status === "needs_ok").length;
  check((await approveBtns.count()) === needs, `Approve shows on the ${needs} move(s) that need an OK`);
  const iconsOk = await moves
    .locator("[data-status]")
    .evaluateAll((els) => els.every((e) => e.querySelector("svg") && e.textContent.trim().length > 3));
  check(iconsOk, "every status has an icon and text");

  // Approve persists
  const row = page.locator('[data-move="conversion"]');
  await row.getByRole("button", { name: /^Approve/ }).click();
  check((await row.locator("[data-status]").innerText()) === "Scheduled", "Approve changes the status to Scheduled");
  check((await row.getByRole("button").count()) === 0, "and the button is gone");
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
  for (const acct of h.accounts) {
    await page.getByRole("tab", { name: acct.label, exact: true }).click();
    const panel = page.getByTestId(`account-${acct.key}`);
    check(
      (await panel.getByTestId("account-balance").innerText()) === dollarsWhole(acct.balance),
      `${acct.label}: balance`,
    );
    const ptext = await panel.locator("dl").innerText();
    check(ptext.includes(acct.taxation), `${acct.label}: taxed "${acct.taxation}"`);
    if (acct.cost_basis !== null)
      check(
        ptext.includes(dollarsWhole(acct.cost_basis)) && ptext.includes(dollarsWhole(acct.unrealized_gain)),
        `${acct.label}: cost basis and unrealized gain`,
      );
    else check(!/Cost basis/.test(ptext), `${acct.label}: no cost basis`);
    const rows = await tableRows(panel.getByTestId("holdings-table"));
    check(
      eq(
        rows,
        acct.holdings.map((r) => [
          r.name,
          String(r.positions),
          dollarsWhole(r.value),
          r.gain !== null ? dollarsWhole(r.gain) : r.yield_rate !== null ? `${pctTrim(r.yield_rate)} yield` : "—",
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
  for (const [id, rows] of [
    ["bars-stocks-by-sector", h.sectors],
    ["bars-stocks-by-region", h.regions],
  ]) {
    const items = await page.getByTestId(id).locator("li").allInnerTexts();
    check(
      eq(
        items.map((s) => s.replace(/\s+/g, " ")),
        rows.map((r) => `${r.label} ${pctTrim(r.share)} ${dollarsWhole(r.amount)}`),
      ),
      `${id}: label, share and amount equal the API's`,
    );
  }
  check(
    (await page.getByText("Illustrative", { exact: true }).count()) === (h.illustrative ? 2 : 0),
    "two Illustrative tags (sector and region)",
  );

  // --- Taxes
  await openTab(page, "Taxes");
  const tx = pf.taxes;
  const y = tx.this_year;
  const yearText = await page.getByTestId("taxes-year").innerText();
  const want = [
    ["Roth conversion", y.roth_conversion],
    ["Tax on the conversion", y.conversion_tax],
    ["Losses harvested", y.losses_harvested],
    ["Gains offset", y.gains_offset],
    ["Deducted from income", y.deducted_from_income],
    ["Interest kept out of taxable accounts", y.interest_kept_out],
    ["Estimated tax saved", y.tax_saved],
  ];
  const flat = yearText.replace(/\s+/g, " ");
  check(
    want.every(([l, v]) => flat.includes(`${l} ${dollarsWhole(v)}`)),
    "taxes this year: every row equals the API's",
  );
  check(y.carried_forward > 0 === flat.includes("Carried forward"), "carried forward only when above 0");
  const filled = await page.locator('[data-testid="bracket-bar"] [data-filled]').getAttribute("data-rate");
  check(+filled === tx.bracket.brackets.find((b) => b.filled).rate, "the filled bracket is highlighted");
  check(
    (await page.locator('[data-testid="bracket-bar"] > div').count()) === tx.bracket.brackets.length,
    "one segment per bracket",
  );
  const bv = (await page.getByTestId("bracket-values").innerText()).replace(/\s+/g, " ");
  const b = tx.bracket;
  check(
    [
      ["Taxable income before the conversion", dollarsWhole(b.taxable_before)],
      ["The conversion", dollarsWhole(b.conversion)],
      ["Fills to", dollarsWhole(b.fills_to)],
      ["Marginal rate", pctTrim(b.marginal_rate)],
      ["Illinois tax on the conversion", dollarsWhole(b.illinois_tax_on_conversion)],
    ].every(([l, v]) => bv.includes(`${l} ${v}`)),
    "bracket values equal the API's",
  );
  if (tx.opportunities.length === 0)
    check(
      (await page.getByTestId("no-opportunities").innerText()) === "No positions below cost",
      "no opportunities: one quiet line",
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
        pct0(c.bracket_rate),
      ]),
    ),
    "Roth conversions by year equal the API's",
  );

  // --- Retirement income
  await openTab(page, "Retirement income");
  const rt = pf.retirement;
  check(
    eq(
      await tableRows(page.getByTestId("income-table")),
      rt.rows.map((r) => [
        String(r.age),
        String(r.year),
        dash(r.social_security),
        dash(r.from_pretax),
        dash(r.from_taxable),
        dash(r.from_roth),
        dollarsWhole(r.total_sources),
        dollarsWhole(r.spending),
        dash(r.tax),
        dollarsWhole(r.total_uses),
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
  check(
    req.includes(`Starting age ${rt.required.start_age}`) &&
      req.includes(`First required amount ${dollarsWhole(rt.required.first_amount)}`),
    "required withdrawals equal the API's",
  );
  check((await page.getByText(rt.required.note, { exact: true }).count()) === 1, "and the API's note is shown");

  // --- Goals
  await openTab(page, "Goals");
  const cards = await page
    .getByTestId("goal-cards")
    .locator("li")
    .evaluateAll((lis) =>
      lis.map((li) => ({
        label: li.querySelector("h2").innerText,
        target: li.querySelector("p").innerText,
        now: +li.querySelector('[role="progressbar"]').getAttribute("aria-valuenow"),
        status: li.querySelector("p[data-status]").innerText,
      })),
    );
  check(
    eq(
      cards.map((c) => [c.label, c.target, c.now, c.status]),
      pf.goals.cards.map((c) => [c.label, c.target_label, c.progress, c.status]),
    ),
    "goal cards equal the API's (label, target, progress, status)",
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
    check(
      w.includes(
        `Roth conversion at ${wc.conversion_age}: ${dollarsWhole(wc.conversion_before)} → ${dollarsWhole(wc.conversion_after)}`,
      ),
      `What changed: Roth conversion at ${wc.conversion_age}: ${dollarsWhole(wc.conversion_before)} → ${dollarsWhole(wc.conversion_after)}`,
    );
    check(
      w.includes(`Projected wealth at 80: ${wealthM(wc.wealth_before)} → ${wealthM(wc.wealth_after)}`),
      "What changed: projected wealth before → after",
    );
    check(
      (await p.getByTestId("change-mix").count()) === wc.mix.filter((m) => m.moved).length,
      "no mix lines when no class moved",
    );
    check(
      (await p.getByTestId("change-move").count()) === wc.moves.length &&
        wc.moves.every((m) => w.includes(m.title) && w.includes(m.after ?? "")),
      "What changed: the moves that changed",
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
      (await p.locator('[data-move="conversion_next"] td').first().innerText()).includes(
        dollarsWhole(wc.conversion_after),
      ),
      "its amount is the new one",
    );
    check(
      (await p.locator("[data-move].changedRow, [data-move] .tag").count()) >= 1 ||
        (await p.locator('[data-move="conversion_next"] span').filter({ hasText: "Changed" }).count()) === 1,
      "the changed move row carries a Changed tag",
    );
    check(
      (await p.locator('[data-move="conversion"] span').filter({ hasText: "Changed" }).count()) === 0,
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
      (await p.getByTestId("mix-table").locator("tbody tr").filter({ hasText: "Changed" }).count()) === moved.length,
      "the moved mix rows are tagged Changed",
    );
    await s.context.close();
  }
}

if (isMain(import.meta.url)) await runAlone(runInvest, "invest");
