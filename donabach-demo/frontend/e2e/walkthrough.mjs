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

import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { chromium } from "playwright-core";

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
page.on("response", async (response) => {
  if (response.request().method() === "POST" && new URL(response.url()).pathname === "/api/plan") {
    lastPlan = await response.json().catch(() => lastPlan);
  }
});
const planSent = async () => {
  for (let i = 0; i < 100 && !lastPlan; i++) await page.waitForTimeout(100);
  if (!lastPlan) throw new Error("the plan response was never seen");
  return lastPlan;
};
const squash = (text) => text.replace(/\s+/g, " ").trim();
// A yearly rate the way the screen writes it: +0.27%, −0.04% (a true minus sign).
const rate = (fraction) => {
  const v = Number((fraction * 100).toFixed(2));
  return v === 0 ? "0.00%" : `${v > 0 ? "+" : "\u2212"}${Math.abs(v).toFixed(2)}%`;
};
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
await page.getByText(/Hold \d+% of long-term money/).first().waitFor({ timeout: 20000 });
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
await audit("6-plan");
const row = page.getByRole("row").nth(26); // a retirement year
await row.click();
await page.getByText(/Marginal federal rate/).first().waitFor({ timeout: 15000 });
text = await bodyText();
check(/Worth|Costs/.test(text), "plan: the side panel shows the value of each decision");
check(new RegExp(`after-tax wealth at ${horizon}\\b`).test(text), `plan: the side panel measures decisions at the API's horizon (after-tax wealth at ${horizon})`);
await audit("6-plan-drawer");
await page.keyboard.press("Escape");

// --- 8. What-if (opened from Plan) --------------------------------------------------------------
await page.getByRole("button", { name: /What if/i }).first().click();
await page.getByRole("button", { name: /Retire at 57/ }).first().click();
await page.getByText(/Re-planning/i).first().waitFor({ timeout: 5000 }).catch(() => notes.push("what-if: 'Re-planning' state was too brief to catch"));
await page.getByText(/Retirement age/).first().waitFor({ timeout: 20000 });
await audit("8-whatif");
check(/62\s*(→|->|to)\s*57|57/.test(await bodyText()), "what-if: the change (retirement age 62 to 57) is listed");
await page.getByRole("button", { name: /Reset/i }).first().click();
await page.keyboard.press("Escape");

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

// (3) The fan chart: the plan and both advisors, the typical advisor told apart by line style as well as colour.
const legend = page.getByRole("list", { name: "Chart legend" });
const legendItems = (await legend.locator("li").allInnerTexts()).map(squash);
check(legendItems.length === 3 && legendItems.some((t) => /^Typical advisor/.test(t)), `compare: the chart legend names the plan and both advisors (${legendItems.join(", ")})`);
check(
  (await legend.locator("li", { hasText: "Typical advisor" }).locator("line[stroke-dasharray]").count()) === 1 &&
    (await legend.locator("li", { hasText: "Donabach plan" }).locator("line[stroke-dasharray]").count()) === 0 &&
    (await legend.locator("li", { hasText: "Good RIA" }).locator("line[stroke-dasharray]").count()) === 0,
  "compare: the typical advisor is dashed in the legend and the other two are solid",
);
await page.waitForFunction(() => {
  const lines = [...document.querySelectorAll("path.recharts-line-curve")];
  return lines.length === 3 && lines.every((l) => !(l.getAttribute("stroke-dasharray") ?? "").includes("px"));
}, null, { timeout: 8000 }).catch(() => notes.push("compare: the chart lines were still animating at the check"));
const chartLines = await page.evaluate(() =>
  [...document.querySelectorAll("path.recharts-line-curve")].map((l) => ({ stroke: l.getAttribute("stroke"), dash: l.getAttribute("stroke-dasharray") })),
);
check(
  chartLines.length === 3 && chartLines.filter((l) => l.dash).length === 1 && /typical/.test(chartLines.find((l) => l.dash)?.stroke ?? ""),
  "compare: the chart draws three median lines and only the typical advisor's is dashed",
);
const alt = await page
  .locator("figure")
  .filter({ has: page.locator(".recharts-wrapper") })
  .first()
  .evaluate((figure) => document.getElementById(figure.getAttribute("aria-describedby") ?? "")?.innerText ?? "");
check(
  new RegExp(`^At age ${s.horizon_age} the median after-tax wealth is \\$[\\d.]+[kM]? with the Donabach plan, \\$[\\d.]+[kM]? with a good RIA and \\$[\\d.]+[kM]? with a typical advisor\\.$`).test(squash(alt)),
  `compare: the chart has a text alternative stating the medians at age ${s.horizon_age} (${squash(alt).slice(0, 60)}...)`,
);

// (5) The ranked table says it lists the best of the whole menu, and how they were screened and scored.
check(
  flat.includes(
    `Best ${sent.searched.length} of ${s.strategies_searched.toLocaleString("en-US")} strategies: every strategy was screened on 100 futures and the best ${sent.searched.length} were scored on all ${s.n_paths}`,
  ),
  `compare: the strategies table says it lists the best ${sent.searched.length} of ${s.strategies_searched.toLocaleString("en-US")}`,
);
check((await page.locator("tr[data-row-key]").count()) <= sent.searched.length + 1, "compare: the table never lists more strategies than the API returned");

await page.screenshot({ path: `${OUT}/7-compare-full.png`, fullPage: true });
await audit("7-compare");
const spilled = await spill("main section");
check(spilled.length === 0, `compare: nothing spills out of its panel${spilled.length ? ` (${spilled.join(", ")})` : ""}`);
await page.setViewportSize({ width: 1100, height: 900 });
await page.waitForTimeout(500);
check((await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 0, "compare: no horizontal overflow at 1100px wide either");
await page.setViewportSize({ width: 1440, height: 900 });

// A what-if on the Comparison screen: the page narrows beside the panel, and every figure says how far it moved,
// both advantage measures included.
await page.getByRole("button", { name: /What if/i }).first().click();
await page.getByRole("button", { name: /Market drops 30%/ }).first().click();
await page.getByText(/What-if applied/).first().waitFor({ timeout: 30000 });
await page.waitForTimeout(1500);
const moved = await page.getByRole("group", { name: /advantage against/ }).allInnerTexts();
check(moved.length === 4 && moved.every((t) => /(?:Up|Down) [\d.]+ percentage points? from your plan|No change from your plan/.test(t)), "compare with a what-if: both advantage measures, against both advisors, show how far they moved");
text = await bodyText();
check(/(?:Up|Down) [\d.$,kM]+ from your plan/.test(text), "compare with a what-if: the plan's own figures show how far they moved");
await audit("7-compare-whatif");
const spilledNarrow = await spill("main section");
check(spilledNarrow.length === 0, `compare with a what-if: nothing spills out of its panel${spilledNarrow.length ? ` (${spilledNarrow.join(", ")})` : ""}`);
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

await browser.close();
for (const n of notes) console.log(` note  ${n}`);
console.log(failures.length ? `\n${failures.length} of ${checks} check(s) failed:\n - ${failures.join("\n - ")}` : `\nAll checks passed (${checks} of ${checks})`);
process.exit(failures.length ? 1 : 0);
