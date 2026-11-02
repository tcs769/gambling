// The wording sweep: every new screen (Documents, Reading, Review, Goals, Invest, Compare) in a browser, at 1440 and 320 wide.
// None of Donabach, Gracchi, Tanaka, learned, AI, predict, trained, model; no "plan" a customer can read; the tab title is Waramoug;
// no explanatory text (no sentence-length paragraphs besides a flag and the one disclaimer); no sideways scrolling.
import { isMain, runAlone, newPage, toGoals, visibleText } from "./portal.mjs";

const FORBIDDEN = [
  /donabach/i,
  /gracchi/i,
  /tanaka/i,
  /learned/i,
  /\bAI\b/,
  /predict/i,
  /trained/i,
  /\bmodels?\b/i,
  /\bplans?\b/i,
  /simulated futures/i,
  /rollout/i,
  /median/i,
];
const DISCLAIMER = "Illustration based on simulated outcomes. Not investment advice.";

async function sweep(page, label, check, { disclaimer = false } = {}) {
  const { text, attrs, title } = await visibleText(page);
  const all = [text, ...attrs];
  const hits = FORBIDDEN.flatMap((re) =>
    all
      .filter((t) => re.test(t) && !(disclaimer && t.includes(DISCLAIMER) && !re.test(t.replace(DISCLAIMER, ""))))
      .map((t) => `${re}: ${t.slice(0, 50)}`),
  );
  check(hits.length === 0, `${label}: no forbidden words (${hits.slice(0, 2).join(" | ")})`);
  check(title === "Waramoug", `${label}: the tab title is Waramoug (${title})`);
  const count = text.split(DISCLAIMER).length - 1;
  check(
    count === (disclaimer ? 1 : 0),
    `${label}: ${disclaimer ? "exactly one disclaimer line" : "no disclaimer or footer"} (${count})`,
  );
  const html = await page.content();
  check(
    !/donabach|gracchi|tanaka/i.test(html.replace(/<script[\s\S]*?<\/script>/g, "")),
    `${label}: no code names in the page markup`,
  );
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check(over <= 0, `${label}: no sideways scrolling (${over})`);
}

export async function runWording({ browser, base, check }) {
  for (const width of [1440, 320]) {
    const { context, page, issues } = await newPage(browser, { width, height: width === 320 ? 700 : 900 });
    const tag = `${width}px`;
    await page.goto(`${base}/`, { waitUntil: "networkidle" });
    await sweep(page, `${tag} Documents`, check);
    await page.getByRole("button", { name: "Use sample documents" }).click();
    await page.waitForURL("**/reading");
    await page.waitForTimeout(1400);
    await sweep(page, `${tag} Reading`, check);
    await page.waitForURL("**/review", { timeout: 15_000 });
    await page.locator("[data-field-key]").first().waitFor();
    await sweep(page, `${tag} Review`, check);
    await page.getByRole("button", { name: "Confirm", exact: true }).click();
    await page.getByRole("button", { name: "Confirm and continue" }).click();
    await page.waitForURL("**/goals");
    await page.getByRole("radio", { name: "60", exact: true }).waitFor();
    await sweep(page, `${tag} Goals`, check);
    await page.getByRole("button", { name: "Invest", exact: true }).click();
    await page.waitForURL("**/invest", { timeout: 60_000 });
    await sweep(page, `${tag} Invest`, check, { disclaimer: true });
    await page.getByRole("button", { name: "Compare" }).click();
    await page.waitForURL("**/compare");
    await sweep(page, `${tag} Compare`, check, { disclaimer: true });
    check(issues.length === 0, `${tag}: no console errors (${issues.join(" | ")})`);
    await context.close();
  }

  // the text on the screens is labels: no paragraph longer than a sentence besides the flag
  const { context, page } = await newPage(browser);
  await toGoals(page, base);
  const long = await page.evaluate(() =>
    [...document.querySelectorAll("main p")].map((p) => p.innerText).filter((t) => t.split(/\s+/).length > 12),
  );
  check(long.length === 0, `Goals has no explanatory paragraphs (${long.join(" | ")})`);
  await context.close();
}

if (isMain(import.meta.url)) await runAlone(runWording, "wording");
