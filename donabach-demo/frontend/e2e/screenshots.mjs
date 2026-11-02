// Full-page screenshots at 1440x900 of every screen of the flow, into OUT_DIR (default ../.screenshots).
//   BASE_URL=http://localhost:3000 OUT_DIR=/some/dir node e2e/screenshots.mjs
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { isMain, runAlone, newPage } from "./portal.mjs";

export async function runShots({ browser, base, check }) {
  const out = resolve(process.env.OUT_DIR ?? fileURLToPath(new URL("../.screenshots", import.meta.url)));
  mkdirSync(out, { recursive: true });
  const { context, page, issues } = await newPage(browser, { width: 1440, height: 900 });
  const shot = async (name) => {
    await page.waitForTimeout(500);
    await page.screenshot({ path: join(out, `${name}.png`), fullPage: true });
  };
  const hash = async (tab) => {
    await page.getByRole("tablist", { name: "Invest sections" }).getByRole("tab", { name: tab, exact: true }).click();
    await page.waitForTimeout(300);
  };
  const invest = async () => {
    await page.getByRole("button", { name: "Invest", exact: true }).click();
    await page.waitForURL("**/invest", { timeout: 60_000 });
    await page.getByTestId("projected-wealth").waitFor();
  };
  const tabs = async (prefix) => {
    await shot(`${prefix}_overview`);
    await hash("Holdings");
    for (const account of ["Brokerage", "401(k)/IRA", "Roth IRA"]) {
      await page.getByRole("tab", { name: account, exact: true }).click();
      await shot(`${prefix}_holdings_${account.replace(/\W+/g, "").toLowerCase()}`);
    }
    await hash("Taxes");
    await shot(`${prefix}_taxes`);
    await hash("Retirement income");
    await shot(`${prefix}_retirement`);
    await hash("Goals");
    await shot(`${prefix}_goals`);
    await hash("Overview");
  };

  await page.goto(`${base}/`, { waitUntil: "networkidle" });
  await shot("01_documents");
  await page.getByRole("button", { name: "Use sample documents" }).click();
  await page.waitForURL("**/reading");
  await page.getByRole("list").first().locator("li").nth(1).waitFor();
  await shot("02_reading");
  await page.waitForURL("**/review", { timeout: 15_000 });
  await page.locator("[data-field-key]").first().waitFor();
  await shot("03_review");
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await page.getByRole("button", { name: "Confirm and continue" }).click();
  await page.waitForURL("**/goals");
  await page.getByRole("radio", { name: "60", exact: true }).waitFor();
  await shot("04_goals");
  await invest();
  await tabs("05_invest");
  await page.getByRole("button", { name: "Compare" }).click();
  await page.waitForURL("**/compare");
  await shot("06_compare");
  await page.getByRole("button", { name: "Back" }).click();
  await page.getByRole("button", { name: "Back" }).click();
  await page.waitForURL("**/goals");
  await page.getByRole("radio", { name: "Job loss next year" }).check();
  await invest();
  await page.getByTestId("what-changed").waitFor();
  await shot("07_what_changed_job_loss");
  await page.getByRole("button", { name: "Back" }).click();
  await page.waitForURL("**/goals");
  await page.getByRole("radio", { name: "No", exact: true }).check();
  await page.getByRole("radio", { name: "65", exact: true }).check();
  await invest();
  await shot("08_invest_retirement_65");
  await page.getByRole("button", { name: "Compare" }).click();
  await page.waitForURL("**/compare");
  await shot("09_compare_retirement_65");
  check(issues.length === 0, `no console errors (${issues.join(" | ")})`);
  await context.close();
}

if (isMain(import.meta.url)) await runAlone(runShots, "screenshots");
