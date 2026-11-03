// Reading (/reading): the mockup's file card (file name, percent, bar, the four documents Waiting then Found), staged over about 2.2 s,
// then Review after a beat (about 3 s in all). The list is exactly the API's `documents`. Coming back does not replay or move on.
import { isMain, runAlone, newPage, apiPost, docLabel } from "./portal.mjs";

export async function runReading({ browser, base, check }) {
  const api = await apiPost(base, "/portal/documents/sample", undefined);
  const expected = api.documents.map(docLabel);

  const { context, page, issues } = await newPage(browser);
  await page.goto(`${base}/`, { waitUntil: "networkidle" });
  const started = Date.now();
  await page.getByRole("button", { name: "Use sample documents" }).click();
  await page.waitForURL("**/reading", { timeout: 10_000 });
  check(
    (await page.locator("main h1").innerText()) === "Reading your documents",
    "the heading is 'Reading your documents'",
  );
  check(
    await page.getByText("This takes a few seconds.", { exact: true }).isVisible(),
    "the lede is 'This takes a few seconds.'",
  );
  const items = page.locator('[data-testid="read-item"]');
  const firstNames = await items.locator("span:nth-child(1)").allInnerTexts();
  check(
    JSON.stringify(firstNames) === JSON.stringify(expected),
    `all documents are listed from the start, under the mockup's names: ${firstNames.join(", ")}`,
  );
  check(
    (await page.locator(".num", { hasText: "%" }).count()) >= 1 &&
      (await page.getByText(api.name, { exact: true }).isVisible()),
    `the card shows the file name (${api.name}) and a percent`,
  );

  const found = [];
  const percents = [];
  let advancedAt = null;
  while (Date.now() - started < 12_000) {
    if (new URL(page.url()).pathname === "/review") {
      advancedAt = Date.now() - started;
      break;
    }
    const n = await items.evaluateAll((els) => els.filter((e) => e.dataset.found === "true").length).catch(() => null);
    const pct = await page
      .locator('[data-testid="read-percent"]')
      .innerText()
      .catch(() => null);
    if (n !== null) found.push(n);
    if (pct !== null) percents.push(parseInt(pct, 10));
    await page.waitForTimeout(120);
  }
  check(advancedAt !== null, "Reading moves to Review by itself");
  check(advancedAt >= 2200 && advancedAt <= 5000, `it takes about 3 s (${advancedAt} ms)`);
  const distinct = [...new Set(found)];
  check(
    distinct.length >= 4 && Math.max(...found) <= expected.length,
    `documents turn from Waiting to Found one at a time (${distinct.join(" > ")})`,
  );
  check(
    found.every((n, i) => i === 0 || n >= found[i - 1]),
    "a Found document never goes back to Waiting",
  );
  check(
    percents.every((n, i) => i === 0 || n >= percents[i - 1]) && Math.max(...percents) >= 80,
    `the percent only goes up (${percents.slice(0, 3).join(", ")} ... ${Math.max(...percents)})`,
  );

  // the list, once read, is the API's, all Found, at 100%, and does not replay
  await page.getByRole("link", { name: "Documents" }).click();
  await page.waitForURL(`${base}/`);
  await page.goto(`${base}/reading`, { waitUntil: "networkidle" });
  const names = await items.locator("span:nth-child(1)").allInnerTexts();
  const marks = await items.locator("span:nth-child(2)").allInnerTexts();
  check(
    JSON.stringify(names) === JSON.stringify(expected),
    `the list is exactly the API's documents: ${names.join(", ")}`,
  );
  check(
    marks.every((m) => m === "Found"),
    "on a second visit every document is Found",
  );
  check((await page.locator('[data-testid="read-percent"]').innerText()) === "100%", "at 100%");
  await page.waitForTimeout(1800);
  check(new URL(page.url()).pathname === "/reading", "coming back to Reading does not move on by itself");
  check(await page.getByRole("button", { name: "Next" }).isEnabled(), "Next goes on to Review");
  await page.getByRole("button", { name: "Next" }).click();
  await page.waitForURL("**/review");
  check(issues.length === 0, `no console errors (${issues.join(" | ")})`);
  await context.close();
}

if (isMain(import.meta.url)) await runAlone(runReading, "reading");
