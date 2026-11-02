// Annual charitable giving: the question, what it sends, where it shows, and the what-if edit (round two, part B).
//
//   BASE_URL=http://localhost:3000 CHROMIUM_PATH=... node e2e/giving.mjs
//
// The household request and the what-if request are read from what the browser itself sends; the profile and the what-if's change
// are compared with the API's own answers to them.

import { isMain, layoutOf, openPage, runAlone, squash, exact } from "../lib.mjs";

/** The one line of help the question carries, as the brief words it. */
const HELP =
  "Donabach gives shares that have gained the most instead of cash, so that gain is never taxed. Without itemizing, a couple deducts at most $2,000 of cash gifts.";
const LABEL = "Charitable giving a year";

export async function runGiving({ browser, base, out, check, notes }) {
  // --- The question: $0 to start with, a custom amount that must be at least zero, one line of help -----------------------------
  const { context, page, issues } = await openPage(browser, { width: 1440 });
  const households = [];
  const whatIfs = [];
  let whatIfAnswer = null;
  page.on("request", (r) => {
    if (r.method() !== "POST") return;
    const { pathname } = new URL(r.url());
    if (pathname === "/api/household") households.push(r.postDataJSON());
    if (pathname === "/api/plan/whatif") whatIfs.push(r.postDataJSON());
  });
  page.on("response", async (r) => {
    if (r.request().method() === "POST" && new URL(r.url()).pathname === "/api/plan/whatif")
      whatIfAnswer = await r.json().catch(() => null);
  });
  // The year-by-year job is not what is looked at here: ask for the plans without it.
  for (const pattern of ["**/api/plan", "**/api/plan/whatif"]) {
    await page.route(pattern, async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      const body = JSON.parse(route.request().postData() ?? "{}");
      await route.continue({ postData: JSON.stringify({ ...body, adaptive: false }) });
    });
  }

  await page.goto(base + "/questions", { waitUntil: "networkidle" });
  const group = page.getByRole("radiogroup", { name: LABEL });
  await group.waitFor({ timeout: 30000 });
  const choices = (await group.getByRole("radio").allInnerTexts()).map(squash);
  const helpId = await group.getAttribute("aria-describedby");
  const help = helpId ? squash(await page.locator(`[id="${helpId}"]`).innerText()) : "";
  check(
    choices[0] === "$0" &&
      choices.at(-1) === "Custom" &&
      (await group.getByRole("radio", { name: "$0", exact: true }).getAttribute("aria-checked")) === "true",
    `giving: the Questions screen asks "${LABEL}", with $0 chosen to start with (${choices.join(", ")})`,
  );
  check(help === HELP, "giving: one line of help sits under the question, and the question is described by it");
  const topic = squash(await page.locator('section[aria-labelledby="topic-giving"]').innerText());
  check(
    topic.includes(LABEL) && topic.indexOf(HELP.slice(0, 40)) > topic.indexOf(LABEL),
    "giving: the question is under its own heading, with the help below it",
  );

  // A custom amount: a negative one is refused like any other money field, a good one is kept.
  await group.getByRole("radio", { name: "Custom" }).click();
  const box = page.getByLabel(`${LABEL} (custom amount)`);
  await box.fill("-50");
  const refused = (await box.getAttribute("aria-invalid")) === "true";
  await box.blur();
  const back = await box.inputValue();
  await box.fill("abc");
  const text = (await box.getAttribute("aria-invalid")) === "true";
  await box.blur();
  check(
    refused && text && back === "0" && (await box.inputValue()) === "0",
    "giving: a negative amount or a word is refused (red box) and the box goes back to the last good amount when left, like the other money fields",
  );
  await box.fill("7500");
  await box.press("Enter");
  check(
    (await box.inputValue()) === "7,500" &&
      (await group.getByRole("radio", { name: "Custom" }).getAttribute("aria-checked")) === "true",
    "giving: a custom amount ($7,500) is kept and shown with its separator",
  );
  const weak = await layoutOf(page, 'section[aria-labelledby="topic-giving"]');
  check(
    weak.spill.length === 0 && weak.small.length === 0,
    `giving: the question has no text under 14px and nothing spilling out at 1440px${weak.spill.length ? ` (${weak.spill.join(", ")})` : ""}`,
  );

  // --- It goes into the household request, beside the other answers --------------------------------------------------------
  await page.getByRole("button", { name: /Build my profile/ }).click();
  await page.waitForURL("**/profile", { timeout: 60000 });
  const sent = households.at(-1);
  check(
    households.length === 1 &&
      sent.answers.charitable_giving === 7500 &&
      sent.answers.retirement_spending === 110000 &&
      Object.keys(sent.answers).filter((k) =>
        ["retirement_age", "retirement_spending", "charitable_giving"].includes(k),
      ).length === 3,
    `giving: the household request carries charitable_giving (${sent?.answers.charitable_giving}) in its answers, next to retirement_spending (${sent?.answers.retirement_spending})`,
  );

  // --- The profile lists it, only when there is some ---------------------------------------------------------------------
  const goals = page.getByRole("region", { name: "Goals" });
  await goals.waitFor({ timeout: 30000 });
  const goalsText = squash(await goals.innerText());
  check(
    goalsText.includes(`Charitable giving ${exact(7500)} a year`) &&
      goalsText.indexOf("Retirement") < goalsText.indexOf("Charitable giving"),
    `giving: the profile's goals list shows "Charitable giving", ${exact(7500)} a year, like its other goals (from the household's goals)`,
  );
  const footer = squash(await page.locator("footer").innerText());
  check(
    footer.includes("the standard deduction (itemizing only for charitable gifts)") &&
      !footer.includes("standard deduction only (no itemizing)"),
    "giving: the profile's footer reads 'the standard deduction (itemizing only for charitable gifts)'",
  );

  // --- The what-if edit, beside retirement spending ---------------------------------------------------------------------
  await page.goto(base + "/plan", { waitUntil: "networkidle" });
  await page
    .getByText(/Hold (the next \d+ years of what you will need|\d+% of)/)
    .first()
    .waitFor({ timeout: 120000 });
  await page
    .getByRole("button", { name: /What if/i })
    .first()
    .click();
  const panel = page.getByRole("region", { name: "What if..." });
  await panel.waitFor();
  const field = panel.getByLabel("Charitable giving");
  check(
    (await field.inputValue()) === "7,500",
    "giving: after a reload the answer is still $7,500 (it was kept with the others) and the what-if panel starts from it",
  );
  const order = await panel.evaluate((root) => {
    const labels = [...root.querySelectorAll("label")].map((l) => l.querySelector("span")?.textContent?.trim());
    return labels;
  });
  const spendingAt = order.indexOf("Retirement spending");
  check(
    spendingAt >= 0 && order[spendingAt + 1] === "Charitable giving",
    `giving: the what-if panel has an edit for it right after retirement spending (${order.slice(0, 5).join(", ")})`,
  );
  await field.fill("12000");
  await field.press("Enter");
  await page
    .getByText(/What-if applied/)
    .first()
    .waitFor({ timeout: 120000 });
  const request = whatIfs.at(-1);
  const answer = whatIfAnswer;
  const others = Object.entries(request.edits).filter(
    ([k, v]) => k !== "charitable_giving" && v !== null && v !== false,
  );
  check(
    whatIfs.length === 1 &&
      request.edits.charitable_giving === 12000 &&
      others.length === 0 &&
      request.household.goals.charitable_giving === 7500,
    `giving: the what-if request carries edits.charitable_giving (${request.edits.charitable_giving}) and nothing else, from a household that gives ${request.household.goals.charitable_giving}`,
  );
  const change = answer.changes.find((c) => c.field === "charitable_giving");
  const banner = squash(await page.locator('[aria-live="polite"]', { hasText: "What-if applied" }).first().innerText());
  check(
    !!change &&
      answer.household.goals.charitable_giving === 12000 &&
      banner.includes(`${change.label} ${change.before}`) &&
      banner.includes(change.after) &&
      (await field.inputValue()) === "12,000",
    `giving: the API's change is shown ("${change?.label} ${change?.before} to ${change?.after}") and the what-if household gives ${exact(answer.household.goals.charitable_giving)}`,
  );
  check(issues.length === 0, `giving: no console errors${issues.length ? ` (${issues[0]})` : ""}`);
  await context.close();

  // --- With nothing asked for: $0 goes to the API and the profile does not mention it -------------------------------------------
  {
    const fresh = await openPage(browser, { width: 1440 });
    const sentFresh = [];
    fresh.page.on("request", (r) => {
      if (r.method() === "POST" && new URL(r.url()).pathname === "/api/household") sentFresh.push(r.postDataJSON());
    });
    await fresh.page.goto(base + "/profile", { waitUntil: "networkidle" });
    const list = fresh.page.getByRole("region", { name: "Goals" });
    await list.waitFor({ timeout: 60000 });
    const t = squash(await list.innerText());
    check(
      sentFresh.length >= 1 && sentFresh.at(-1).answers.charitable_giving === 0 && !t.includes("Charitable giving"),
      "giving: by default the household request says charitable_giving 0 and the goals list leaves giving out",
    );
    await fresh.context.close();
  }

  // --- At a phone's width ---------------------------------------------------------------------------------------------
  {
    const phone = await openPage(browser, { width: 390 });
    await phone.page.goto(base + "/questions", { waitUntil: "networkidle" });
    await phone.page.getByRole("radiogroup", { name: LABEL }).waitFor({ timeout: 30000 });
    const layout = await layoutOf(phone.page, 'section[aria-labelledby="topic-giving"]');
    check(
      layout.mainOverflow <= 0 && layout.spill.length === 0 && layout.small.length === 0,
      `giving at 390px: the question and its help fit${layout.spill.length ? ` (${layout.spill.join(", ")})` : ""}`,
    );
    await phone.page.screenshot({ path: `${out}/giving-questions-390.png`, fullPage: true });
    await phone.context.close();
  }
  void notes;
}

if (isMain(import.meta.url)) await runAlone(runGiving, "giving");
