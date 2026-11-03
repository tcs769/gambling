// Goals (/goals): the questions prefilled with the API's defaults, tap-to-select chips (the mockup's rows), the down payment box, the income-change question,
// and what Invest sends (household, then invest with the event, the previous plan and the words for what changed).
import { isMain, runAlone, newPage, apiGet, toGoals, toReview, openAll, dollarsWhole } from "./portal.mjs";

const group = (page, legend) => page.getByRole("radiogroup", { name: legend });
const checked = (page, legend) => group(page, legend).locator("input:checked + span").innerText();
const options = (page, legend) => group(page, legend).locator("label").allInnerTexts();
const AGE = "When do you want to retire?";
const COLLEGE = "College for your child";
const HOME = "Buying a home?";
const INCOME = "Any income changes coming?";
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

  // --- the copy of the mockup
  check((await page.locator("main h1").innerText()) === "A few questions", "the heading is 'A few questions'");
  check(
    await page.getByText("Your documents can't tell us these.", { exact: true }).isVisible(),
    "the lede is 'Your documents can't tell us these.'",
  );
  const rowLabels = await page.locator("main [class*=qt]").allInnerTexts();
  check(
    JSON.stringify(rowLabels) === JSON.stringify([AGE, COLLEGE, HOME, INCOME, "Yearly spending in retirement"]),
    `the questions, in the mockup's order: ${rowLabels.join(" | ")}`,
  );
  const labelBox = await page.getByText(AGE, { exact: true }).boundingBox();
  const chipBox = await page.getByRole("radio", { name: "60", exact: true }).locator("..").boundingBox();
  check(
    Math.abs(chipBox.x - labelBox.x - 260 - 20) < 3,
    `the chips start 280px after the question (${Math.round(chipBox.x - labelBox.x)})`,
  );

  // --- prefilled with the defaults
  check((await checked(page, AGE)) === String(d.retirement_age), `retirement age ${d.retirement_age} is selected`);
  const spend = page.getByLabel("Yearly spending in retirement");
  check(
    (await spend.inputValue()) === Math.round(d.retirement_spending).toLocaleString("en-US"),
    `spending is prefilled with ${Math.round(d.retirement_spending).toLocaleString("en-US")}`,
  );
  const startsIn = `Starts in ${plural(d.college_starts_in_years, "year")}`;
  check((await checked(page, COLLEGE)) === startsIn, `college is "${startsIn}"`);
  check(d.home_purchase_in_years === null && (await checked(page, HOME)) === "No plans", "home is No plans");
  check((await checked(page, INCOME)) === "No", "income changes: No is selected");
  check((await page.getByLabel("Down payment").count()) === 0, "no down payment box while there are no home plans");

  // --- the chips
  check(
    JSON.stringify(await options(page, AGE)) === JSON.stringify(["60", "62", "65", "67"]),
    "retirement age chips: 60 62 65 67",
  );
  check(
    JSON.stringify(await options(page, COLLEGE)) === JSON.stringify([startsIn, "Not planned"]),
    "college chips: Starts in 8 years, Not planned",
  );
  check(
    JSON.stringify(await options(page, HOME)) === JSON.stringify(["No plans", "Within 3 years", "Within 5 years"]),
    "home chips: No plans, Within 3 years, Within 5 years",
  );
  check(
    JSON.stringify(await options(page, INCOME)) === JSON.stringify(["No", "Job loss next year", "A raise"]),
    "income chips: No, Job loss next year, A raise",
  );

  // --- tapping selects; a home purchase asks for a down payment
  await page.getByRole("radio", { name: "65", exact: true }).check();
  check((await checked(page, AGE)) === "65", "tapping 65 selects it");
  await page.getByRole("radio", { name: "Within 5 years" }).check();
  const down = page.getByLabel("Down payment");
  check((await down.inputValue()) === "150,000", "Within 5 years shows a Down payment box prefilled with 150,000");
  await down.fill("175000");
  await down.press("Enter");
  check((await down.inputValue()) === "175,000", "the down payment can be edited");
  await page.getByRole("radio", { name: "Within 3 years" }).check();
  check((await down.inputValue()) === "175,000", "switching between 3 and 5 years keeps the down payment");
  await page.getByRole("radio", { name: "No plans" }).check();
  check((await page.getByLabel("Down payment").count()) === 0, "No plans takes the down payment box away");
  await page.getByRole("radio", { name: "Not planned" }).check();
  check((await checked(page, COLLEGE)) === "Not planned", "college can be set to Not planned");
  await page.getByRole("radio", { name: startsIn }).check();
  check((await checked(page, COLLEGE)) === startsIn, "and back to Starts in 8 years");
  await page.getByRole("radio", { name: "60", exact: true }).check();
  // keyboard: the chips are radio buttons
  await page.getByRole("radio", { name: "No", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  check((await checked(page, INCOME)) === "Job loss next year", "arrow keys move between the income options");
  await page.keyboard.press("ArrowLeft");
  check((await checked(page, INCOME)) === "No", "and back");

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
    (await checked(page, AGE)) === "60" && (await checked(page, INCOME)) === "No",
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
  // a spending nobody has asked for before (typed in the box), so the portfolio really is built now and not found in the cache
  const spending = 111_000 + Math.floor(Math.random() * 8_000);
  await spend.fill(String(spending));
  await spend.press("Enter");
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
    await openAll(p);
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

  // --- an age that is not one of the four chips (here 58) shows as one more selected chip
  {
    const s = await newPage(browser);
    const p = s.page;
    await toGoals(p, base);
    await p.evaluate(() => {
      const key = "waramoug.portal.v1";
      const saved = JSON.parse(window.sessionStorage.getItem(key));
      saved.answers.retirement_age = 58;
      window.sessionStorage.setItem(key, JSON.stringify(saved));
    });
    await p.reload({ waitUntil: "networkidle" });
    await p.getByRole("radio", { name: "58", exact: true }).waitFor();
    check(
      JSON.stringify(await options(p, AGE)) === JSON.stringify(["58", "60", "62", "65", "67"]) &&
        (await checked(p, AGE)) === "58",
      "a retirement age outside the four chips is shown as an extra selected chip",
    );
    await s.context.close();
  }
}

if (isMain(import.meta.url)) await runAlone(runGoals, "goals");
