// Walks the whole demo in a real browser and checks the cross-cutting requirements.
//
//   node e2e/walkthrough.mjs            (with the API on :8000 and the app on :3000 running)
//
// Environment: BASE_URL (default http://localhost:3000), OUT_DIR for screenshots (default
// ../.screenshots), CHROMIUM_PATH if Playwright's own browser is not installed.
// Checks per screen: no console errors, no visible text under 14px, no horizontal overflow at
// 1440 wide, charts at least 300px tall. Beyond those, the Plan and Comparison screens are checked
// against what the API sent for the plan (its horizon, advisor definitions, advantage figures,
// table size), not against copy typed here. Exits non-zero if anything fails.
//
// The showcase flow (/showcase: the household card, the strategy waterfall, wealth over time) is checked at the end by
// e2e/showcase.mjs, also against the API's own responses (it can be run alone: `node e2e/showcase.mjs`, same environment).
//
// Round two: both valuations of wealth at 80 (e2e/valuations.mjs), annual charitable giving (e2e/giving.mjs) and the Plan screen's
// planning-style switch (e2e/styles.mjs) are checked at the end, the same way (each can be run alone; e2e/lib.mjs has what they share).
//
// The year-by-year (adaptive) plan is checked the same way: the years highlighted in the plan table, the "Why this
// year" panel, the four-way comparison, what judgment over time adds and the "What changed" panel are compared with
// the adaptive plan the API sent (in the plan response, or as the result of its background job, read from
// GET /plan/adaptive/{id}), including the "Refining plan…" state of a what-if. The API keeps finished year-by-year
// plans in memory: against an API that has already planned these households the Refining checks find the plan
// ready at once and say so in a note instead; start the API fresh to exercise them.

import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { chromium } from "playwright-core";
import { runGiving } from "./giving.mjs";
import { runShowcase } from "./showcase.mjs";
import { runStyles } from "./styles.mjs";
import { runValuations } from "./valuations.mjs";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const OUT = resolve(process.env.OUT_DIR ?? new URL("../../.screenshots", import.meta.url).pathname);
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
  args: ["--no-sandbox"],
});
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

const failures = [];
const notes = [];
let consoleIssues = [];
page.on("console", (m) => {
  if (m.type() === "error") consoleIssues.push(m.text());
});
page.on("pageerror", (e) => consoleIssues.push(`pageerror: ${e.message}`));

let checks = 0;
const check = (ok, message) => {
  checks++;
  if (!ok) failures.push(message);
  console.log(`${ok ? "  ok  " : " FAIL "} ${message}`);
};

async function audit(name) {
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/${name}.png` });
  const result = await page.evaluate(() => {
    const small = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!node.textContent.trim()) continue;
      const el = node.parentElement;
      if (!el || el.closest("script,style,noscript,[hidden],nextjs-portal")) continue;
      const style = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      if (style.visibility === "hidden" || style.display === "none" || +style.opacity === 0) continue;
      if (rect.width < 2 || rect.height < 2) continue;
      if (el.closest(".sr-only")) continue;
      const size = parseFloat(style.fontSize);
      if (size < 13.99) small.push(`${size}px "${node.textContent.trim().slice(0, 40)}"`);
    }
    const charts = [...document.querySelectorAll(".recharts-wrapper")].map((c) => Math.round(c.getBoundingClientRect().height));
    return {
      small: [...new Set(small)].slice(0, 6),
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      charts,
    };
  });
  check(consoleIssues.length === 0, `${name}: no console errors${consoleIssues.length ? ` (${consoleIssues[0]})` : ""}`);
  consoleIssues = [];
  check(result.small.length === 0, `${name}: no visible text under 14px${result.small.length ? ` (${result.small.join(", ")})` : ""}`);
  check(result.overflow <= 0, `${name}: no horizontal overflow`);
  for (const h of result.charts) check(h >= 300, `${name}: chart is at least 300px tall (${h}px)`);
  return result;
}

const click = (name, options = {}) => page.getByRole("button", { name, ...options }).first().click();
const bodyText = () => page.evaluate(() => document.body.innerText);

// The plan the API sent for the household on screen (POST /api/plan, not the what-if variant). Checks on
// the Plan and Comparison screens read their expectations from it: horizon, definitions, figures.
let lastPlan = null;
let lastWhatIf = null;
let yearDetailRequests = 0;
page.on("response", async (response) => {
  if (response.request().method() !== "POST") return;
  const { pathname } = new URL(response.url());
  if (pathname === "/api/plan") lastPlan = await response.json().catch(() => lastPlan);
  if (pathname === "/api/plan/whatif") lastWhatIf = await response.json().catch(() => lastWhatIf);
});
page.on("request", (request) => {
  if (request.method() === "POST" && new URL(request.url()).pathname === "/api/plan/year-detail") yearDetailRequests++;
});
const planSent = async () => {
  for (let i = 0; i < 100 && !lastPlan; i++) await page.waitForTimeout(100);
  if (!lastPlan) throw new Error("the plan response was never seen");
  return lastPlan;
};
const squash = (text) => text.replace(/\s+/g, " ").trim();
// A yearly rate the way the screen writes it: +0.27%, −0.04% (a true minus sign); three decimals for a figure under
// 0.1% a year (+0.016%), which the screen also does.
const rate = (fraction, digits = 2) => {
  const v = Number((fraction * 100).toFixed(digits));
  return v === 0 ? `${(0).toFixed(digits)}%` : `${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(digits)}%`;
};
const rateDigits = (...fractions) => (Math.max(...fractions.map((f) => Math.abs(f))) < 0.001 ? 3 : 2);
const printed = (fraction, digits) => Number((fraction * 100).toFixed(digits));
// No panel's content may spill out of the panel: a figure past its card, a label past the panel's edge.
// (Things inside a scrolling table body are clipped on purpose and never reach past it.)
const spill = (scope) =>
  page.evaluate((selector) => {
    const out = [];
    for (const panel of document.querySelectorAll(selector)) {
      const box = panel.getBoundingClientRect();
      for (const el of panel.querySelectorAll("*")) {
        if (el.closest(".sr-only")) continue;
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        if (r.right > box.right + 1 || r.left < box.left - 1) {
          out.push(`${el.tagName.toLowerCase()}.${(el.getAttribute("class") ?? "").split(" ")[0]} reaches ${Math.round(Math.max(r.right - box.right, box.left - r.left))}px past the panel`);
        }
      }
    }
    return [...new Set(out)].slice(0, 5);
  }, scope);

// --- The year-by-year (adaptive) plan: helpers. Every expectation is read from the API's own responses. ----------
const API = BASE + "/api";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const getJson = async (path) => (await fetch(API + path)).json();
const postJson = async (path, body) =>
  (await fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();

// Money the way the app writes it ($850, $4.2k, $40k, $250k, $1.24M), for figures read from the API.
const trimZeros = (s) => (s.includes(".") ? s.replace(/\.?0+$/, "") : s);
const money = (value) => {
  const sign = value < 0 ? "−" : "";
  const abs = Math.abs(value);
  if (abs >= 999_500) return `${sign}$${trimZeros((abs / 1_000_000).toFixed(2))}M`;
  if (abs >= 100_000) return `${sign}$${Math.round(abs / 1_000)}k`;
  if (abs >= 1_000) return `${sign}$${trimZeros((abs / 1_000).toFixed(1))}k`;
  return `${sign}$${Math.round(abs)}`;
};
const signedMoney = (value) => (Math.abs(value) < 0.5 ? "$0" : `${value > 0 ? "+" : ""}${money(value)}`);
const pct1 = (fraction) => `${Number((fraction * 100).toFixed(1))}%`;
const mean = (xs) => xs.reduce((sum, x) => sum + x, 0) / xs.length;
const agesText = (from, to) => (from === to ? `age ${from}` : `ages ${from} to ${to}`);
// "age 55", "ages 55 and 71", "ages 55, 71 and 78"; past eight ages "ages 55, 71, 72 and 5 more" (the way the screen lists them).
const agesListText = (ages, limit = 8) => {
  if (ages.length === 1) return `age ${ages[0]}`;
  const shown = ages.slice(0, limit);
  const more = ages.length - shown.length;
  return `ages ${shown.slice(0, -1).join(", ")} and ${more > 0 ? `${shown[shown.length - 1]} and ${more} more` : shown[shown.length - 1]}`;
};

// The product owner's plain names for the planner's decisions and for the strategy's choices.
const DECISION_NAMES = {
  conversion: "Roth conversion",
  realize_gains: "Realizing gains",
  goal_funding: "How the goal is paid",
  k401: "401(k) type",
  private_credit: "Private credit",
  stock_share: "Stock share",
};
const changedTag = (departures) => `Changed: ${departures.map((d) => DECISION_NAMES[d] ?? d).join(", ")}`;
const CHOICE_LABELS = {
  stock_share: "Stock share",
  conversion: "Roth conversions",
  private_credit: "Private credit sleeve",
  direct_indexing: "Direct indexing",
  goal_bonds: "Goal-matched bonds",
  k401: "401(k) contributions",
  goal_funding: "Paying for goals",
  reserve: "Spending reserve",
};
// How an alternative's score reads against the chosen action's (ce_gap = the chosen action's score minus its own).
const gapWords = (gap) =>
  Math.abs(gap) < 0.5 ? "Scored the same as the chosen action" : gap > 0 ? `Scored ${money(gap)} lower` : `Scored ${money(-gap)} higher, but not convincingly`;

const refiningStatus = (pg = page) => pg.getByRole("status").filter({ hasText: /Refining plan/ });
const waitRefiningGone = (pg = page, timeout = 150_000) => refiningStatus(pg).first().waitFor({ state: "detached", timeout });
const viewRadio = (name, pg = page) => pg.getByRole("radio", { name });
const markedYears = (pg = page) => pg.locator('tr[data-row-key][data-tone="changed"]').evaluateAll((rows) => rows.map((r) => Number(r.getAttribute("data-row-key"))));
const visibleLegend = (pg = page) => pg.getByRole("list", { name: "Chart legend" }).locator("li:visible");
/** Where an element sits on the page (document coordinates), to see whether anything below moved. */
const pageTop = (locator) => locator.evaluate((el) => Math.round(el.getBoundingClientRect().top + window.scrollY));
// A line of text is about 24px: the room kept for the year-by-year plan may be off by that much for a household of another shape.
const JUMP_TOLERANCE = 24;

/** The year-by-year plan that goes with a plan response: in it, or the finished job's result (read from the API). */
async function adaptiveOf(planResponse, seconds = 150) {
  if (planResponse.adaptive) return planResponse.adaptive;
  const id = planResponse.adaptive_job;
  if (!id) throw new Error("the plan response has neither a year-by-year plan nor a job to follow");
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    const job = await getJson(`/plan/adaptive/${id}`);
    if (job.status === "done" && job.result) return job.result;
    if (job.status === "error") throw new Error(`the year-by-year job failed: ${job.error}`);
    await sleep(500);
  }
  throw new Error("the year-by-year plan did not finish in time");
}

const whatIfSent = async () => {
  for (let i = 0; i < 300 && !lastWhatIf; i++) await page.waitForTimeout(100);
  if (!lastWhatIf) throw new Error("the what-if response was never seen");
  return lastWhatIf;
};

/** The plan table in its year-by-year view: the years highlighted are the API's `departs` rows, and say what changed. */
async function checkDepartureRows(section, label, pg = page) {
  const departing = section.rows.filter((r) => r.departs);
  const expected = departing.map((r) => r.year_index);
  const marked = await markedYears(pg);
  check(
    JSON.stringify(marked) === JSON.stringify(expected),
    `${label}: the years highlighted as changed are exactly the API's departs rows (${expected.length} of ${section.rows.length}${departing.length ? `: ages ${departing.map((r) => r.age).join(", ")}` : ""})`,
  );
  let words = true;
  for (const r of departing) {
    const rowText = squash(await pg.locator(`tr[data-row-key="${r.year_index}"]`).innerText());
    if (!rowText.includes(changedTag(r.departures))) words = false;
  }
  const taggedElsewhere = await pg.locator('tr[data-row-key]:not([data-tone="changed"])').filter({ hasText: "Changed:" }).count();
  check(
    words && taggedElsewhere === 0,
    `${label}: each highlighted year says what changed in words (${departing.slice(0, 2).map((r) => changedTag(r.departures)).join("; ") || "no year changed"}) and no other year does`,
  );
  const status = squash(await pg.getByText(/changed from the fixed strategy on this path/).first().innerText());
  check(
    status.includes(`${departing.length} of ${section.rows.length} years changed from the fixed strategy on this path`) &&
      status.includes(`Across ${section.n_eval_paths} simulated futures the planner changes something in ${pct1(section.departure_share)} of its year-by-year decisions`),
    `${label}: the table says how many years changed (${departing.length} of ${section.rows.length}, counted from the rows) and the share over every simulated future (${pct1(section.departure_share)})`,
  );
}

/** The four-strategy table: every figure for every strategy is the API's. */
async function checkFourWay(section, horizon, label, pg = page) {
  const table = pg.getByRole("table", { name: /The four strategies side by side/ });
  await table.waitFor({ timeout: 30000 });
  const heads = (await table.locator("thead th").allInnerTexts()).map(squash);
  const order = section.strategies.map((s) => s.label);
  check(heads.length === 5 && order.every((l, i) => heads[i + 1] === l), `${label}: the four-way table has a column for each strategy, in the API's order (${order.join(", ")})`);
  const rows = await table.locator("tbody tr").all();
  check(rows.length === 9, `${label}: the four-way table has five outcome rows and four advantage rows (${rows.length} rows)`);
  const cellsOf = async (i) => (await rows[i].locator("td").allInnerTexts()).map(squash);
  const outcomes = [
    ["typical outcome", (s) => money(s.outcome.median)],
    ["certainty equivalent", (s) => money(s.outcome.score)],
    ["bad case (10th percentile)", (s) => money(s.outcome.p10)],
    ["lifetime taxes", (s) => money(s.lifetime_taxes)],
    ["chance of running out of money", (s) => pct1(s.shortfall_chance)],
  ];
  for (const [i, [name, expect]] of outcomes.entries()) {
    const want = section.strategies.map(expect);
    check(JSON.stringify(await cellsOf(i)) === JSON.stringify(want), `${label}: ${name} of the four strategies is the API's (${want.join(", ")})`);
  }
  let anySpans = false;
  const advantages = [
    ["median", "typical_advisor"],
    ["median", "good_ria"],
    ["risk_adjusted", "typical_advisor"],
    ["risk_adjusted", "good_ria"],
  ];
  for (const [j, [measure, over]] of advantages.entries()) {
    const cells = await cellsOf(5 + j);
    const low = `${measure}_low`;
    const high = `${measure}_high`;
    const dollarsKey = `${measure}_dollars`;
    let ok = cells.length === 4;
    const figures = [];
    section.strategies.forEach((s, k) => {
      if (s.key === over) {
        ok &&= cells[k].includes("Not applicable");
        figures.push("n/a");
        return;
      }
      const a = over === "typical_advisor" ? s.advantage_vs_typical : s.advantage_vs_ria;
      const d = rateDigits(a[measure], a[low], a[high]);
      const need = [`${rate(a[measure], d)} a year`, `90% range: ${rate(a[low], d)} to ${rate(a[high], d)}`, `${signedMoney(a[dollarsKey])} at ${horizon}`];
      const spans = printed(a[low], d) <= 0 && printed(a[high], d) >= 0;
      anySpans ||= spans;
      // A range that includes zero carries a dagger, and only such a range does.
      ok &&= need.every((t) => cells[k].includes(t)) && cells[k].includes("\u2020") === spans;
      figures.push(need[0] + (spans ? " \u2020" : ""));
    });
    check(ok, `${label}: ${measure === "median" ? "median" : "risk-adjusted"} advantage over ${over === "good_ria" ? "a good RIA" : "a typical advisor"} for each strategy is the API's (${figures.join(", ")}), with its 90% range and dollars`);
  }
  // The sentence under the table says what a dagger means, or that there is none: exactly one of the two shows.
  const some = pg.getByText("The 90% range includes zero, so that advantage is not distinguishable from no effect.");
  const none = pg.getByText("No advantage here has a 90% range that includes zero");
  check(
    (await some.isVisible()) === anySpans && (await none.isVisible()) === !anySpans,
    `${label}: ${anySpans ? "a \u2020 marks each advantage whose 90% range includes zero, and the note says it is not distinguishable from no effect" : "no advantage's 90% range includes zero, and the note says so"}`,
  );
}

/** "What judgment over time adds": the API's value_of_judgment, and a verdict no stronger than the range allows. */
async function checkJudgment(section, horizon, label, pg = page) {
  const v = section.value_of_judgment;
  for (const [name, value, low, high, dollars, unit] of [
    ["Median advantage", "median", "median_low", "median_high", "median_dollars", "typical (median)"],
    ["Risk-adjusted advantage", "risk_adjusted", "risk_adjusted_low", "risk_adjusted_high", "risk_adjusted_dollars", "certainty-equivalent"],
  ]) {
    const cell = squash(await pg.getByRole("group", { name: `${name} of the adaptive planner over the best fixed strategy` }).innerText());
    const d = rateDigits(v[value], v[low], v[high]);
    check(
      cell.includes(`${rate(v[value], d)} a year`) &&
        cell.includes(`90% range: ${rate(v[low], d)} to ${rate(v[high], d)} when the futures are resampled`) &&
        cell.includes(`${signedMoney(v[dollars])} of ${unit} wealth at ${horizon}`),
      `${label}: ${name.toLowerCase()} of the adaptive planner over the best fixed strategy is ${rate(v[value], d)} a year (range ${rate(v[low], d)} to ${rate(v[high], d)}, ${signedMoney(v[dollars])} at ${horizon}), as the API says`,
    );
    const spansPrinted = printed(v[low], d) <= 0 && printed(v[high], d) >= 0;
    const expectedSentence = spansPrinted
      ? "The 90% range includes zero, so this is not distinguishable from no effect."
      : printed(v[low], d) > 0
        ? "The whole 90% range is above zero."
        : "The whole 90% range is below zero.";
    // Never stronger than the range: a range that reaches zero is never called one-sided.
    const overclaims = v[low] <= 0 && v[high] >= 0 && /whole 90% range is (?:above|below) zero/.test(cell);
    check(cell.includes(expectedSentence) && !overclaims, `${label}: ${name.toLowerCase()}: the range ${rate(v[low], d)} to ${rate(v[high], d)} is described as "${expectedSentence}"`);
  }
}

/** The "What changed in the plan" panel against the plan before the what-if and the one after, both from the API. */
async function checkWhatChanged(before, after, shock, baseChips, label, otherChanges = false) {
  const panel = page.getByRole("region", { name: "What changed in the plan" });
  await panel.waitFor({ timeout: 20000 });
  const text = squash(await panel.innerText());
  // (a) the recommended strategy's choices that changed, marked on the chips
  const was = before.plan.strategy.choices;
  const now = after.plan.strategy.choices;
  const changed = Object.keys(now).filter((c) => was[c] !== now[c]);
  const marked = (await panel.locator('li[data-changed="true"]').allInnerTexts()).map(squash);
  let chipsOk = marked.length === changed.length;
  for (const choice of changed) {
    const name = CHOICE_LABELS[choice] ?? choice;
    const baseChip = baseChips.find((c) => c.startsWith(name));
    const wasWords = baseChip ? baseChip.slice(name.length).trim() : "";
    chipsOk &&= marked.some((m) => m.startsWith(name) && m.includes(`Changed, was ${wasWords}`));
  }
  check(
    chipsOk && (changed.length > 0 || text.includes("The recommended strategy is the same as before the what-if.")),
    `${label}: the strategy chips mark exactly the choices the API says changed (${changed.map((c) => CHOICE_LABELS[c] ?? c).join(", ") || "none"})`,
  );
  // (b) the years whose adaptive chosen-action label differs
  const n = Math.min(before.adaptive.decisions.length, after.adaptive.decisions.length);
  const differing = [];
  for (let i = 0; i < n; i++) {
    const a = before.adaptive.decisions[i];
    const b = after.adaptive.decisions[i];
    if (a.chosen.label !== b.chosen.label) differing.push({ i, age: b.age, before: a.chosen.label, now: b.chosen.label });
  }
  // The action in each differing year is folded away (so the panel keeps its height whatever the count): open it.
  const fold = panel.getByRole("button", { name: /The action in each of those years/ });
  let list = [];
  if (differing.length > 0) {
    check((await fold.getAttribute("aria-expanded")) === "false" && squash(await fold.innerText()).includes(`${differing.length} ${differing.length === 1 ? "year" : "years"}`), `${label}: the action in each differing year is folded away until opened (${differing.length} ${differing.length === 1 ? "year" : "years"})`);
    await fold.click();
    list = await panel.getByRole("list", { name: /Years where the planner's chosen action differs/ }).locator("li").allInnerTexts();
  }
  const yearsText = squash(await panel.locator('section[aria-labelledby="whatchanged-years"]').innerText());
  if (differing.length === 0) {
    check(yearsText.includes(`None. The planner's chosen action is the same as before the what-if in all ${n} years`), `${label}: the planner's chosen action is the same in all ${n} years, and the panel says so in a plain sentence`);
  } else {
    check(
      yearsText.includes(`First at age ${differing[0].age}.`) &&
        yearsText.includes(`It differs in ${differing.length} of ${n} years: ${agesListText(differing.map((d) => d.age))}.`) &&
        list.length === differing.length &&
        differing.every((d, k) => squash(list[k]).includes(`Age ${d.age}`) && squash(list[k]).includes(`Before: ${d.before}`) && squash(list[k]).includes(`Now: ${d.now}`)),
      `${label}: the years whose chosen action differs are the API's (${differing.length} of ${n}, first at age ${differing[0].age}: ${differing.map((d) => d.age).join(", ")})`,
    );
    if (shock) {
      // A year before the drop can only differ because the fixed strategy it continues does: it says so, and no later year does.
      const beforeDrop = differing.filter((d) => d.i < shock.year);
      const reason = otherChanges
        ? "the planner could not see it coming; the household and the fixed strategy it continues differ here"
        : "differs only because the fixed strategy it continues differs";
      const tagged = list.filter((t) => /before the drop: /i.test(t)).length;
      check(
        tagged === beforeDrop.length && (beforeDrop.length === 0 ? !/Before the drop \(/.test(yearsText) : yearsText.includes(`Before the drop (${agesListText(beforeDrop.map((d) => d.age))}): ${reason}.`)),
        `${label}: exactly the years before the drop are labelled "before the drop: ${reason}" (${beforeDrop.length} such year(s))`,
      );
    }
  }
  if (shock && differing.every((d) => d.i < shock.year)) {
    check(yearsText.includes("From the year of the drop on, its chosen action is the same as before the what-if in every year."), `${label}: from the year of the drop on the planner's chosen action is unchanged, and the panel says so`);
  }
  // (c) how often the planner changes something: from departure_by_year
  const years = Math.min(before.adaptive.departure_by_year.length, after.adaptive.departure_by_year.length);
  const slice = (plan, from, to) => mean(plan.adaptive.departure_by_year.slice(from, to));
  const rowsExpected = [];
  if (shock && shock.year >= 0 && shock.year < years) {
    const s = shock.year;
    const ageAt = (i) => after.adaptive.rows[i].age;
    if (s > 0) rowsExpected.push([`Before the drop (${agesText(ageAt(0), ageAt(s - 1))})`, slice(before, 0, s), slice(after, 0, s)]);
    rowsExpected.push([`Year of the drop (age ${ageAt(s)})`, before.adaptive.departure_by_year[s], after.adaptive.departure_by_year[s]]);
    if (s + 1 < years) rowsExpected.push([`Years after the drop (${agesText(ageAt(s + 1), ageAt(years - 1))})`, slice(before, s + 1, years), slice(after, s + 1, years)]);
  } else {
    rowsExpected.push(["All years", before.adaptive.departure_share, after.adaptive.departure_share]);
  }
  const tableRows = (await panel.locator("tbody tr").allInnerTexts()).map(squash);
  check(
    tableRows.length === rowsExpected.length && rowsExpected.every(([name, b, a], k) => tableRows[k].startsWith(name) && tableRows[k].includes(pct1(b)) && tableRows[k].endsWith(pct1(a))),
    `${label}: how often the planner changes something, before and with the what-if: ${rowsExpected.map(([name, b, a]) => `${name.split(" (")[0]} ${pct1(b)} to ${pct1(a)}`).join("; ")}`,
  );
}

// --- 0. The API's head start: the demo household's year-by-year plan is computed in the background at startup ----
const DEFAULT_ANSWERS = {
  home_purchase_in_years: 3,
  home_down_payment: 120000,
  college_starts_in_years: 10,
  college_annual_cost: 35000,
  college_years: 4,
  retirement_age: 62,
  retirement_spending: 110000,
  roth_balance: 30000,
  cash: 40000,
  social_security_annual: 50000,
  social_security_start_age: 67,
};
const demo = {};
{
  const started = Date.now();
  const docs = (await postJson("/documents/sample")).documents;
  for (const d of docs) await postJson(`/documents/${d.id}/parse`);
  demo.household = (await postJson("/household", { document_ids: docs.map((d) => d.id), overrides: {}, answers: DEFAULT_ANSWERS })).household;
  const ask = () => postJson("/plan", { household: demo.household, n_paths: 400, demo_mode: true, shock: null });
  demo.plan = await ask();
  if (!demo.plan.adaptive && demo.plan.adaptive_job) {
    while (Date.now() - started < 60_000) {
      const job = await getJson(`/plan/adaptive/${demo.plan.adaptive_job}`);
      if (job.status !== "running") break;
      await sleep(700);
    }
    demo.plan = await ask();
  }
  const seconds = ((Date.now() - started) / 1000).toFixed(1);
  check(!!demo.plan.adaptive, `api: the demo household's year-by-year plan is ready within 60 s of the API starting (${seconds}s here)`);
  if (!demo.plan.adaptive) throw new Error("the demo household's year-by-year plan never became ready: nothing else can be checked");
}

// --- 1. Upload ---------------------------------------------------------------------------------
await page.goto(BASE + "/", { waitUntil: "networkidle" });
await page.evaluate(() => localStorage.clear());
await page.reload({ waitUntil: "networkidle" });
await page.getByText("Add your household's documents").first().waitFor();
await page.getByText(/Ready/).first().waitFor({ timeout: 15000 });
await page.waitForFunction(() => (document.body.innerText.match(/Ready/g) ?? []).length >= 3, null, { timeout: 15000 });
check(true, "upload: demo mode preloads the three sample documents");
await audit("1-upload");
await page.getByRole("link", { name: /Review extracted numbers/ }).or(page.getByRole("button", { name: /Review extracted numbers/ })).first().click();

// --- 2. Review ---------------------------------------------------------------------------------
await page.waitForURL("**/review");
await page.getByText(/149,999/).first().waitFor({ timeout: 15000 });
check(/150,000/.test(await bodyText()), "review: the flagged total ($150,000) and its reason ($149,999) are shown");
await audit("2-review-flagged");
const cont = page.getByRole("button", { name: /Confirm and continue/ }).or(page.getByRole("link", { name: /Confirm and continue/ })).first();
check(await cont.isDisabled().catch(() => false), "review: Confirm and continue waits for the flagged field");
await page.getByRole("button", { name: /Keep as is/ }).first().click();
await page.waitForTimeout(300);
await audit("2-review-confirmed");
await cont.click();

// --- 3. Questions ------------------------------------------------------------------------------
await page.waitForURL("**/questions");
await page.getByRole("radio", { name: /\$150k/ }).first().click();
await audit("3-questions");
await click(/Build my profile/);

// --- 4. Profile --------------------------------------------------------------------------------
await page.waitForURL("**/profile");
await page.getByText(/Estimated/).first().waitFor();
check(/206,300|\$206k/.test(await bodyText()), "profile: computed adjusted gross income appears");
check(/Prototype for illustration only/.test(await bodyText()), "profile: results footer is present");
await audit("4-profile");
await page.getByRole("link", { name: /forecast/i }).or(page.getByRole("button", { name: /forecast/i })).first().click();

// --- 5. Forecast -------------------------------------------------------------------------------
await page.waitForURL("**/forecast");
await page.locator(".recharts-wrapper").first().waitFor({ timeout: 15000 });
let text = await bodyText();
check(/Model not connected/.test(text) && /Placeholder forecast/i.test(text), "forecast: shows 'Model not connected' and 'Placeholder forecast'");
check(!/What drives this/.test(text), "forecast: no 'What drives this' while the model is not connected");
check(/Prototype for illustration only/.test(text), "forecast: results footer is present");
await audit("5-forecast");
await page.getByRole("link", { name: /recommended plan/i }).or(page.getByRole("button", { name: /recommended plan/i })).first().click();

// --- 6. Plan -----------------------------------------------------------------------------------
await page.waitForURL("**/plan");
await page.getByText(/Hold (the next \d+ years of what you will need|\d+% of)/).first().waitFor({ timeout: 20000 });
text = await bodyText();
check(/Search planner \(model not connected\)/.test(text), "plan: labelled 'Search planner (model not connected)'");
check(/Model not connected/.test(text), "plan: the recommender panel shows 'Model not connected'");
check(/Prototype for illustration only/.test(text), "plan: results footer is present");

// The horizon, the table and the strategy's choices all come from the API's plan.
const sent = await planSent();
const horizon = sent.settings.horizon_age;
check(
  new RegExp(`running to ${horizon}\\b`).test(text) && (horizon === 70 || !/\b(?:at|by|to|until) 70\b/.test(text)),
  `plan: the horizon on screen is the API's (age ${horizon}); nothing is hard-coded to 70`,
);
const tableRows = await page.getByRole("row").count();
check(tableRows === sent.rows.length + 1, `plan: the year-by-year table lists all ${sent.rows.length} years (ages ${sent.rows[0].age} to ${sent.rows.at(-1).age}), one row each`);
const choices = sent.strategy.choices;
const chips = (await page.getByRole("list", { name: "The choices in this strategy" }).locator("li").allInnerTexts()).map(squash);
check(chips.length === Object.keys(choices).length, `plan: one chip for each of the strategy's ${Object.keys(choices).length} choices (${chips.length} shown)`);
check(
  chips.some((c) => /^401\(k\) contributions (Pre-tax|Roth)/.test(c)) &&
    chips.some((c) => /^Paying for goals (Sell|Borrow)/.test(c)) &&
    chips.some((c) => (choices.private_credit === "0" ? /^Private credit sleeve Off$/ : new RegExp(`^Private credit sleeve ${choices.private_credit}%$`)).test(c)),
  `plan: the 401(k) type, how goals are funded and the private credit percent (${choices.private_credit}%) are shown in words`,
);
check(!chips.some((c) => /\b(pretax|roth_low|borrow|sell)\b/.test(c)), "plan: no raw API codes show in the choice chips");
check(
  chips.some((c) => (choices.reserve === "off" ? /^Spending reserve Off$/ : new RegExp(`^Spending reserve ${choices.reserve} years$`)).test(c)) &&
    (choices.reserve === "off" || chips.some((c) => c === "Stock share Everything outside the reserve")),
  `plan: the spending reserve (${choices.reserve === "off" ? "off" : `${choices.reserve} years`}) is shown in words, and with one the stock share reads "Everything outside the reserve"`,
);
await audit("6-plan");

// The year-by-year plan arrives after the fixed plan (a background job), unless the API already had it.
if (sent.adaptive) {
  notes.push("plan: the API already had this household's year-by-year plan, so its Refining state was not exercised here (start the API fresh to see it)");
} else {
  const sawRefining = await refiningStatus().first().waitFor({ timeout: 8000 }).then(() => true, () => false);
  check(sawRefining, "plan: the fixed plan is on screen and the header says 'Refining plan…' while the year-by-year plan is worked out");
  check(
    (await viewRadio("Year-by-year plan").isDisabled()) && (await viewRadio("Fixed strategy").getAttribute("aria-checked")) === "true" && (await page.getByRole("row").count()) === sent.rows.length + 1,
    "plan: until it is ready the table shows the fixed strategy, in full, and the year-by-year choice waits",
  );
  await audit("6-plan-refining");
  // Nothing below the table may jump when the year-by-year plan replaces the fixed one in it.
  const nextLink = page.getByRole("link", { name: /Compare with two advisors/ });
  const topBefore = await pageTop(nextLink);
  await waitRefiningGone();
  await page.waitForTimeout(1500);
  const planShift = (await pageTop(nextLink)) - topBefore;
  check(Math.abs(planShift) <= JUMP_TOLERANCE, `plan: no layout jump when the year-by-year plan arrives (the content below the table moved ${planShift}px)`);
}
const adaptive = await adaptiveOf(sent);
await viewRadio("Year-by-year plan").waitFor();
await page.waitForFunction(() => document.querySelector('[role="radio"][aria-checked="true"]')?.textContent?.includes("Year-by-year"), null, { timeout: 15000 }).catch(() => {});
check(
  (await viewRadio("Year-by-year plan").getAttribute("aria-checked")) === "true" && (await refiningStatus().count()) === 0,
  "plan: once the year-by-year plan is ready the 'Refining plan…' state is gone and the table shows it",
);
await checkDepartureRows(adaptive, "plan");
{
  // The two views carry the two plans' own figures: pick a year the planner changed (else the first) and read both.
  const probe = adaptive.rows.find((r) => r.departs) ?? adaptive.rows[0];
  const fixedRow = sent.rows[probe.year_index];
  const inAdaptive = squash(await page.locator(`tr[data-row-key="${probe.year_index}"]`).innerText());
  await viewRadio("Fixed strategy").click();
  const inFixed = squash(await page.locator(`tr[data-row-key="${probe.year_index}"]`).innerText());
  check(
    inAdaptive.includes(money(probe.total_tax)) && inFixed.includes(money(fixedRow.total_tax)) && (await markedYears()).length === 0,
    `plan: the Fixed strategy view shows the fixed plan's rows (age ${probe.age}: total tax ${money(fixedRow.total_tax)}, against ${money(probe.total_tax)} year by year) with no year marked as changed`,
  );
}
check((await page.getByRole("row").count()) === sent.rows.length + 1, `plan: the Fixed strategy view lists all ${sent.rows.length} years too`);

// The fixed strategy's year: decisions with what each is worth, from /plan/year-detail.
const row = page.getByRole("row").nth(26); // a retirement year
await row.click();
await page.getByText(/Marginal federal rate/).first().waitFor({ timeout: 15000 });
text = await bodyText();
check(/Worth|Costs/.test(text), "plan: the side panel shows the value of each decision");
check(new RegExp(`after-tax wealth at ${horizon}\\b`).test(text), `plan: the side panel measures decisions at the API's horizon (after-tax wealth at ${horizon})`);
check(yearDetailRequests > 0 && (await page.getByRole("region", { name: "Why this year" }).count()) === 0, "plan: in the Fixed strategy view the year comes from /plan/year-detail, with no 'Why this year' (that is the planner's)");
await audit("6-plan-drawer");
await page.keyboard.press("Escape");

// The planner's year: "Why this year", from the year-by-year plan itself (no /plan/year-detail request).
await viewRadio("Year-by-year plan").click();
{
  const requestsBefore = yearDetailRequests;
  const target = adaptive.decisions.find((d) => d.departs) ?? adaptive.decisions[0];
  const targetRow = page.locator(`tr[data-row-key="${target.year_index}"]`);
  await targetRow.scrollIntoViewIfNeeded();
  await targetRow.click();
  const why = page.getByRole("region", { name: "Why this year" });
  await why.waitFor({ timeout: 10000 });
  const drawer = page.getByRole("dialog");
  const whyText = squash(await why.innerText());
  check(
    whyText.includes(target.chosen.label) && whyText.includes(target.fixed.label) && whyText.includes(squash(target.why)) && (!target.departs || whyText.includes(changedTag(target.departures))),
    `plan: "Why this year" (age ${target.age}${target.departs ? ", a year the planner changed" : ""}) shows what the planner does (${target.chosen.label}), what the fixed strategy would do (${target.fixed.label}) and the API's own explanation`,
  );
  const alternatives = why.getByRole("list", { name: /best alternatives?/ }).locator("li");
  const altTexts = (await alternatives.allInnerTexts()).map(squash);
  check(
    target.alternatives.length === 2 && altTexts.length === 2 && (await why.getByRole("heading", { name: "The next two best alternatives" }).count()) === 1,
    "plan: 'Why this year' shows the next two best alternatives",
  );
  check(
    target.alternatives.every((a, i) => altTexts[i].includes(a.action.label) && altTexts[i].includes(gapWords(a.ce_gap))),
    `plan: each alternative carries its score difference as the API's ce_gap (${target.alternatives.map((a) => gapWords(a.ce_gap)).join("; ")})`,
  );
  check(
    /rollout score/.test(whyText) && new RegExp(`certainty-equivalent wealth at ${horizon}`).test(whyText),
    "plan: 'Why this year' says the gap is the planner's rollout score, in dollars of certainty-equivalent wealth at the horizon",
  );
  check(
    new RegExp(`certainty-equivalent after-tax wealth at ${horizon} from simulated futures`).test(whyText) && whyText.includes("the guaranteed amount that would feel as good as the uncertain outcome"),
    "plan: 'Why this year' explains the score as certainty-equivalent after-tax wealth from simulated futures, in the Comparison screen's words",
  );
  const retest = squash(await why.locator("p", { hasText: "Re-test." }).innerText());
  const fresh = target.ce_chosen_fresh - target.ce_fixed_fresh;
  const retestOk =
    target.changes_proposed === 0
      ? retest.includes("The search proposed no change")
      : retest.includes(`proposed ${target.changes_proposed} change`) &&
        retest.includes(`re-tested on ${adaptive.plan_path_confirm_k} fresh futures`) &&
        (target.changes_kept === 0 || retest.includes(money(Math.abs(fresh))) || Math.abs(fresh) < 0.5);
  check(retestOk, `plan: the re-test line says ${target.changes_proposed} proposed, ${target.changes_kept} kept${target.changes_kept ? `, ${money(fresh)} ahead on fresh futures` : ""}`);
  // What was done and the year's tax return are the adaptive plan's own (year_details), not the fixed strategy's.
  const detail = adaptive.year_details.find((d) => d.year_index === target.year_index);
  const drawerText = squash(await drawer.innerText());
  const totalLine = detail.tax_lines.find((l) => l.kind === "total") ?? detail.tax_lines.at(-1);
  const dollars = (v) => `${v < 0 ? "−" : ""}$${Math.abs(Math.round(v)).toLocaleString("en-US")}`;
  check(
    detail.decisions.every((d) => drawerText.includes(squash(d.description))) && drawerText.includes(totalLine.label) && drawerText.includes(dollars(totalLine.amount)) && yearDetailRequests === requestsBefore,
    `plan: the decisions and the tax return (${totalLine.label} ${dollars(totalLine.amount)}) are the year-by-year plan's, with no /plan/year-detail request`,
  );
  await audit("6-plan-adaptive-drawer");
  await page.keyboard.press("Escape");

  // A year the planner kept the fixed strategy's action: it says so and what it considered.
  const kept = adaptive.decisions.find((d) => !d.departs);
  if (kept) {
    const keptRow = page.locator(`tr[data-row-key="${kept.year_index}"]`);
    await keptRow.scrollIntoViewIfNeeded();
    await keptRow.click();
    await why.waitFor({ timeout: 10000 });
    const keptText = squash(await why.innerText());
    check(
      keptText.includes("Keeps the fixed strategy's action") && keptText.includes(`scored ${kept.candidates_scored} candidate actions`) && keptText.includes(kept.chosen.label) && keptText.includes(squash(kept.why)),
      `plan: in a year the planner kept the fixed strategy's action (age ${kept.age}) it says so, and how many candidate actions it scored (${kept.candidates_scored})`,
    );
    await page.keyboard.press("Escape");
  }
}
await page.setViewportSize({ width: 768, height: 900 });
await page.waitForTimeout(500);
check((await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 0, "plan: no horizontal overflow at 768px wide");
await page.screenshot({ path: `${OUT}/6-plan-768.png`, fullPage: true });
await page.setViewportSize({ width: 1100, height: 900 });
await page.waitForTimeout(500);
await page.screenshot({ path: `${OUT}/6-plan-1100.png`, fullPage: true });
await page.setViewportSize({ width: 1440, height: 900 });
await audit("6-plan-adaptive");

// --- 8. What-if (opened from Plan) --------------------------------------------------------------
lastWhatIf = null;
await page.getByRole("button", { name: /What if/i }).first().click();
await page.getByRole("button", { name: /Retire at 57/ }).first().click();
await page.getByText(/Re-planning/i).first().waitFor({ timeout: 5000 }).catch(() => notes.push("what-if: 'Re-planning' state was too brief to catch"));
await page.getByText(/Retirement age/).first().waitFor({ timeout: 20000 });
await audit("8-whatif");
check(/62\s*(→|->|to)\s*57|57/.test(await bodyText()), "what-if: the change (retirement age 62 to 57) is listed");
{
  // The fixed plan is on screen at once; the year-by-year plan follows as its own background job.
  const w = await whatIfSent();
  check((await page.locator("tr[data-row-key]").count()) === w.plan.rows.length, `what-if: the new fixed plan is on screen at once, all ${w.plan.rows.length} years`);
  if (w.plan.adaptive) {
    notes.push("what-if (retire at 57): the API already had its year-by-year plan, so its Refining state was not exercised here (start the API fresh to see it)");
  } else {
    const saw = await refiningStatus().first().waitFor({ timeout: 8000 }).then(() => true, () => false);
    check(
      saw && (await viewRadio("Year-by-year plan").isDisabled()) && (await markedYears()).length === 0,
      "what-if: 'Refining plan…' shows for the new plan, whose fixed table is usable meanwhile and carries none of the old year-by-year plan's marks",
    );
    check(/still being refined/.test(await page.getByRole("region", { name: "What changed in the plan" }).innerText()), "what-if: the 'What changed' panel shows the strategy at once and says the planner's choices follow");
    await waitRefiningGone();
  }
  const adaptive57 = await adaptiveOf(w.plan);
  await page.waitForFunction(() => document.querySelector('[role="radio"][aria-checked="true"]')?.textContent?.includes("Year-by-year"), null, { timeout: 15000 }).catch(() => {});
  check((await viewRadio("Year-by-year plan").getAttribute("aria-checked")) === "true" && (await refiningStatus().count()) === 0, "what-if: when the new year-by-year plan arrives 'Refining plan…' is gone and the table shows it");
  await checkDepartureRows(adaptive57, "what-if");
  await checkWhatChanged({ plan: sent, adaptive }, { plan: w.plan, adaptive: adaptive57 }, w.shock, chips, "what-if (retire at 57)");
  await audit("8-whatif-adaptive");
}
await page.getByRole("button", { name: /Reset/i }).first().click();
await page.keyboard.press("Escape");
await page.getByText(/What-if applied/).first().waitFor({ state: "detached", timeout: 15000 });
// The unmodified plan's year-by-year plan was kept in the app: it is back at once, with no new job to wait for.
check((await refiningStatus().count()) === 0 && (await viewRadio("Year-by-year plan").getAttribute("aria-checked")) === "true", "after a reset: the unmodified plan's year-by-year plan is back at once (kept from before the what-if), with no 'Refining plan…'");
await checkDepartureRows(adaptive, "after a reset");

// --- 7. Compare --------------------------------------------------------------------------------
await page.getByRole("link", { name: /Compare with two advisors/i }).or(page.getByRole("button", { name: /Compare with two advisors/i })).first().click();
await page.waitForURL("**/compare");
await page.getByText(/Where the advantage comes from/).first().waitFor({ timeout: 20000 });
text = await bodyText();
const flat = squash(text);
for (const label of [`Typical outcome at ${horizon}`, "Bad case", "Median advantage", "Risk-adjusted advantage", "Lifetime taxes", "Chance of a shortfall", "Strategies searched"]) {
  check(text.includes(label), `compare: shows "${label}"`);
}
check(/Prototype for illustration only/.test(text), "compare: results footer is present");

// (1) Both advantage measures, against both advisors: defined in words, with a sign, a rate, a range and dollars.
const s = sent.settings;
check(
  flat.includes(`Difference in the typical (median) after-tax wealth at ${s.horizon_age}, as a yearly growth-rate difference.`),
  "compare: the median advantage is defined in plain words",
);
check(
  flat.includes(`The same, but using certainty-equivalent wealth: the guaranteed amount that would feel as good as the risky range of outcomes to a household with risk aversion ${s.risk_aversion}. It is the planner's own objective, so it rewards a smaller bad case, not just a higher middle.`),
  "compare: the risk-adjusted advantage is defined in plain words",
);
check((flat.match(/[+\u2212]\d+\.\d{2}% a year/g) ?? []).length >= 4, "compare: both measures show a signed percentage a year, against both advisors");
const against = { good_ria: "a good RIA", typical_advisor: "a typical advisor" };
const MEASURES = [
  ["Median advantage", "median", "median_low", "median_high"],
  ["Risk-adjusted advantage", "risk_adjusted", "risk_adjusted_low", "risk_adjusted_high"],
];
for (const baseline of sent.baselines) {
  for (const [label, value, low, high] of MEASURES) {
    const a = baseline.advantage;
    const cell = squash(await page.getByRole("group", { name: `${label} against ${against[baseline.key]}` }).innerText());
    check(
      cell.includes(`${rate(a[value])} a year`) &&
        cell.includes(`90% range: ${rate(a[low])} to ${rate(a[high])} when the futures are resampled`) &&
        /[+\u2212]\$\d/.test(cell),
      `compare: ${label} against ${against[baseline.key]} is ${rate(a[value])} a year, with its 90% range and dollars`,
    );
  }
}

// (2) Each advisor: its label and its definition in full (on the page, not in a tooltip), beside the plan's figures.
for (const baseline of sent.baselines) {
  check(
    flat.includes(squash(baseline.definition)) && (await page.getByRole("heading", { name: baseline.label, exact: true }).count()) >= 1,
    `compare: ${baseline.label} is labelled and its definition is shown in full`,
  );
}
check(
  flat.includes(`measured on ${s.n_eval_paths} fresh futures the search never saw`) && (await page.getByRole("heading", { name: "How we measure" }).count()) === 1,
  `compare: a note says the figures are measured on ${s.n_eval_paths} fresh futures the search never saw, and a "How we measure" panel follows`,
);

// (3) The fan chart: the Donabach plan (the best fixed strategy), the adaptive planner and both advisors; the typical
// advisor is told apart by a dashed line and the adaptive planner by a dotted one, as well as by colour.
const section = await adaptiveOf(sent);
await page.getByText("The four strategies side by side").first().waitFor({ timeout: 150000 });
check((await refiningStatus().count()) === 0, "compare: with the year-by-year plan ready there is no 'Refining plan…' state");
const legend = page.getByRole("list", { name: "Chart legend" });
const legendItems = (await visibleLegend().allInnerTexts()).map(squash);
check(
  legendItems.length === 4 && legendItems.some((t) => /^Typical advisor/.test(t)) && legendItems.some((t) => /^Adaptive planner/.test(t)) && legendItems.some((t) => /^Donabach plan/.test(t)),
  `compare: the chart legend names the plan, the adaptive planner and both advisors (${legendItems.join(", ")})`,
);
check(
  (await legend.locator("li", { hasText: "Typical advisor" }).locator("line[stroke-dasharray]").count()) === 1 &&
    (await legend.locator("li", { hasText: "Adaptive planner" }).locator("line[stroke-dasharray]").count()) === 1 &&
    (await legend.locator("li", { hasText: "Donabach plan" }).locator("line[stroke-dasharray]").count()) === 0 &&
    (await legend.locator("li", { hasText: "Good RIA" }).locator("line[stroke-dasharray]").count()) === 0,
  "compare: the typical advisor (dashed) and the adaptive planner (dotted) are marked in the legend by their line style, and the other two are solid",
);
const settleLines = (count) =>
  page.waitForFunction((n) => {
    const lines = [...document.querySelectorAll("path.recharts-line-curve")];
    return lines.length === n && lines.every((l) => !(l.getAttribute("stroke-dasharray") ?? "").includes("px"));
  }, count, { timeout: 8000 }).catch(() => notes.push("compare: the chart lines were still animating at the check"));
const drawnLines = () =>
  page.evaluate(() => [...document.querySelectorAll("path.recharts-line-curve")].map((l) => ({ stroke: l.getAttribute("stroke"), dash: l.getAttribute("stroke-dasharray") })));
await settleLines(4);
const chartLines = await drawnLines();
const dashed = chartLines.filter((l) => l.dash);
check(
  chartLines.length === 4 &&
    dashed.length === 2 &&
    /typical/.test(dashed.find((l) => /typical/.test(l.stroke))?.stroke ?? "") &&
    /adaptive/.test(dashed.find((l) => /adaptive/.test(l.stroke))?.stroke ?? "") &&
    dashed[0].dash !== dashed[1].dash,
  "compare: the chart draws four median lines; the typical advisor's is dashed, the adaptive planner's dotted (a different pattern), the other two solid",
);
const medianAtEnd = (key) => money(section.strategies.find((x) => x.key === key).fan.p50.at(-1));
const alt = await page
  .locator("figure")
  .filter({ has: page.locator(".recharts-wrapper") })
  .first()
  .evaluate((figure) => document.getElementById(figure.getAttribute("aria-describedby") ?? "")?.innerText ?? "");
check(
  squash(alt) ===
    `At age ${s.horizon_age} the median after-tax wealth is ${medianAtEnd("best_fixed")} with the Donabach plan, ${medianAtEnd("adaptive")} with the adaptive planner, ${medianAtEnd("good_ria")} with a good RIA and ${medianAtEnd("typical_advisor")} with a typical advisor.`,
  `compare: the chart has a text alternative stating the four medians at age ${s.horizon_age} as the API has them (${squash(alt).slice(0, 70)}...)`,
);
check(
  section.strategies.find((x) => x.key === "best_fixed").fan.p50.at(-1) === sent.fan.p50.at(-1) && section.strategies.find((x) => x.key === "typical_advisor").fan.p50.at(-1) === sent.baselines.find((b) => b.key === "typical_advisor").fan.p50.at(-1),
  "compare: the fixed-strategy and advisor lines of the four-way chart are the same futures as the plan's own (the API's fans agree)",
);

// (5) The ranked table says it lists the best of the whole menu, and how they were screened and scored.
check(
  flat.includes(
    `Best ${sent.searched.length} of ${s.strategies_searched.toLocaleString("en-US")} strategies: every strategy was screened on 100 futures and the best ${sent.searched.length} were scored on all ${s.n_paths}`,
  ),
  `compare: the strategies table says it lists the best ${sent.searched.length} of ${s.strategies_searched.toLocaleString("en-US")}`,
);
check((await page.locator("tr[data-row-key]").count()) <= sent.searched.length + 1, "compare: the table never lists more strategies than the API returned");

// (6) The four strategies side by side, what judgment over time adds, and how the planner works.
await checkFourWay(section, s.horizon_age, "compare", page);
await checkJudgment(section, s.horizon_age, "compare", page);
{
  const how = page.getByRole("button", { name: "How the year-by-year planner works" });
  check((await how.getAttribute("aria-expanded")) === "false", "compare: 'How the year-by-year planner works' is folded away until opened");
  await how.click();
  const body = squash(await page.locator(`[id="${await how.getAttribute("aria-controls")}"]`).innerText());
  const n = (x) => x.toLocaleString("en-US");
  const secs = (x) => `${Number(x.toPrecision(2))} seconds`;
  check(body.includes(squash(section.search)), "compare: it gives the API's own account of the planner's search, word for word");
  check(
    body.includes(`Futures scored for each candidate action ${n(section.k)}`) &&
      body.includes(`Fresh futures a proposed change is re-tested on ${n(section.confirm_k)}`) &&
      body.includes(`Futures the verdict is measured on ${n(section.n_eval_paths)}`) &&
      body.includes(`${secs(section.seconds_per_path)} per simulated future`),
    `compare: it states the settings: ${section.k} futures per candidate, ${section.confirm_k} for the re-test, ${section.n_eval_paths} for the verdict, ${secs(section.seconds_per_path)} per future`,
  );
}

await page.screenshot({ path: `${OUT}/7-compare-full.png`, fullPage: true });
await audit("7-compare");
const spilled = await spill("main section");
check(spilled.length === 0, `compare: nothing spills out of its panel${spilled.length ? ` (${spilled.join(", ")})` : ""}`);
await page.setViewportSize({ width: 1100, height: 900 });
await page.waitForTimeout(500);
check((await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 0, "compare: no horizontal overflow at 1100px wide either");
await page.screenshot({ path: `${OUT}/7-compare-1100.png`, fullPage: true });
await page.setViewportSize({ width: 768, height: 900 });
await page.waitForTimeout(500);
check((await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 0, "compare: no horizontal overflow at 768px wide");
await page.screenshot({ path: `${OUT}/7-compare-768.png`, fullPage: true });
await page.setViewportSize({ width: 1440, height: 900 });

// A what-if on the Comparison screen: the page narrows beside the panel, and every figure says how far it moved,
// both advantage measures included.
lastWhatIf = null;
await page.getByRole("button", { name: /What if/i }).first().click();
await page.getByRole("button", { name: /Market drops 30%/ }).first().click();
await page.getByText(/What-if applied/).first().waitFor({ timeout: 30000 });
await page.waitForTimeout(1500);
const moved = await page.getByRole("group", { name: /advantage against/ }).allInnerTexts();
check(moved.length === 4 && moved.every((t) => /(?:Up|Down) [\d.]+ percentage points? from your plan|No change from your plan/.test(t)), "compare with a what-if: both advantage measures, against both advisors, show how far they moved");
text = await bodyText();
check(/(?:Up|Down) [\d.$,kM]+ from your plan/.test(text), "compare with a what-if: the plan's own figures show how far they moved");
const drop = await whatIfSent();
check(
  !!drop.shock && drop.shock.year === 1 && drop.shock.equity_return === -0.3 && drop.plan.settings.market_shock?.year === 1,
  `what-if: the market drop is the API's shock (year ${drop.shock?.year}, ${drop.shock ? Math.round(drop.shock.equity_return * 100) : "?"}% stocks) and the plan carries it`,
);
const refiningNow = !drop.plan.adaptive && (await refiningStatus().count()) > 0;
await audit("7-compare-whatif");
const spilledNarrow = await spill("main section");
check(spilledNarrow.length === 0, `compare with a what-if: nothing spills out of its panel${spilledNarrow.length ? ` (${spilledNarrow.join(", ")})` : ""}`);
if (drop.plan.adaptive) {
  notes.push("what-if (market drop): the API already had its year-by-year plan, so its Refining state was not exercised here (start the API fresh to see it)");
} else {
  check(refiningNow, "compare with a what-if: the new fixed results are on screen at once and 'Refining plan…' marks where the year-by-year panels will be");
  await settleLines(3);
  check(
    (await drawnLines()).length === 3 &&
      (await visibleLegend().count()) === 3 &&
      (await page.getByRole("table", { name: /The four strategies side by side/ }).count()) === 0 &&
      /still being refined/.test(await page.getByRole("region", { name: "What changed in the plan" }).innerText()),
    "compare with a what-if: while it is refined the chart keeps its three lines (and the legend its room for the fourth), no stale four-way table shows, and the 'What changed' panel says the planner's choices follow",
  );
  // The placeholder holds the room of the panels that replace it: nothing below moves when they arrive.
  const below = page.getByRole("heading", { name: "Where the advantage comes from" });
  const topBefore = await pageTop(below);
  await waitRefiningGone();
  await page.waitForTimeout(1500);
  const compareShift = (await pageTop(below)) - topBefore;
  check(Math.abs(compareShift) <= JUMP_TOLERANCE, `compare with a what-if: no layout jump when the year-by-year panels replace the placeholder (the content below moved ${compareShift}px)`);
}
const adaptiveDrop = await adaptiveOf(drop.plan);
await page.getByRole("table", { name: /The four strategies side by side/ }).waitFor({ timeout: 30000 });
await settleLines(4);
check((await drawnLines()).length === 4 && (await visibleLegend().count()) === 4 && (await refiningStatus().count()) === 0, "compare with a what-if: when the year-by-year plan arrives the chart gains the adaptive line and 'Refining plan…' is gone");
await checkFourWay(adaptiveDrop, s.horizon_age, "compare with a what-if", page);
await checkJudgment(adaptiveDrop, s.horizon_age, "compare with a what-if", page);
await checkWhatChanged({ plan: sent, adaptive: section }, { plan: drop.plan, adaptive: adaptiveDrop }, drop.shock, chips, "what-if (market drop)", drop.changes.some((c) => c.field !== "market_shock"));
await audit("7-compare-whatif-adaptive");
const spilledAfter = await spill("main section");
check(spilledAfter.length === 0, `compare with a what-if: nothing spills out of its panel once the year-by-year panels are in${spilledAfter.length ? ` (${spilledAfter.join(", ")})` : ""}`);

// The year of the drop on the Plan screen: marked on its row, and "Why this year" says the market fell.
await page.getByRole("navigation", { name: "Progress" }).getByRole("link", { name: /Plan/ }).click();
await page.waitForURL("**/plan");
await page.getByText(/What-if applied/).first().waitFor({ timeout: 15000 });
await viewRadio("Year-by-year plan").waitFor();
{
  const shockYear = drop.shock.year;
  const decision = adaptiveDrop.decisions[shockYear];
  const fell = `The market ${decision.facts.market_return < 0 ? "fell" : "rose"} ${Math.round(Math.abs(decision.facts.market_return) * 100)}% this year.`;
  const shockRow = page.locator(`tr[data-row-key="${shockYear}"]`);
  check(
    decision.facts.market_return === drop.shock.equity_return && squash(await shockRow.innerText()).includes(`Market falls ${Math.round(Math.abs(drop.shock.equity_return) * 100)}%`),
    `what-if: the year of the drop (age ${decision.age}) is marked on its row, and the planner's facts for it carry the same return (${Math.round(decision.facts.market_return * 100)}%)`,
  );
  await shockRow.scrollIntoViewIfNeeded();
  await shockRow.click();
  const why = page.getByRole("region", { name: "Why this year" });
  await why.waitFor({ timeout: 10000 });
  check(squash(await why.innerText()).includes(fell), `what-if: "Why this year" for the year of the drop says "${fell}"`);
  await page.keyboard.press("Escape");
  const before = page.locator('tr[data-row-key="0"]');
  await before.scrollIntoViewIfNeeded();
  await before.click();
  await why.waitFor({ timeout: 10000 });
  check(/before the market drop/.test(await why.innerText()), "what-if: \"Why this year\" for the year before the drop says the planner cannot see it coming");
  await page.keyboard.press("Escape");
}
await page.getByRole("navigation", { name: "Progress" }).getByRole("link", { name: /Compare/ }).click();
await page.waitForURL("**/compare");
await page.getByText(/What-if applied/).first().waitFor({ timeout: 15000 });
await page.getByRole("button", { name: /Reset/i }).first().click();
await page.getByText(/What-if applied/).first().waitFor({ state: "detached", timeout: 15000 });
await page.keyboard.press("Escape");

// --- Reload and determinism --------------------------------------------------------------------------
// The headline figures: both advantage measures with their ranges, and the outcome cards.
const figure = async (p) =>
  squash(
    [await p.getByRole("region", { name: "Donabach's advantage" }).innerText(), await p.getByRole("region", { name: "Donabach against two advisors" }).innerText()].join(" "),
  );
const outcomeLabel = `Typical outcome at ${horizon}`;
const gist = (f) => (f.match(/[+\u2212]\d+\.\d{2}% a year/g) ?? []).slice(0, 2).join(", ");
await page.getByText(outcomeLabel).first().waitFor({ timeout: 20000 });
const first = await figure(page);
await page.reload({ waitUntil: "networkidle" });
await page.getByText(outcomeLabel).first().waitFor({ timeout: 20000 });
check((await figure(page)) === first, `reload keeps the viewer's answers and gives identical numbers (${gist(first)}, ...)`);

// Two brand-new sessions (nothing saved) bootstrap from the sample documents: demo mode must give the
// same numbers every time.
const fresh = [];
for (let i = 0; i < 2; i++) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(BASE + "/compare", { waitUntil: "networkidle" });
  await p.getByText(outcomeLabel).first().waitFor({ timeout: 30000 });
  fresh.push(await figure(p));
  await ctx.close();
}
check(fresh[0] === fresh[1], `demo mode: two fresh sessions show identical numbers (${gist(fresh[0])}, ...)`);

// --- The demo household: its year-by-year plan comes with the plan, and there is no Refining state ----------------
// (The API has had up to 60 s to precompute it: see section 0.)
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const issues = [];
  p.on("console", (m) => {
    if (m.type() === "error") issues.push(m.text());
  });
  p.on("pageerror", (e) => issues.push(e.message));
  await p.addInitScript(() => {
    window.__refiningSeen = false;
    const look = () => {
      if (document.body && document.body.innerText.includes("Refining plan")) window.__refiningSeen = true;
    };
    new MutationObserver(look).observe(document, { childList: true, subtree: true, characterData: true });
  });
  const planResponse = p.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/plan");
  await p.goto(BASE + "/plan", { waitUntil: "networkidle" });
  const demoSent = await (await planResponse).json();
  await p.getByText(/Hold (the next \d+ years of what you will need|\d+% of)/).first().waitFor({ timeout: 30000 });
  await p.waitForTimeout(1000);
  check(
    !!demoSent.adaptive && demoSent.adaptive.from_cache === true && !demoSent.adaptive_job,
    "demo household: the API sends its year-by-year plan with the plan itself (precomputed), not a job to wait for",
  );
  check(
    !(await p.evaluate(() => window.__refiningSeen)) && (await viewRadio("Year-by-year plan", p).getAttribute("aria-checked")) === "true",
    "demo household: the page shows the year-by-year plan at once and never shows 'Refining plan…'",
  );
  await checkDepartureRows(demoSent.adaptive, "demo household", p);
  check(issues.length === 0, `demo household: no console errors${issues.length ? ` (${issues[0]})` : ""}`);
  await ctx.close();
}

// --- The year-by-year job fails: the page says so plainly and the fixed plan stays usable --------------------------
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const issues = [];
  p.on("console", (m) => {
    if (m.type() === "error") issues.push(m.text());
  });
  p.on("pageerror", (e) => issues.push(e.message));
  // The plan comes back as the API sends it for a household it has not planned before: the fixed plan and a job id.
  await p.route("**/api/plan", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const response = await route.fetch();
    const json = await response.json();
    json.adaptive = null;
    json.adaptive_job = "e2e-broken-job";
    await route.fulfill({ response, json });
  });
  const message = "The simulation ran out of memory (an error this test made up)";
  let polls = 0;
  await p.route("**/api/plan/adaptive/e2e-broken-job", async (route) => {
    polls++;
    // two answers of "running" (a window of about a second and a half to see the progress), then the failure
    const job = polls <= 2 ? { status: "running", progress: 0.4, error: null } : { status: "error", progress: 0.4, error: message };
    await route.fulfill({ json: { id: "e2e-broken-job", result: null, ...job } });
  });
  await p.goto(BASE + "/plan", { waitUntil: "networkidle" });
  await p.getByText(/Hold (the next \d+ years of what you will need|\d+% of)/).first().waitFor({ timeout: 30000 });
  await p.waitForFunction(() => /Refining plan…\s*40%/.test(document.body.innerText), null, { timeout: 10000 }).catch(() => {});
  check(/Refining plan….*40%/.test(squash(await refiningStatus(p).first().innerText().catch(() => ""))), "failed job: while the job runs the header shows its progress ('Refining plan… 40%')");
  const alert = p.getByRole("alert").filter({ hasText: "The year-by-year plan could not be completed" });
  await alert.first().waitFor({ timeout: 10000 });
  check(squash(await alert.first().innerText()).includes(message), `failed job: the Plan screen says plainly that it could not be completed, with the error text ("${message}")`);
  check(
    (await p.getByText("Year-by-year plan unavailable").count()) === 1 &&
      (await refiningStatus(p).count()) === 0 &&
      (await viewRadio("Year-by-year plan", p).isDisabled()) &&
      (await viewRadio("Fixed strategy", p).getAttribute("aria-checked")) === "true" &&
      (await p.locator("tr[data-row-key]").count()) === demo.plan.rows.length,
    "failed job: the header notes it is unavailable, 'Refining plan…' is gone, and the fixed plan's table is whole and selected",
  );
  await p.getByRole("row").nth(26).click();
  await p.getByText(/Marginal federal rate/).first().waitFor({ timeout: 15000 });
  check(/Worth|Costs/.test(await p.evaluate(() => document.body.innerText)), "failed job: the fixed plan stays usable (a year opens with the value of each decision)");
  await p.keyboard.press("Escape");
  await p.getByRole("navigation", { name: "Progress" }).getByRole("link", { name: /Compare/ }).click();
  await p.waitForURL("**/compare");
  await p.getByText(/Where the advantage comes from/).first().waitFor({ timeout: 30000 });
  const compareAlert = squash(await p.getByRole("alert").filter({ hasText: "The year-by-year plan could not be completed" }).first().innerText());
  await p.waitForFunction(() => document.querySelectorAll("path.recharts-line-curve").length === 3, null, { timeout: 8000 }).catch(() => {});
  check(
    compareAlert.includes(message) && /final and unaffected/.test(compareAlert) && (await p.locator("path.recharts-line-curve").count()) === 3 && (await visibleLegend(p).count()) === 3,
    "failed job: the Comparison screen says so with the error text, keeps its three-line chart and results, and shows no four-way panel",
  );
  check(issues.length === 0, `failed job: no console errors${issues.length ? ` (${issues[0]})` : ""}`);
  await ctx.close();
}

// --- A newer what-if abandons the older year-by-year job, and a late result for it is never shown ------------------
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const demoSection = demo.plan.adaptive;
  // What job A would answer if it were still being listened to: the demo plan with a mark nothing else has.
  const late = structuredClone(demoSection);
  late.rows[0] = { ...late.rows[0], departs: true, departures: ["k401"] };
  let whatIfCalls = 0;
  await p.route("**/api/plan/whatif", async (route) => {
    const body = JSON.parse(route.request().postData() ?? "{}");
    // Ask for no year-by-year plan (so the API starts no real job), then hand the page a job id of our own.
    const response = await route.fetch({ postData: JSON.stringify({ ...body, adaptive: false }) });
    const json = await response.json();
    whatIfCalls++;
    json.plan.adaptive = null;
    json.plan.adaptive_job = whatIfCalls === 1 ? "e2e-job-a" : "e2e-job-b";
    await route.fulfill({ response, json });
  });
  const pollsA = [];
  const pollsB = [];
  const dropsA = []; // DELETE requests: the page telling the API it no longer wants a job
  const dropsB = [];
  let releaseA;
  const heldA = new Promise((resolve) => (releaseA = resolve));
  await p.route("**/api/plan/adaptive/e2e-job-a", async (route) => {
    if (route.request().method() === "DELETE") {
      dropsA.push(Date.now());
      return route.fulfill({ status: 204 });
    }
    pollsA.push(Date.now());
    if (pollsA.length === 1) {
      await heldA; // A's first answer is in flight while the viewer changes the plan again
      return route.fulfill({ json: { id: "e2e-job-a", status: "done", progress: 1, error: null, result: late } });
    }
    return route.fulfill({ json: { id: "e2e-job-a", status: "running", progress: 0.2, error: null, result: null } });
  });
  await p.route("**/api/plan/adaptive/e2e-job-b", async (route) => {
    if (route.request().method() === "DELETE") {
      dropsB.push(Date.now());
      return route.fulfill({ status: 204 });
    }
    pollsB.push(Date.now());
    const done = pollsB.length >= 4;
    await route.fulfill({ json: { id: "e2e-job-b", status: done ? "done" : "running", progress: done ? 1 : 0.5, error: null, result: done ? demoSection : null } });
  });
  await p.goto(BASE + "/plan", { waitUntil: "networkidle" });
  await p.getByText(/Hold (the next \d+ years of what you will need|\d+% of)/).first().waitFor({ timeout: 30000 });
  await p.getByRole("button", { name: /What if/i }).first().click();
  await p.getByRole("button", { name: /Spouse B changes jobs/ }).first().click();
  await p.getByText(/What-if applied/).first().waitFor({ timeout: 30000 });
  for (let i = 0; i < 100 && pollsA.length === 0; i++) await p.waitForTimeout(100);
  await p.getByRole("button", { name: /Move home purchase to next year/ }).first().click();
  for (let i = 0; i < 200 && pollsB.length === 0; i++) await p.waitForTimeout(100);
  await refiningStatus(p).first().waitFor({ timeout: 10000 });
  check(
    pollsA.length === 1 && pollsB.length > 0 && (await viewRadio("Year-by-year plan", p).isDisabled()) && (await markedYears(p)).length === 0,
    "newer what-if: its fixed plan is on screen with its own job being followed; neither the base plan's year-by-year plan nor the older job's is shown against it",
  );
  releaseA(); // the older job's answer now arrives, late
  await waitRefiningGone(p, 60000);
  await p.waitForTimeout(2000);
  const expected = demoSection.rows.filter((r) => r.departs).map((r) => r.year_index);
  check(pollsA.length === 1, `newer what-if: the older job is not polled again once the plan has changed (${pollsA.length} poll in all, ${pollsB.length} for the newer one)`);
  check(
    dropsA.length === 1 && dropsB.length === 0,
    `newer what-if: the page tells the API to drop the older job exactly once (${dropsA.length}), and never the job it is following (${dropsB.length})`,
  );
  check(
    JSON.stringify(await markedYears(p)) === JSON.stringify(expected) && !(await p.evaluate(() => document.body.innerText)).includes("Changed: 401(k) type"),
    "newer what-if: the older job's late result is never shown; the table shows the newer job's year-by-year plan",
  );
  await ctx.close();
}

// --- Other paths worth guarding ---------------------------------------------------------------------
// A fresh session with demo mode off: nothing is preloaded, and a direct visit to a later step goes back.
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await p.addInitScript(() => localStorage.setItem("donabach-demo-mode", "false"));
  await p.goto(BASE + "/plan", { waitUntil: "networkidle" });
  await p.waitForURL((u) => u.pathname === "/", { timeout: 15000 });
  check(true, "demo mode off: a direct visit to /plan goes back to Upload");
  await p.waitForTimeout(1500);
  check(!/Ready/.test(await p.evaluate(() => document.body.innerText)), "demo mode off: no documents are preloaded");

  // A PDF the demo does not read is accepted but reported plainly.
  const pdf = Buffer.from("JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3VyY2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9NZWRpYUJveCBbIDAgMCA1OTUuMjc1NiA4NDEuODg5OCBdIC9QYXJlbnQgNiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKNCAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUgL1BhZ2VzIDYgMCBSIC9UeXBlIC9DYXRhbG9nCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9BdXRob3IgKGFub255bW91cykgL0NyZWF0aW9uRGF0ZSAoRDoyMDAwMDEwMTAwMDAwMCswMCcwMCcpIC9DcmVhdG9yIChhbm9ueW1vdXMpIC9LZXl3b3JkcyAoKSAvTW9kRGF0ZSAoRDoyMDAwMDEwMTAwMDAwMCswMCcwMCcpIC9Qcm9kdWNlciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gXChvcGVuc291cmNlXCkpIAogIC9TdWJqZWN0ICh1bnNwZWNpZmllZCkgL1RpdGxlICh1bnRpdGxlZCkgL1RyYXBwZWQgL0ZhbHNlCj4+CmVuZG9iago2IDAgb2JqCjw8Ci9Db3VudCAxIC9LaWRzIFsgMyAwIFIgXSAvVHlwZSAvUGFnZXMKPj4KZW5kb2JqCjcgMCBvYmoKPDwKL0xlbmd0aCA5MQo+PgpzdHJlYW0KMSAwIDAgMSAwIDAgY20gIEJUIC9GMSAxMiBUZiAxNC40IFRMIEVUCkJUIDEgMCAwIDEgMTAwIDcwMCBUbSAoQSBzaG9wcGluZyBsaXN0KSBUaiBUKiBFVAogCmVuZHN0cmVhbQplbmRvYmoKeHJlZgowIDgKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDYxIDAwMDAwIG4gCjAwMDAwMDAwOTIgMDAwMDAgbiAKMDAwMDAwMDE5OSAwMDAwMCBuIAowMDAwMDAwNDAyIDAwMDAwIG4gCjAwMDAwMDA0NzAgMDAwMDAgbiAKMDAwMDAwMDczMSAwMDAwMCBuIAowMDAwMDAwNzkwIDAwMDAwIG4gCnRyYWlsZXIKPDwKL0lEIApbPDFjMTc4MTk4ZmJkZmE1MWIyNTk5NWQ4OWQ0MTAyMDQzPjwxYzE3ODE5OGZiZGZhNTFiMjU5OTVkODlkNDEwMjA0Mz5dCiUgUmVwb3J0TGFiIGdlbmVyYXRlZCBQREYgZG9jdW1lbnQgLS0gZGlnZXN0IChvcGVuc291cmNlKQoKL0luZm8gNSAwIFIKL1Jvb3QgNCAwIFIKL1NpemUgOAo+PgpzdGFydHhyZWYKOTMwCiUlRU9GCg==", "base64");
  await p.locator('input[type="file"]').setInputFiles({ name: "shopping-list.pdf", mimeType: "application/pdf", buffer: pdf });
  await p.getByText(/Not recognised|Not recognized/i).first().waitFor({ timeout: 15000 });
  check(true, "upload: a PDF the demo does not read is reported as not recognised");
  await ctx.close();
}

// No tax form: the household cannot be built, the missing values are asked for by name, and the tax
// picture that follows is labelled as an estimate.
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(BASE + "/", { waitUntil: "networkidle" });
  await p.waitForFunction(() => (document.body.innerText.match(/Ready/g) ?? []).length >= 3, null, { timeout: 20000 });
  await p.getByRole("button", { name: /remove/i }).first().click(); // drops the Form 1040
  await p.getByRole("link", { name: /Review extracted numbers/ }).or(p.getByRole("button", { name: /Review extracted numbers/ })).first().click();
  await p.waitForURL("**/review");
  await p.getByRole("button", { name: /Keep as is/ }).first().click();
  await p.getByRole("button", { name: /Confirm and continue/ }).or(p.getByRole("link", { name: /Confirm and continue/ })).first().click();
  await p.waitForURL("**/questions");
  await p.getByRole("button", { name: /Build my profile/ }).click();
  await p.waitForURL("**/review");
  const asked = await p.evaluate(() => document.body.innerText);
  check(/Taxpayer age/.test(asked) && /Taxpayer W-2 wages \(box 1\)/.test(asked), "no tax form: the missing values are asked for by name");
  await p.getByLabel(/Taxpayer age/).first().fill("38");
  await p.getByLabel(/Taxpayer W-2 wages/).first().fill("115500");
  await p.keyboard.press("Tab");
  await p.getByRole("button", { name: /Confirm and continue/ }).or(p.getByRole("link", { name: /Confirm and continue/ })).first().click();
  await p.waitForURL("**/questions");
  await p.getByRole("button", { name: /Build my profile/ }).click();
  await p.waitForURL("**/profile", { timeout: 20000 });
  await p.getByText(/Estimated from your wages and balances/).first().waitFor({ timeout: 10000 });
  check(true, "no tax form: the profile's tax picture is labelled as an estimate");
  await ctx.close();
}

// --- The showcase flow: household card, strategy waterfall, wealth over time (e2e/showcase.mjs) ----------------------
// Its own section of checks, all read from the API's /showcase responses; they count with the rest.
await runShowcase({ browser, base: BASE, out: OUT, check, notes });

// --- Round two: both valuations, charitable giving, planning styles (e2e/valuations.mjs, giving.mjs, styles.mjs) --------------------
// Each reads its expectations from what the API sent the browser; they count with the rest.
await runValuations({ browser, base: BASE, out: OUT, check, notes });
await runGiving({ browser, base: BASE, out: OUT, check, notes });
await runStyles({ browser, base: BASE, out: OUT, check, notes });

await browser.close();
for (const n of notes) console.log(` note  ${n}`);
console.log(failures.length ? `\n${failures.length} of ${checks} check(s) failed:\n - ${failures.join("\n - ")}` : `\nAll checks passed (${checks} of ${checks})`);
process.exit(failures.length ? 1 : 0);
