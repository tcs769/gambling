// Helpers shared by the portal's browser checks (documents, reading, review, goals, navigation, wording).
// Run one alone:  BASE_URL=http://localhost:3000 node e2e/review.mjs   (the app is `next start`, the API is behind its /api proxy).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { openPage } from "./lib.mjs";

export { isMain, runAlone, squash } from "./lib.mjs";

export const PDF_PATH = fileURLToPath(new URL("../../fixtures/smith_documents.pdf", import.meta.url));
export const PDF_BYTES = readFileSync(PDF_PATH);

/** The API through the app's own proxy, as the browser sees it. */
export const apiGet = async (base, path) => (await fetch(`${base}/api${path}`)).json();
export const apiPost = async (base, path, body) =>
  (
    await fetch(`${base}/api${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  ).json();

/** What a document is called on screen (the same words as src/lib/portal-format.ts). */
export const KIND_LABEL = {
  form_1040: "Tax return",
  brokerage_statement: "Brokerage statement",
  retirement_401k: "401(k) statement",
  roth_ira: "Roth IRA statement",
};
export const docLabel = (doc) => KIND_LABEL[doc.doc_kind] ?? doc.title;

export const dollarsWhole = (v) => `$${Math.round(v).toLocaleString("en-US")}`;
export const money2 = (v) => {
  const r = Math.round(v * 100) / 100;
  return `$${r.toLocaleString("en-US", { minimumFractionDigits: Number.isInteger(r) ? 0 : 2, maximumFractionDigits: 2 })}`;
};

export const newPage = (browser, opts) => openPage(browser, opts);

/** Open the app and load John Smith's PDF with "Use sample documents"; waits for Review. */
export async function toReview(page, base, { sample = true } = {}) {
  await page.goto(`${base}/`, { waitUntil: "networkidle" });
  if (sample) await page.getByRole("button", { name: "Use sample documents" }).click();
  await page.waitForURL("**/review", { timeout: 20_000 });
  await page.locator("[data-field-key]").first().waitFor();
}

/** Confirm the flagged field and go to Goals. */
export async function toGoals(page, base) {
  await toReview(page, base);
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await page.getByRole("button", { name: "Confirm and continue" }).click();
  await page.waitForURL("**/goals");
  await page.getByRole("radio", { name: "60", exact: true }).waitFor();
}

/** Every field row on Review: [key, label, value shown]. */
export const reviewRows = (page) =>
  page.$$eval("[data-field-key]", (items) =>
    items.map((li) => {
      const input = li.querySelector("input");
      const label = li.querySelector("label")?.innerText.replace(/\s+/g, " ").trim() ?? "";
      const value = input ? input.value : (li.querySelector("[class*=text]")?.textContent ?? "").trim();
      return [li.getAttribute("data-field-key"), label, value];
    }),
  );

/** The visible text of the page (what a customer can read), plus every attribute text a reader or tooltip could show. */
export const visibleText = (page) =>
  page.evaluate(() => {
    const attrs = [...document.querySelectorAll("[aria-label],[title],[alt],[placeholder]")].flatMap((el) =>
      ["aria-label", "title", "alt", "placeholder"].map((a) => el.getAttribute(a)).filter(Boolean),
    );
    return { text: document.body.innerText, attrs, title: document.title };
  });

export const sessionState = (page) =>
  page.evaluate(() => JSON.parse(window.sessionStorage.getItem("waramoug.portal.v1") ?? "null"));
