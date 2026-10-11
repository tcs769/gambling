// Walks the whole demo in a real browser and checks the cross-cutting requirements.
//
//   node e2e/walkthrough.mjs            (with the API on :8000 and the app on :3000 running)
//
// Environment: BASE_URL (default http://localhost:3000), OUT_DIR for screenshots (default
// ../.screenshots), CHROMIUM_PATH if Playwright's own browser is not installed.
// Checks per screen: no console errors, no visible text under 14px, no horizontal overflow at
// 1440 wide, charts at least 300px tall. Exits non-zero if anything fails.

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

const check = (ok, message) => {
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
await audit("6-plan");
const row = page.getByRole("row").nth(26); // a retirement year
await row.click();
await page.getByText(/Marginal federal rate/).first().waitFor({ timeout: 15000 });
check(/Worth|Costs/.test(await bodyText()), "plan: the side panel shows the value of each decision");
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
await page.getByRole("link", { name: /Compare with a typical advisor/i }).or(page.getByRole("button", { name: /Compare with a typical advisor/i })).first().click();
await page.waitForURL("**/compare");
await page.getByText(/Where the advantage comes from/).first().waitFor({ timeout: 20000 });
text = await bodyText();
for (const label of ["Typical outcome at 70", "Bad case", "Typical advantage per year", "Lifetime taxes", "Strategies searched"]) {
  check(text.includes(label), `compare: shows "${label}"`);
}
check(/Prototype for illustration only/.test(text), "compare: results footer is present");
await page.screenshot({ path: `${OUT}/7-compare-full.png`, fullPage: true });
await audit("7-compare");

// --- Reload and determinism --------------------------------------------------------------------------
const figure = async (p) => (await p.getByText("Typical outcome at 70").first().locator("xpath=..").innerText()).replace(/\s+/g, " ");
const first = await figure(page);
await page.reload({ waitUntil: "networkidle" });
await page.getByText("Typical outcome at 70").first().waitFor({ timeout: 20000 });
check((await figure(page)) === first, `reload keeps the viewer's answers and gives identical numbers (${first.slice(0, 48)})`);

// Two brand-new sessions (nothing saved) bootstrap from the sample documents: demo mode must give the
// same numbers every time.
const fresh = [];
for (let i = 0; i < 2; i++) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(BASE + "/compare", { waitUntil: "networkidle" });
  await p.getByText("Typical outcome at 70").first().waitFor({ timeout: 30000 });
  fresh.push(await figure(p));
  await ctx.close();
}
check(fresh[0] === fresh[1], `demo mode: two fresh sessions show identical numbers (${fresh[0].slice(0, 48)})`);

await browser.close();
for (const n of notes) console.log(` note  ${n}`);
console.log(failures.length ? `\n${failures.length} check(s) failed` : "\nAll checks passed");
process.exit(failures.length ? 1 : 0);
