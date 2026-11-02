// Goals (/goals): the questions prefilled with the API's defaults, tap-to-select chips with an "Other" input, the income-change question,
// and what Invest sends (household, then invest with the event, the previous plan and the words for what changed).
import { isMain, runAlone, newPage, apiGet, toGoals, toReview, dollarsWhole } from "./portal.mjs";

const checked = (page, legend) => page.getByRole("group", { name: legend }).locator("input:checked + span").innerText();
const options = (page, legend) => page.getByRole("group", { name: legend }).locator("label").allInnerTexts();
const plural = (n, u) => `${n} ${u}${n === 1 ? "" : "s"}`;

/** Press Invest and return what was sent and answered. */
async function invest(page) {
  const sent = { household: null, invest: null };
  const answered = { invest: null };
  const onRequest = (r) => {
    if (r.url().includes("/api/portal/household")) sent.household = JSON.parse(r.postData());
    if (r.url().includes("/api/portal/invest")) sent.invest = JSON.parse(r.postData());
  };
  const onResponse = async (r) => {
    if (r.url().includes("/api/portal/invest")) answered.invest = await r.json();
  };
  page.on("request", onRequest);
  page.on("response", onResponse);
  await page.getByRole("button", { name: "Invest", exact: true }).click();
  await page.waitForURL("**/invest", { timeout: 60_000 });
  await page.waitForTimeout(200);
  page.off("request", onRequest);
  page.off("response", onResponse);
  return { sent, answered };
}

export async function runGoals({ browser, base, check }) {
  const d = await apiGet(base, "/portal/defaults");
  const { context, page, issues } = await newPage(browser);
  await toGoals(page, base);

  // --- prefilled with the defaults
  check(
    (await checked(page, "Retirement age")) === String(d.retirement_age),
    `retirement age is ${d.retirement_age}, the API's default`,
  );
  check(
    (await checked(page, "Retirement spending a year")) === dollarsWhole(d.retirement_spending),
    `retirement spending is ${dollarsWhole(d.retirement_spending)}`,
  );
  const john = `In ${plural(d.college_starts_in_years, "year")}, ${dollarsWhole(d.college_annual_cost)} a year for ${plural(d.college_years, "year")}`;
  check((await checked(page, "College")) === john, `college is "${john}"`);
  check(
    d.home_purchase_in_years === null && (await checked(page, "Home purchase")) === "None planned",
    "home purchase is None planned",
  );
  check((await checked(page, "Any income changes coming?")) === "No", "income changes: No is selected");

  // --- the chips
  check(
    JSON.stringify(await options(page, "Retirement age")) ===
      JSON.stringify(["55", "58", "60", "62", "65", "67", "70", "Other"]),
    "retirement age chips: 55 58 60 62 65 67 70 Other",
  );
  check(
    JSON.stringify(await options(page, "Retirement spending a year")) ===
      JSON.stringify(["$75,000", dollarsWhole(d.retirement_spending), "$105,000", "$120,000", "Other"]),
    "spending chips: $75,000, $90,015, $105,000, $120,000, Other",
  );
  check(
    JSON.stringify(await options(page, "College")) === JSON.stringify(["None", john, "Other"]),
    "college: None, John's, Other",
  );
  check(
    JSON.stringify(await options(page, "Home purchase")) ===
      JSON.stringify(["None planned", "Within 3 years, $150,000 down payment", "Other"]),
    "home: None planned, Within 3 years, Other",
  );
  check(
    JSON.stringify(await options(page, "Any income changes coming?")) ===
      JSON.stringify(["No", "Job loss next year", "A raise"]),
    "income: No, Job loss next year, A raise",
  );

  // --- tapping selects, Other opens a value box
  await page.getByRole("radio", { name: "65", exact: true }).check();
  check((await checked(page, "Retirement age")) === "65", "tapping 65 selects it");
  await page.getByRole("group", { name: "Retirement age" }).getByRole("radio", { name: "Other" }).check();
  const other = page.getByLabel("Retirement age, other");
  check(await other.isVisible(), "Other opens a value box");
  await other.fill("62");
  await other.press("Enter");
  check(
    (await checked(page, "Retirement age")) === "Other" && (await other.inputValue()) === "62",
    "an Other value stays under Other",
  );
  await page.getByRole("radio", { name: "60", exact: true }).check();
  await page.getByRole("group", { name: "Home purchase" }).getByRole("radio", { name: "Other" }).check();
  check(
    (await page.getByLabel("Home purchase in years, other").isVisible()) &&
      (await page.getByLabel("Home down payment, other").isVisible()),
    "home Other asks for years and a down payment",
  );
  await page.getByRole("radio", { name: "None planned" }).check();
  await page.getByRole("group", { name: "College" }).getByRole("radio", { name: "Other" }).check();
  check(
    await page.getByLabel("College starts in years, other").isVisible(),
    "college Other asks for start, cost and years",
  );
  await page.getByRole("radio", { name: john }).check();
  check((await checked(page, "College")) === john, "John's college option can be picked again");
  // keyboard: the chips are radio buttons
  await page.getByRole("radio", { name: "No", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  check(
    (await checked(page, "Any income changes coming?")) === "Job loss next year",
    "arrow keys move between the income options",
  );
  await page.keyboard.press("ArrowLeft");
  check((await checked(page, "Any income changes coming?")) === "No", "and back");

  // --- Invest with John's values: the base portfolio
  const first = await invest(page);
  const defaults = { ...d, income_change: "none" };
  check(
    first.sent.household.document_id === "smith-bundle" && Object.keys(first.sent.household.overrides).length === 0,
    "household is built from the dropped PDF with no overrides",
  );
  check(
    JSON.stringify(first.sent.household.answers) === JSON.stringify(defaults),
    "household answers equal /portal/defaults (income_change none)",
  );
  const bodyEvent = first.sent.invest;
  check(
    bodyEvent.event === "none" && bodyEvent.previous_plan_id === null && bodyEvent.change_label === null,
    "first invest: event none, no previous plan, no label",
  );
  check(
    JSON.stringify(Object.keys(bodyEvent.household).sort()) ===
      JSON.stringify(Object.keys(first.answered.invest.household).sort()),
    "the invest request carries the household the API built",
  );
  check(
    (await page.locator("[data-plan-id]").getAttribute("data-plan-id")) === first.answered.invest.plan_id,
    "the Invest screen has the API's plan id",
  );
  check(first.answered.invest.what_changed === null, "the first result has no what-changed");

  // --- a cached change: job loss
  await page.getByRole("button", { name: "Back" }).click();
  await page.waitForURL("**/goals");
  check(
    (await checked(page, "Retirement age")) === "60" && (await checked(page, "Any income changes coming?")) === "No",
    "Back from Invest keeps the answers",
  );
  await page.getByRole("radio", { name: "Job loss next year" }).check();
  const second = await invest(page);
  check(second.sent.household.answers.income_change === "job_loss", "household answers carry income_change job_loss");
  check(second.sent.invest.event === "job_loss", "event is job_loss");
  check(
    second.sent.invest.previous_plan_id === first.answered.invest.plan_id,
    "previous_plan_id is the plan of the last Invest",
  );
  check(
    second.sent.invest.change_label === "Income: job loss next year",
    `change_label: ${second.sent.invest.change_label}`,
  );
  check(
    second.answered.invest.what_changed?.changed === "Income: job loss next year",
    "the API answers with that what-changed",
  );

  // --- same inputs again: the same plan, nothing new to say
  await page.getByRole("button", { name: "Back" }).click();
  await page.waitForURL("**/goals");
  const again = await invest(page);
  check(again.sent.invest.change_label === null, "same inputs as last time: no change label");
  check(again.answered.invest.plan_id === second.answered.invest.plan_id, "and the API returns the same plan");

  // --- a live change shows "Building your portfolio…"; two changes are joined with "; "
  await page.getByRole("button", { name: "Back" }).click();
  await page.waitForURL("**/goals");
  await page.getByRole("radio", { name: "No", exact: true }).check();
  await page.getByRole("radio", { name: "65", exact: true }).check();
  // a spending nobody has asked for before (through Other), so the portfolio really is built now and not found in the cache
  const spending = 111_000 + Math.floor(Math.random() * 8_000);
  await page.getByRole("group", { name: "Retirement spending a year" }).getByRole("radio", { name: "Other" }).check();
  await page.getByLabel("Retirement spending a year, other").fill(String(spending));
  await page.getByLabel("Retirement spending a year, other").press("Enter");
  const live = page.getByRole("button", { name: "Invest", exact: true });
  const waiting = (async () => {
    await page.getByText("Building your portfolio…").waitFor({ timeout: 10_000 });
    return true;
  })().catch(() => false);
  const third = await invest(page);
  check(await waiting, "while a new portfolio is built the screen says 'Building your portfolio…'");
  check(
    third.sent.invest.change_label ===
      `Income: no change; Retirement age: 65; Retirement spending: ${dollarsWhole(spending)}`,
    `several changes are joined with "; ": ${third.sent.invest.change_label}`,
  );
  check(
    third.sent.invest.previous_plan_id === second.answered.invest.plan_id && third.sent.invest.event === "none",
    "previous_plan_id and event follow the last Invest",
  );
  void live;

  check(issues.length === 0, `no console errors (${issues.join(" | ")})`);
  await context.close();

  // --- an edited review field is named in the label (a fresh customer: Review, edit, Goals, Invest twice)
  {
    const s = await newPage(browser);
    const p = s.page;
    await toReview(p, base);
    await p.getByRole("button", { name: "Confirm", exact: true }).click();
    await p.getByRole("button", { name: "Confirm and continue" }).click();
    await p.waitForURL("**/goals");
    const base1 = await invest(p);
    check(
      base1.sent.invest.change_label === null &&
        base1.sent.household.overrides &&
        Object.keys(base1.sent.household.overrides).length === 0,
      "a fresh customer's first Invest sends no overrides",
    );
    await p.getByRole("link", { name: "Review" }).click();
    await p.waitForURL("**/review");
    const box = p.locator('[data-field-key="wages_1a"] input');
    await box.fill("163415");
    await box.press("Enter");
    await p.getByRole("button", { name: "Confirm and continue" }).click();
    await p.waitForURL("**/goals");
    const edited = await invest(p);
    check(edited.sent.household.overrides.wages_1a === 163415, "the edit is sent as overrides {wages_1a: 163415}");
    check(
      edited.sent.invest.change_label === "Wages (line 1a): $163,415",
      `change_label names the edited field: ${edited.sent.invest.change_label}`,
    );
    check(
      edited.sent.invest.previous_plan_id === base1.answered.invest.plan_id,
      "the edit is compared with the plan before it",
    );
    await s.context.close();
  }
}

if (isMain(import.meta.url)) await runAlone(runGoals, "goals");
