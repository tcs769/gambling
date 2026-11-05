// Shared by the Invest, Compare and recording checks: the figures the way the screens write them (written again here, not imported
// from src/), the API's plans, and the way to reach Invest.
import { apiPost, apiGet, dollarsWhole, toGoals } from "./portal.mjs";

export const DISCLAIMER = "Illustration based on simulated outcomes. Not investment advice.";
export const wealthM = (v) => (Math.abs(v) >= 999_500 ? `$${(v / 1_000_000).toFixed(2)}M` : dollarsWhole(v));
export const dash = (v) => (Math.abs(v) < 0.5 ? "–" : dollarsWhole(v));
export const pct0 = (f) => `${Math.round(f * 100)}%`;
export const pctTrim = (f) => `${+(f * 100).toFixed(2)}%`;
export const pct2 = (f) => `${(f * 100).toFixed(2)}%`;
export const signedPct2 = (f) => `${f < 0 ? "−" : "+"}${(Math.abs(f) * 100).toFixed(2)}%`;
export const feeLine = (d, r, two = false) => `${dollarsWhole(d)} (${two ? pct2(r) : pctTrim(r)})`;

/** Every body row of a table: the text of each cell. */
export const tableRows = (locator) =>
  locator.evaluate((table) =>
    [...table.querySelectorAll("tbody tr")].map((tr) =>
      [...tr.children].map((c) => c.innerText.replace(/\s+/g, " ").trim()),
    ),
  );
export const footRows = (locator) =>
  locator.evaluate((table) =>
    [...table.querySelectorAll("tfoot tr")].map((tr) =>
      [...tr.children].map((c) => c.innerText.replace(/\s+/g, " ").trim()),
    ),
  );

/** The cells of every row of a table, or of a list's items (the text of each direct child), squashed. */
export const listRows = (locator) =>
  locator.evaluate((list) =>
    [...list.children].map((li) => [...li.children].map((c) => c.innerText.replace(/\s+/g, " ").trim())),
  );

/** The words of a move in the mockup's list, built again here from the API's move (not imported from src/). */
export function moveText(m) {
  const amt = m.amount === null || m.amount === undefined ? 0 : m.amount;
  const has = Math.abs(amt) >= 0.5;
  const d = m.detail ? ` (${m.detail.charAt(0).toLowerCase()}${m.detail.slice(1)})` : "";
  switch (m.key) {
    case "invest":
      return `Invested your savings in the target mix${has ? `, ${dollarsWhole(amt)}` : ""}`;
    case "lots":
      return "Selling the highest-cost shares first";
    case "harvest":
      return `${m.title}${has ? `, ${dollarsWhole(amt)} harvested so far` : ""}`;
    case "conversion":
    case "conversion_next":
      return `Convert ${dollarsWhole(amt)} from your 401(k) / IRA to your Roth${d}`;
    case "k401":
      return `Raise your 401(k) contribution to ${dollarsWhole(amt)} through your employer`;
    default:
      return `${m.title}${has ? `, ${dollarsWhole(amt)}` : ""}${d}`;
  }
}
export const STATUS = {
  done: "Done",
  ongoing: "Ongoing",
  scheduled: "Scheduled",
  needs_ok: "Needs your OK",
  your_step: "Your step",
};

/** The API's plan for John Smith with the given answers changed (the same call the app makes). */
export async function planFromApi(base, { patch = {}, event = "none", previous = null, label = null } = {}) {
  const docs = await apiPost(base, "/portal/documents/sample", undefined);
  const defaults = await apiGet(base, "/portal/defaults");
  const answers = { ...defaults, income_change: event === "none" ? "none" : event, ...patch };
  const { household } = await apiPost(base, "/portal/household", { document_id: docs.id, overrides: {}, answers });
  return apiPost(base, "/portal/invest", { household, event, previous_plan_id: previous, change_label: label });
}

/** From the sample documents to the Invest page with John Smith's values (returns the milliseconds the plan step took). */
export async function toInvest(page, base) {
  await toGoals(page, base);
  const t0 = Date.now();
  await page.getByRole("button", { name: "Invest", exact: true }).click();
  await page.waitForURL("**/invest", { timeout: 60_000 });
  await page.getByRole("tablist", { name: "Invest sections" }).waitFor();
  return Date.now() - t0;
}

/** Click a tab of the Invest page. */
export const openTab = async (page, name) => {
  await page.getByRole("tab", { name, exact: true }).click();
  await page.locator(`[role="tabpanel"][id^="invest-panel"]`).waitFor();
};
