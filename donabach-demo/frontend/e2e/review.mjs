// Review (/review): the fields grouped by document, the flagged field highlighted and gated behind Confirm, clicking a field highlights
// its source on the PDF (absolute page, bbox in PDF points), any field editable (edits are sent as overrides), values equal the API's.
import { isMain, runAlone, newPage, apiPost, toReview, reviewRows, sessionState, openAll, money2 } from "./portal.mjs";

const parse = (text) => Number(text.replace(/[$,%\s,]/g, ""));

export async function runReview({ browser, base, check }) {
  const api = await apiPost(base, "/portal/documents/sample", undefined);
  const fields = api.documents.flatMap((d) => d.fields);
  const flagged = fields.filter((f) => f.confidence !== "high");

  const { context, page, issues } = await newPage(browser);
  const households = [];
  page.on("request", (r) => r.url().includes("/api/portal/household") && households.push(JSON.parse(r.postData())));
  await toReview(page, base);

  // --- the copy and the curated rows of the mockup
  check((await page.locator("main h1").innerText()) === "Check what we found", "the heading is 'Check what we found'");
  check(
    await page.getByText("Select any number to see where it came from.", { exact: true }).isVisible(),
    "the lede is the mockup's",
  );
  const headings = await page.locator("main h2").allInnerTexts();
  check(
    JSON.stringify(headings) === JSON.stringify(["Tax return", "Accounts"]),
    `two groups, like the mockup: ${headings.join(", ")}`,
  );
  const CURATED = [
    ["w2_wages_taxpayer", "Wages, after 401(k)"],
    ["filing_status", "Filing status"],
    ["qualified_dividends_3a", "Qualified dividends"],
    ["brokerage_total_value", "Brokerage"],
    ["brokerage_cost_basis", "Brokerage cost basis"],
    ["k401_total_balance", "401(k) and IRA"],
    ["k401_contrib_taxpayer", "401(k) contributions this year"],
    ["roth_total_balance", "Roth IRA"],
    ["brokerage_cash", "Cash"],
  ];
  const visibleRows = await page.$$eval('main section[aria-labelledby^="group-"] [data-field-key]', (items) =>
    items.map((li) => [li.getAttribute("data-field-key"), li.querySelector("label")?.innerText.trim()]),
  );
  check(
    JSON.stringify(visibleRows) === JSON.stringify(CURATED),
    `the friendly rows, in order, with the mockup's labels (${visibleRows.length})`,
  );
  const details = page.locator("main details");
  check(
    (await details.locator("summary").innerText()) === "Show all fields" && !(await details.evaluate((e) => e.open)),
    "a quiet 'Show all fields' disclosure holds the rest, closed",
  );
  check(
    (await page.locator('[data-field-key="wages_1a"]').isVisible()) === false,
    "a field that is not a friendly row is hidden until it is opened",
  );
  await openAll(page);
  check(
    await page.locator('[data-field-key="wages_1a"]').isVisible(),
    "'Show all fields' shows every other parsed field",
  );
  const rest = await page.$$eval("main details [data-field-key]", (items) => items.length);
  check(rest === fields.length - CURATED.length, `the disclosure lists the other ${rest} fields`);
  await details.locator("summary").click();
  const rows = await reviewRows(page);
  check(rows.length === fields.length, `${rows.length} rows, the API has ${fields.length} fields`);
  let wrong = [];
  for (const f of fields) {
    const row = rows.find((r) => r[0] === f.key);
    if (!row) continue;
    const shown = row[2];
    const ok = f.kind === "text" ? shown === String(f.value) : Math.abs(parse(shown) - Number(f.value)) < 0.005;
    if (!ok) wrong.push(`${f.key}: ${shown} vs ${f.value}`);
  }
  check(wrong.length === 0, `every value equals the API's (${wrong.slice(0, 3).join("; ")})`);
  await openAll(page);
  check(
    (await page.locator('[data-field-key="taxpayer_name"]').innerText()).includes("John Smith"),
    "text fields are shown as read",
  );
  const inputs = await page.locator("[data-field-key] input").count();
  check(inputs === fields.filter((f) => f.kind !== "text").length, `every number is an editable box (${inputs})`);

  // --- the flagged field
  check(
    flagged.length === 1 && flagged[0].confidence === "medium",
    `the API flags one medium field (${flagged.map((f) => f.key).join(", ")})`,
  );
  const flagRow = page.locator(`[data-field-key="${flagged[0].key}"]`);
  check((await flagRow.getAttribute("data-waiting")) === "true", "the flagged field is highlighted as waiting");
  check(flagged[0].key === "brokerage_total_value", "the flagged field is the Brokerage row");
  check((await flagRow.innerText()).includes(flagged[0].flag), "its flag text says why");
  check(
    (await flagRow.locator("p").evaluate((el) => getComputedStyle(el).color)) === "rgb(138, 90, 18)",
    "the note is in the warn colour",
  );
  check(
    (await flagRow.evaluate((el) => getComputedStyle(el).backgroundColor)) !== "rgba(0, 0, 0, 0)",
    "it has a tinted background",
  );
  const next = page.getByRole("button", { name: "Confirm and continue" });
  check(await next.isDisabled(), "'Confirm and continue' is disabled until the flagged field is dealt with");
  check(
    (await page.getByRole("button", { name: "Confirm", exact: true }).count()) === 1,
    "one Confirm button, on the flagged field",
  );

  // --- clicking a field highlights its source
  const highlight = page.locator('[data-testid="highlight"]');
  const card = await page.locator('section[aria-label="Document pages"]').evaluate((el) => {
    const s = getComputedStyle(el);
    return { radius: s.borderTopLeftRadius, position: getComputedStyle(el.parentElement).position };
  });
  check(
    card.radius === "14px" && card.position === "sticky",
    `the document sits in a 14px card that stays in view (${JSON.stringify(card)})`,
  );
  check(
    (await page.locator('section[aria-label="Document pages"] h3').innerText()) === "Brokerage statement",
    "the card is titled with the document being shown",
  );
  check((await highlight.count()) === 1, "the flagged field's source is highlighted on the PDF when Review opens");
  const wages = fields.find((f) => f.key === "w2_wages_taxpayer");
  await page.locator(`[data-field-key="${wages.key}"] label`).click();
  await page.waitForTimeout(700);
  check((await highlight.count()) === 1, "clicking a field puts one box on the PDF");
  const pageBox = await page.locator(`[data-page="${wages.page}"][data-points]`).boundingBox();
  const boxBox = await highlight.boundingBox();
  const points = Number(await page.locator(`[data-page="${wages.page}"][data-points]`).getAttribute("data-points"));
  const scale = pageBox.width / points;
  const dx = Math.abs(boxBox.x - (pageBox.x + wages.bbox.x0 * scale - 3));
  const dy = Math.abs(boxBox.y - (pageBox.y + wages.bbox.top * scale - 3));
  check(
    dx < 3 && dy < 3,
    `the box sits on the number's bbox on page ${wages.page} (off by ${dx.toFixed(1)}, ${dy.toFixed(1)} px)`,
  );
  await page.locator(`[data-field-key="${flagged[0].key}"] label`).click();
  await page.waitForTimeout(700);
  check(
    (await page.locator(`[data-page="${flagged[0].page}"][data-points] [data-testid="highlight"]`).count()) === 1,
    `the flagged field's box is on page ${flagged[0].page} of the same PDF`,
  );
  check((await flagRow.getAttribute("aria-current")) === "true", "the selected row carries aria-current");
  const tabCurrent = await page.locator('section[aria-label="Document pages"] button[aria-current="true"]').innerText();
  check(tabCurrent === "Brokerage statement", `the document tab follows the selection (${tabCurrent})`);

  // --- confirm: the value stays as printed, no override
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  check(await next.isEnabled(), "after Confirm the button is enabled");
  check((await flagRow.getAttribute("data-waiting")) === "false", "the flagged field is no longer waiting");
  check(
    (await flagRow.locator("input").inputValue()) === money2(flagged[0].value).slice(1),
    "Confirm keeps the value as printed",
  );
  let saved = await sessionState(page);
  check(
    Object.keys(saved.overrides).length === 0 && saved.confirmed.includes(flagged[0].key),
    "a confirmation is not an override",
  );

  // --- editing: an edit is an override (a number), Reset takes it back
  const box = page.locator(`[data-field-key="w2_wages_taxpayer"] input`);
  await box.fill("163,415");
  await box.press("Enter");
  saved = await sessionState(page);
  check(saved.overrides.w2_wages_taxpayer === 163415, "editing wages stores an override of 163415");
  await openAll(page);
  const other = page.locator('[data-field-key="wages_1a"] input');
  await other.fill("150000");
  await other.press("Enter");
  saved = await sessionState(page);
  check(saved.overrides.wages_1a === 150000, "a field inside 'Show all fields' can be edited too");
  await page
    .locator('[data-field-key="wages_1a"]')
    .getByRole("button", { name: /^Reset to/ })
    .click();
  check(
    await page.locator('[data-field-key="w2_wages_taxpayer"]').getByText("Edited").isVisible(),
    "an edited field says so",
  );
  await page
    .locator('[data-field-key="w2_wages_taxpayer"]')
    .getByRole("button", { name: /^Reset to/ })
    .click();
  saved = await sessionState(page);
  check(!("w2_wages_taxpayer" in saved.overrides), "Reset goes back to the document's value");
  await box.fill("abc");
  await box.press("Enter");
  saved = await sessionState(page);
  check(!("w2_wages_taxpayer" in saved.overrides), "text that is not a number is not saved");

  // --- edit the flagged field instead of confirming: a fresh run
  {
    const second = await newPage(browser);
    const p2 = second.page;
    await toReview(p2, base);
    const n2 = p2.getByRole("button", { name: "Confirm and continue" });
    check(await n2.isDisabled(), "a fresh visit starts with the button disabled");
    const flaggedBox = p2.locator(`[data-field-key="${flagged[0].key}"] input`);
    await flaggedBox.fill("645,775.59");
    await flaggedBox.press("Enter");
    check(await n2.isEnabled(), "editing the flagged field also lets the customer continue");
    const s2 = await sessionState(p2);
    check(s2.overrides[flagged[0].key] === 645775.59, "the edit is stored as a number (645775.59)");
    await n2.click();
    await p2.waitForURL("**/goals");
    await second.context.close();
  }

  check(households.length === 0, "Review itself sends nothing to the household endpoint");
  check(issues.length === 0, `no console errors on Review (${issues.join(" | ")})`);
  await context.close();
}

if (isMain(import.meta.url)) await runAlone(runReview, "review");
