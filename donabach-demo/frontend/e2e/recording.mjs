// The recorded flow, in order and timed: Documents, drop the PDF, Reading, Review (click a field, confirm), Goals, Invest, Approve,
// Compare, Back, Back, job loss, Invest with "What changed". Prints a table of how long each step took (from the click to the next
// screen being interactive) and asserts the plan steps (4, 6, 8) take under 1.5 s and the Reading step under 6 s.
// Only path.join / fileURLToPath for file paths and no shell commands, so it runs the same on Windows.
import { isMain, runAlone, newPage, apiGet, dollarsWhole, PDF_BYTES } from "./portal.mjs";
import {
  wealthM,
  dash,
  pct0,
  pctTrim,
  signedPct2,
  tableRows,
  listRows,
  moveText,
  STATUS,
  planFromApi,
} from "./invest-lib.mjs";

const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
/** Every figure on the Invest Overview against the API's plan (strip, mix, what goes where, moves, what changed). */
async function overviewEqualsPlan(page, plan, check, label, approved = []) {
  const pf = plan.portfolio;
  const t = (id) => page.getByTestId(id).innerText();
  check(
    (await t("projected-wealth")) === wealthM(pf.summary.projected_wealth) &&
      (await t("invested-today")) === dollarsWhole(pf.summary.invested_today) &&
      (await t("yearly-fee")) === dollarsWhole(pf.summary.fee_dollars) &&
      (await t("tax-saved")) === dollarsWhole(pf.summary.tax_saved),
    `${label}: the summary strip equals the API's (${wealthM(pf.summary.projected_wealth)})`,
  );
  const mix = pf.overview.mix.rows.map((r) =>
    r.amount < 0.5
      ? [r.label, "–", "–", "–"]
      : [r.label, dollarsWhole(r.amount), pct0(r.share), pctTrim(r.expected_return)],
  );
  check(eq(await tableRows(page.getByTestId("mix-table")), mix), `${label}: the mix table equals the API's`);
  const loc = pf.overview.location.rows.map((r) => [r.label, dash(r.brokerage), dash(r.pretax), dash(r.roth)]);
  check(eq(await tableRows(page.getByTestId("location-table")), loc), `${label}: what goes where equals the API's`);
  const shown = await listRows(page.getByTestId("moves-list"));
  // a move that changed also carries the "Changed" tag after its words
  const moves = shown.map(([pill, words, when]) => [pill, words.replace(/\s*Changed$/, ""), when]);
  // a move the customer approved shows as Scheduled, with its timing
  const want = pf.overview.moves.map((m) => [
    approved.includes(m.key) ? STATUS.scheduled : STATUS[m.status],
    moveText(m).replace(/\s+/g, " "),
    m.status === "needs_ok" && !approved.includes(m.key) ? `${m.timing} Approve` : m.timing,
  ]);
  check(eq(moves, want), `${label}: this year's moves equal the API's`);
}

export async function runRecording({ browser, base, check, notes }) {
  const times = [];
  const timed = async (step, limit, fn) => {
    const t0 = Date.now();
    await fn();
    const ms = Date.now() - t0;
    times.push([step, ms]);
    if (limit) check(ms < limit, `${step}: ${ms} ms (under ${limit} ms)`);
    return ms;
  };
  const defaults = await apiGet(base, "/portal/defaults");
  void defaults;
  const base0 = await planFromApi(base);
  const jl = await planFromApi(base, {
    patch: { income_change: "job_loss" },
    event: "job_loss",
    previous: base0.plan_id,
    label: "Income: job loss next year",
  });
  const { context, page, issues } = await newPage(browser);

  // 1. open Documents
  await timed("1 Open Documents", 0, async () => {
    await page.goto(`${base}/`, { waitUntil: "load" });
    await page.getByTestId("drop-area").waitFor();
  });

  // 2. drop smith_documents.pdf (DataTransfer events); Reading runs and moves to Review on its own
  await timed("2 Drop the PDF, Reading, Review", 6000, async () => {
    const data = await page.evaluateHandle(
      (bytes) => {
        const dt = new DataTransfer();
        dt.items.add(new File([new Uint8Array(bytes)], "smith_documents.pdf", { type: "application/pdf" }));
        return dt;
      },
      [...PDF_BYTES],
    );
    await page.dispatchEvent('[data-testid="drop-area"]', "dragover", { dataTransfer: data });
    await page.dispatchEvent('[data-testid="drop-area"]', "drop", { dataTransfer: data });
    await page.waitForURL("**/reading", { timeout: 10_000 });
    await page.waitForURL("**/review", { timeout: 15_000 });
    await page.locator("[data-field-key]").first().waitFor();
  });

  // 3. Review: click one field (its source highlights), confirm the flagged field, Confirm and continue
  await page.locator('[data-field-key="w2_wages_taxpayer"] label').click();
  await page.waitForTimeout(500);
  check(
    (await page.locator('[data-testid="highlight"]').count()) === 1,
    "3 Review: the field's source is highlighted on the preview",
  );
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await timed("3 Confirm and continue, Goals", 0, async () => {
    await page.getByRole("button", { name: "Confirm and continue" }).click();
    await page.waitForURL("**/goals");
    await page.getByRole("radio", { name: "60", exact: true }).waitFor();
  });

  // 4. Goals: Invest with John Smith's values unchanged
  await timed("4 Invest (first portfolio)", 1500, async () => {
    await page.getByRole("button", { name: "Invest", exact: true }).click();
    await page.waitForURL("**/invest", { timeout: 60_000 });
    await page.getByRole("tablist", { name: "Invest sections" }).waitFor();
    await page.getByTestId("projected-wealth").waitFor();
  });

  // 5. Invest: the Overview, then Approve on the Roth conversion
  await overviewEqualsPlan(page, base0, check, "5 Invest");
  check((await page.getByTestId("what-changed").count()) === 0, "5 Invest: no What changed on the first portfolio");
  const row = page.locator('[data-move="conversion"]');
  await timed("5 Approve the Roth conversion", 0, async () => {
    await row.getByRole("button", { name: /^Approve/ }).click();
    await page.locator('[data-move="conversion"] [data-status="scheduled"]').waitFor();
  });
  check((await row.getByRole("button").count()) === 0, "5 Invest: Approve is gone once approved");

  // 6. Compare
  await timed("6 Compare", 1500, async () => {
    await page.getByRole("button", { name: "Compare" }).click();
    await page.waitForURL("**/compare");
    await page.getByTestId("dollars-more").waitFor();
  });
  const cmp = base0.comparison;
  check(
    (await page.getByTestId("wealth-waramoug").innerText()) === wealthM(cmp.waramoug.wealth_80) &&
      (await page.getByTestId("wealth-advisor").innerText()) === wealthM(cmp.advisor.wealth_80),
    `6 Compare: ${wealthM(cmp.waramoug.wealth_80)} vs ${wealthM(cmp.advisor.wealth_80)}`,
  );
  check(
    (await page.getByTestId("dollars-more").innerText()) === `${wealthM(cmp.dollars_more)} more at 80`,
    `6 Compare: ${wealthM(cmp.dollars_more)} more at 80`,
  );
  check(
    (await page.getByTestId("rate-per-year").innerText()) === `${signedPct2(cmp.rate_per_year)} a year`,
    `6 Compare: ${signedPct2(cmp.rate_per_year)} a year`,
  );

  // 7. Back, then Back to Goals; choose "Job loss next year"
  await timed("7 Back to Invest, Back to Goals", 0, async () => {
    await page.getByRole("button", { name: "Back" }).click();
    await page.waitForURL("**/invest");
    await page.getByRole("button", { name: "Back" }).click();
    await page.waitForURL("**/goals");
    await page.getByRole("radio", { name: "Job loss next year" }).waitFor();
  });
  await page.getByRole("radio", { name: "Job loss next year" }).check();

  // 8. Invest: the rebuilt portfolio with What changed
  await timed("8 Invest (job loss, rebuilt)", 1500, async () => {
    await page.getByRole("button", { name: "Invest", exact: true }).click();
    await page.waitForURL("**/invest", { timeout: 60_000 });
    await page.getByTestId("what-changed").waitFor();
  });
  const wc = jl.what_changed;
  const w = (await page.getByTestId("what-changed").innerText()).replace(/\s+/g, " ");
  check(
    w.includes(
      `Roth conversion at ${wc.conversion_age} ${dollarsWhole(wc.conversion_before)} → ${dollarsWhole(wc.conversion_after)}`,
    ),
    `8 What changed: Roth conversion at ${wc.conversion_age} ${dollarsWhole(wc.conversion_before)} → ${dollarsWhole(wc.conversion_after)}`,
  );
  check(
    w.includes(wc.changed) && w.includes(`Projected at 80 ${wealthM(wc.wealth_before)} → ${wealthM(wc.wealth_after)}`),
    "8 What changed: the change and the wealth before and after",
  );
  const next = page.locator('[data-move="conversion_next"]');
  check(
    (await next.locator("[data-status]").innerText()) === "Needs your OK" &&
      (await next.getByRole("button", { name: /^Approve/ }).count()) === 1,
    "8 Invest: the larger conversion shows Needs your OK again, Approve visible",
  );
  const nextTiming = jl.portfolio.overview.moves.find((m) => m.key === "conversion_next").timing;
  check(
    (await next.innerText()).replace(/\s+/g, " ").includes(nextTiming),
    `8 Invest: the changed conversion shows its timing, "${nextTiming}", beside Approve`,
  );
  const now = page.locator('[data-move="conversion"]');
  check(
    (await now.locator("[data-status]").innerText()) === "Scheduled" && (await now.getByRole("button").count()) === 0,
    "8 Invest: the conversion approved before the change, which the new plan leaves as it was, stays Scheduled",
  );
  await overviewEqualsPlan(page, jl, check, "8 Invest", ["conversion"]);
  check(issues.length === 0, `no console errors in the flow (${issues.join(" | ")})`);
  await context.close();

  const width = Math.max(...times.map(([s]) => s.length));
  notes.push("step timings (click to the next screen interactive):");
  for (const [s, ms] of times) notes.push(`  ${s.padEnd(width)}  ${String(ms).padStart(6)} ms`);
}

if (isMain(import.meta.url)) await runAlone(runRecording, "recording");
