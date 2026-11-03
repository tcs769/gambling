// Navigation: the left rail (240px, four steps, the name at the bottom), steps not yet reached are not links, going back keeps
// everything (and the PDF is never sent twice), a reload keeps the state, a narrow window gets a top bar.
import { isMain, runAlone, newPage, toGoals, sessionState, openAll } from "./portal.mjs";

const railSteps = (page) =>
  page.$$eval('nav[aria-label="Steps"] li', (items) =>
    items.map((li) => ({
      text: li.innerText.replace(/\s+/g, " ").trim(),
      link: !!li.querySelector("a"),
      current: !!li.querySelector('[aria-current="step"]'),
      disabled: li.querySelector("[aria-disabled]") !== null,
    })),
  );

export async function runNavigation({ browser, base, check }) {
  const { context, page, issues } = await newPage(browser);
  const sent = [];
  page.on(
    "request",
    (r) => r.method() === "POST" && /\/portal\/documents\/(sample|upload)/.test(r.url()) && sent.push(r.url()),
  );

  // --- the rail on Documents
  await page.goto(`${base}/`, { waitUntil: "networkidle" });
  const rail = page.locator("aside");
  const box = await rail.boundingBox();
  check(Math.round(box.width) === 240, `the rail is 240px wide (${box.width})`);
  check((await rail.innerText()).includes("WARAMOUG"), "the WARAMOUG wordmark is in the rail");
  const font = await rail
    .locator("a")
    .first()
    .evaluate((el) => {
      const s = getComputedStyle(el);
      return { family: s.fontFamily, spacing: s.letterSpacing };
    });
  check(
    /Cambria/.test(font.family) && parseFloat(font.spacing) > 1.5,
    `the wordmark is Cambria, letter-spaced (${font.family.slice(0, 20)}, ${font.spacing})`,
  );
  check(
    (await rail
      .locator("a")
      .first()
      .evaluate((el) => getComputedStyle(el).fontSize)) === "30px" &&
      (await rail.getByText("Wealth management", { exact: true }).isVisible()),
    "the wordmark is 30px with a small 'Wealth management' under it",
  );
  let steps = await railSteps(page);
  check(
    JSON.stringify(steps.map((s) => s.text.replace(/^\d /, ""))) ===
      JSON.stringify(["Documents", "Review", "Goals", "Invest"]),
    "four steps: Documents, Review, Goals, Invest",
  );
  check(
    steps[0].current && steps.slice(1).every((s) => !s.link && s.disabled),
    "on a fresh start only Documents is a link; the others are not reachable",
  );
  check(
    (await rail.innerText()).replace(/\s+/g, " ").trimEnd().endsWith("John Smith Signed in"),
    "the name and 'Signed in' are at the bottom of the rail",
  );
  check((await rail.locator("[class*=avatar]").count()) === 0, "there is no avatar circle");
  const stepsLook = await page
    .locator('nav[aria-label="Steps"] li')
    .first()
    .evaluate((li) => li.dataset.state);
  check(stepsLook === "current", "the current step is marked (data-state current)");
  check(
    (await page.locator("aside").evaluate((el) => getComputedStyle(el).position)) === "sticky",
    "the rail stays in place",
  );

  // --- opening a later screen directly with nothing loaded goes back to Documents
  await page.goto(`${base}/goals`, { waitUntil: "networkidle" });
  await page.waitForURL(`${base}/`);
  check(true, "/goals with nothing loaded sends the customer back to Documents");
  await page.goto(`${base}/invest`, { waitUntil: "networkidle" });
  await page.waitForURL(`${base}/`);

  // --- through the flow
  await page.getByRole("button", { name: "Use sample documents" }).click();
  await page.waitForURL("**/reading");
  steps = await railSteps(page);
  check(steps[0].current && steps[0].link, "Reading counts as Documents in the rail");
  await page.waitForURL("**/review", { timeout: 15_000 });
  steps = await railSteps(page);
  check(
    steps[1].current && steps[0].link && !steps[2].link && !steps[3].link,
    "on Review: Documents and Review are links, Goals and Invest are not",
  );

  // an edit and a confirmation, then Goals with another answer
  await page.locator("[data-field-key]").first().waitFor();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await openAll(page);
  const wages = page.locator('[data-field-key="wages_1a"] input');
  await wages.fill("163415");
  await wages.press("Enter");
  await page.getByRole("button", { name: "Confirm and continue" }).click();
  await page.waitForURL("**/goals");
  steps = await railSteps(page);
  check(steps[2].current && steps[1].link && !steps[3].link, "on Goals: Invest is still not reachable");
  await page.getByRole("radio", { name: "65", exact: true }).check();

  // back with the Back button and with the rail
  await page.getByRole("button", { name: "Back" }).click();
  await page.waitForURL("**/review");
  await page.locator("[data-field-key]").first().waitFor();
  check((await wages.inputValue()) === "163,415", "Back to Review keeps the edit");
  check(
    (await page.locator('[data-field-key="brokerage_total_value"]').getAttribute("data-waiting")) === "false",
    "and the confirmation",
  );
  check(
    await page.getByRole("button", { name: "Confirm and continue" }).isEnabled(),
    "so Confirm and continue is still enabled",
  );
  await page.getByRole("button", { name: "Back" }).click();
  await page.waitForURL(`${base}/`);
  check(
    (await page.locator('[data-testid="loaded-file"]').innerText()).includes("smith_documents.pdf"),
    "Back to Documents shows the PDF that was dropped",
  );
  check(sent.length === 1, `the PDF was sent once (${sent.length} request)`);
  await page.getByRole("button", { name: "Next" }).click();
  await page.waitForURL("**/review");
  check(sent.length === 1, "going forward again does not send it again");
  await page.locator('nav[aria-label="Steps"]').getByRole("link", { name: "Goals" }).click();
  await page.waitForURL("**/goals");
  check(
    (await page
      .getByRole("radiogroup", { name: "When do you want to retire?" })
      .locator("input:checked + span")
      .innerText()) === "65",
    "the rail's Goals step keeps the answer (65)",
  );

  // reload keeps everything
  await page.reload({ waitUntil: "networkidle" });
  await page.getByRole("radio", { name: "65", exact: true }).waitFor();
  check(
    (await page
      .getByRole("radiogroup", { name: "When do you want to retire?" })
      .locator("input:checked + span")
      .innerText()) === "65",
    "a reload on Goals keeps the answer",
  );
  steps = await railSteps(page);
  check(steps[2].current && steps[1].link, "and the steps already visited");
  await page.locator('nav[aria-label="Steps"]').getByRole("link", { name: "Review" }).click();
  await page.waitForURL("**/review");
  await page.locator("[data-field-key]").first().waitFor();
  check(
    (await page.locator('[data-field-key="wages_1a"] input').inputValue()) === "163,415",
    "a reload keeps the edit",
  );
  const saved = await sessionState(page);
  check(
    saved.docs.id === "smith-bundle" && saved.overrides.wages_1a === 163415,
    "the state is mirrored to sessionStorage",
  );
  check(sent.length === 1, "the PDF still has not been sent twice");

  // --- Invest and Compare share the Invest step
  await page.locator('nav[aria-label="Steps"]').getByRole("link", { name: "Goals" }).click();
  await page.waitForURL("**/goals");
  await page.getByRole("radio", { name: "60", exact: true }).check();
  await page.getByRole("button", { name: "Invest", exact: true }).click();
  await page.waitForURL("**/invest", { timeout: 60_000 });
  steps = await railSteps(page);
  check(steps.every((s) => s.link) && steps[3].current, "after Invest all four steps are links; Invest is current");
  await page.getByRole("button", { name: "Compare" }).click();
  await page.waitForURL("**/compare");
  steps = await railSteps(page);
  check(steps[3].current, "Compare counts as Invest in the rail");
  await page.getByRole("button", { name: "Back" }).click();
  await page.waitForURL("**/invest");
  check(issues.length === 0, `no console errors (${issues.join(" | ")})`);
  await context.close();

  // --- a narrow window: the rail becomes a top bar and nothing scrolls sideways
  for (const width of [800, 320]) {
    const n = await newPage(browser, { width, height: 700 });
    await toGoals(n.page, base);
    const bar = await n.page.locator("aside").boundingBox();
    const over = await n.page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check(
      bar.width >= width - 1 && bar.height < 150 && bar.y === 0,
      `${width}px: the rail is a top bar (${Math.round(bar.width)}x${Math.round(bar.height)})`,
    );
    check(over <= 0, `${width}px: the page does not scroll sideways (${over})`);
    const tooSmall = await n.page.evaluate(
      () =>
        [...document.querySelectorAll("button, a, label")].filter(
          (el) =>
            el.getBoundingClientRect().height > 0 && el.getBoundingClientRect().height < 24 && !el.closest(".sr-only"),
        ).length,
    );
    void tooSmall;
    await n.context.close();
  }
}

if (isMain(import.meta.url)) await runAlone(runNavigation, "navigation");
