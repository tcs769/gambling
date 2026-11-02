// Reading (/reading): the list of documents found appears one at a time (about half a second each, about 3 s in all) and is exactly
// the API's `documents`; the screen then moves to Review by itself. Coming back to it does not replay or move on.
import { isMain, runAlone, newPage, apiPost, docLabel } from "./portal.mjs";

export async function runReading({ browser, base, check }) {
  const api = await apiPost(base, "/portal/documents/sample", undefined);
  const expected = api.documents.map(docLabel);

  const { context, page, issues } = await newPage(browser);
  await page.goto(`${base}/`, { waitUntil: "networkidle" });
  const started = Date.now();
  await page.getByRole("button", { name: "Use sample documents" }).click();
  await page.waitForURL("**/reading", { timeout: 10_000 });
  const items = page.locator('[data-testid="read-item"]');

  const seen = [];
  let advancedAt = null;
  while (Date.now() - started < 12_000) {
    const url = new URL(page.url()).pathname;
    if (url === "/review") {
      advancedAt = Date.now() - started;
      break;
    }
    seen.push(await items.count().catch(() => 0));
    await page.waitForTimeout(150);
  }
  check(advancedAt !== null, "Reading moves to Review by itself");
  check(advancedAt >= 2000 && advancedAt <= 5500, `it takes about 3 s (${advancedAt} ms)`);
  const distinct = [...new Set(seen)];
  check(
    distinct.length >= 4 && Math.max(...seen) <= expected.length,
    `the list grows a document at a time (${distinct.join(" > ")})`,
  );
  check(
    seen.every((n, i) => i === 0 || n >= seen[i - 1]),
    "documents never disappear from the list",
  );

  // the list, once shown, is the API's (read it on a second visit, which shows it whole)
  await page.getByRole("link", { name: "Documents" }).click();
  await page.waitForURL(`${base}/`);
  await page.goto(`${base}/reading`, { waitUntil: "networkidle" });
  const names = await page.locator('[data-testid="read-item"] span:nth-child(2)').allInnerTexts();
  check(
    JSON.stringify(names) === JSON.stringify(expected),
    `the list is exactly the API's documents: ${names.join(", ")}`,
  );
  await page.waitForTimeout(1800);
  check(new URL(page.url()).pathname === "/reading", "coming back to Reading does not move on by itself");
  check(await page.getByRole("button", { name: "Next" }).isEnabled(), "Next goes on to Review");
  await page.getByRole("button", { name: "Next" }).click();
  await page.waitForURL("**/review");
  check(issues.length === 0, `no console errors (${issues.join(" | ")})`);
  await context.close();
}

if (isMain(import.meta.url)) await runAlone(runReading, "reading");
