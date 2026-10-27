// Round three: the live demo flow. The wealth screen's advisor-only start and the button that shows Donabach, the order of the
// flow and every way on and back, and the what-if screen (/showcase/whatif): the radio group, both events asked for once and kept,
// the headline pair, what Donabach changes, the year table (the years the API flags, and no others), the wealth figure and what
// happens when an event cannot be loaded.
//
// Every expectation is read from the API's own answers (GET /showcase, GET /showcase/scenarios, GET /showcase/scenarios/{key}); no
// number or sentence is typed here. Called from walkthrough.mjs, or on its own:
//
//   BASE_URL=http://localhost:3000 CHROMIUM_PATH=... node e2e/whatif.mjs

import { mkdirSync } from "node:fs";
import { isMain, layoutOf, money, moreOrLess, openPage, pct1, ratePct, runAlone, signedMoney, squash } from "./lib.mjs";
import { lowContrast } from "./showcase.mjs";

const DECISIONS = ["wages", "roth_conversion", "gains_harvested_tax_free", "losses_harvested", "stock_share"];
const sameSet = (a, b) => a.length === b.length && [...a].sort().join() === [...b].sort().join();

export async function runWhatIf({ browser, base, out, check, notes }) {
  mkdirSync(out, { recursive: true });
  const api = base + "/api";
  const getJson = async (path) => (await fetch(api + path)).json();
  const showcase = await getJson("/showcase");
  const { wealth } = showcase;
  const horizon = wealth.horizon_age;
  const infos = await getJson("/showcase/scenarios");
  const scenarios = {};
  for (const info of infos) scenarios[info.key] = await getJson(`/showcase/scenarios/${info.key}`);
  check(
    infos.length >= 2 && infos.every((i) => i.label && i.event && scenarios[i.key].years.length > 0),
    `whatif api: GET /showcase/scenarios lists ${infos.map((i) => `"${i.label}"`).join(" and ")}, and each has its year-by-year plan`,
  );

  /** A page that counts the requests for the household and the events. */
  const newPage = async (width = 1280, height = 900) => {
    const { context, page, issues } = await openPage(browser, { width, height });
    const requests = { showcase: 0, list: 0, scenarios: {} };
    page.on("request", (r) => {
      const { pathname } = new URL(r.url());
      if (r.method() !== "GET") return;
      if (pathname === "/api/showcase") requests.showcase++;
      if (pathname === "/api/showcase/scenarios") requests.list++;
      const one = pathname.match(/^\/api\/showcase\/scenarios\/([^/]+)$/);
      if (one) requests.scenarios[one[1]] = (requests.scenarios[one[1]] ?? 0) + 1;
    });
    return { context, page, issues, requests };
  };
  const lines = (page) => page.locator("path.recharts-line-curve");
  const settle = (page, n) =>
    page
      .waitForFunction(
        (want) => {
          const l = [...document.querySelectorAll("path.recharts-line-curve")];
          return l.length === want && l.every((x) => !(x.getAttribute("stroke-dasharray") ?? "").includes("px"));
        },
        n,
        { timeout: 10000 },
      )
      .catch(() => notes.push("whatif: the chart lines were still animating at the check"));
  const headingOf = (page, label) => page.getByRole("heading", { level: 2, name: label });

  // === The wealth screen starts with the advisor alone ====================================================================
  {
    const { context, page, issues } = await newPage();
    await page.goto(base + "/showcase/wealth", { waitUntil: "networkidle" });
    await page.locator(".recharts-wrapper").first().waitFor({ timeout: 90000 });
    await settle(page, 2);
    const a = wealth.advantage;
    // The page's own words: the button and the way on name Donabach (they lead to it), so they are left out.
    const html = await page.locator("main").evaluate((el) => {
      const copy = el.cloneNode(true);
      for (const x of copy.querySelectorAll("button, a")) x.remove();
      return copy.textContent ?? "";
    });
    check(
      !/Donabach/i.test(html) &&
        (await page
          .locator('main [aria-label^="Donabach"], main #heirs-title, main [aria-label^="The 10th percentile"]')
          .count()) === 0 &&
        (await headingOf(page, "Median advantage").count()) === 0 &&
        (await headingOf(page, wealth.risk_adjusted_label).count()) === 0,
      "advisor only: the word Donabach, its headline, the heirs block, the risk-adjusted advantage and the bad-market comparison are not in the page at all (not hidden: absent from the text of main)",
    );
    const donabachValues = [a.plan_median_at_horizon, a.plan_p10_at_horizon, wealth.heirs.plan_median_at_horizon]
      .map(money)
      .filter(
        (v) =>
          ![a.advisor_median_at_horizon, a.advisor_p10_at_horizon, wealth.heirs.advisor_median_at_horizon]
            .map(money)
            .includes(v),
      );
    check(
      donabachValues.every((v) => !html.includes(v)) && (await lines(page).count()) === 2,
      `advisor only: none of Donabach's figures (${donabachValues.join(", ")}) is anywhere in the page, and the chart draws two lines`,
    );
    const dashes = await lines(page).evaluateAll((ls) => ls.map((l) => l.getAttribute("stroke-dasharray") ?? ""));
    const legend = (await page.locator("figure li, figure [role=list] > *").allInnerTexts()).map(squash);
    check(
      dashes.filter((d) => d !== "").length === 1 &&
        (await page.locator("svg text", { hasText: money(a.advisor_median_at_horizon) }).count()) >= 1 &&
        (await page.locator("svg text", { hasText: money(a.advisor_p10_at_horizon) }).count()) >= 1 &&
        legend.some((t) => t === `${wealth.advisor_label}, typical (median)`) &&
        legend.some((t) => t === `${wealth.advisor_label}, bad market (10th percentile)`) &&
        !legend.some((t) => /Donabach/.test(t)),
      "advisor only: the chart is the advisor's typical (solid) and bad-market (dashed) lines, labelled at their ends with the API's two values at 80, and the legend names just those two",
    );
    const adv = squash(await page.locator('section[aria-label^="What a"]').innerText());
    check(
      adv.includes(money(a.advisor_median_at_horizon)) &&
        adv.includes(money(a.advisor_p10_at_horizon)) &&
        adv.includes(pct1(a.advisor_shortfall)) &&
        adv.includes(wealth.liquidated_label) &&
        /age-based portfolio/.test(adv) &&
        /fees/.test(adv) &&
        /managed separately/.test(adv) &&
        new RegExp(`typical household`).test(adv) &&
        /In a bad market/.test(adv),
      `advisor only: the headline shows the advisor's typical household (${money(a.advisor_median_at_horizon)}), a bad market (${money(a.advisor_p10_at_horizon)}), the chance of running out of money (${pct1(a.advisor_shortfall)}) and one line on what the advisor does`,
    );
    const button = page.getByRole("button", { name: "Show what Donabach does" });
    check(
      (await button.count()) === 1 &&
        (await button.isVisible()) &&
        (await page.getByRole("link", { name: /See what Donabach does/ }).getAttribute("href")) ===
          "/showcase/strategies" &&
        (await page.getByRole("link", { name: /Back to the household/ }).getAttribute("href")) === "/showcase",
      "advisor only: a primary 'Show what Donabach does' button is on the screen; the way on is 'See what Donabach does' to the strategies and the way back goes to the household",
    );
    const weak = await lowContrast(page);
    check(weak.length === 0, `advisor only: all text has enough contrast${weak.length ? ` (${weak.join("; ")})` : ""}`);
    await page.screenshot({ path: `${out}/r3-wealth-advisor-1280.png`, fullPage: true });

    // --- the button reveals Donabach ---
    await button.focus();
    await page.keyboard.press("Enter");
    await headingOf(page, "Median advantage").waitFor({ timeout: 10000 });
    await settle(page, 4);
    const shown = squash(await page.locator('section[aria-label^="Donabach"]').innerText());
    check(
      shown.includes(`${ratePct(a.median_rate)} a year`) &&
        shown.includes(moreOrLess(a.median_dollars, horizon)) &&
        shown.includes(`${ratePct(a.risk_adjusted_rate)} a year`) &&
        shown.includes(signedMoney(a.risk_adjusted_dollars)) &&
        (await lines(page).count()) === 4 &&
        (await page.locator('section[aria-labelledby="heirs-title"]').count()) === 1 &&
        (await page.locator('section[aria-label="The 10th percentile at 80"]').count()) === 1 &&
        (await page.getByRole("button", { name: "Show what Donabach does" }).count()) === 0,
      `revealed: the button (pressed with the keyboard) shows Donabach: the headline (${ratePct(a.median_rate)} a year, ${moreOrLess(a.median_dollars, horizon)}) equals the API's, four lines, the heirs block and the bad-market comparison; the button is gone`,
    );
    const focused = await page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? "");
    const announced = squash(await page.locator('main [role="status"]').first().innerText());
    check(
      focused.startsWith("Donabach") &&
        announced.startsWith("Donabach is now shown") &&
        announced.includes(`${ratePct(a.median_rate)} a year`),
      `revealed: focus moves to the headline ("${focused}") and a polite live region announces it ("${announced}")`,
    );
    await page.screenshot({ path: `${out}/r3-wealth-both-1280.png`, fullPage: true });

    // --- it stays: strategies and back ---
    await page.getByRole("link", { name: /Back to the strategies/ }).click();
    await page.waitForURL("**/showcase/strategies");
    await page.locator("li[data-key]").first().waitFor();
    await page.getByRole("link", { name: /See wealth over time/ }).click();
    await page.waitForURL("**/showcase/wealth");
    await page.locator(".recharts-wrapper").first().waitFor();
    await settle(page, 4);
    check(
      (await page.getByRole("button", { name: "Show what Donabach does" }).count()) === 0 &&
        (await headingOf(page, "Median advantage").count()) === 1 &&
        (await lines(page).count()) === 4,
      "revealed: after a visit to the strategies and back, the wealth screen still shows both lines (it stays for the session)",
    );
    await page.reload({ waitUntil: "networkidle" });
    await page.locator(".recharts-wrapper").first().waitFor({ timeout: 60000 });
    check(
      (await page.getByRole("button", { name: "Show what Donabach does" }).count()) === 1 &&
        (await headingOf(page, "Median advantage").count()) === 0,
      "revealed: reloading the page starts again with the advisor alone (it is state, not the address)",
    );
    check(issues.length === 0, `advisor only and revealed: no console errors${issues.length ? ` (${issues[0]})` : ""}`);
    await context.close();
  }

  // --- moving on from the advisor-only view reveals Donabach too ---
  {
    const { context, page, requests } = await newPage();
    await page.goto(base + "/showcase", { waitUntil: "networkidle" });
    await page.getByRole("link", { name: /See what a good advisor gets them/ }).click();
    await page.waitForURL("**/showcase/wealth");
    await page.locator(".recharts-wrapper").first().waitFor();
    await settle(page, 2);
    check(
      (await page.getByRole("button", { name: "Show what Donabach does" }).count()) === 1,
      "flow: coming from the household the wealth screen is advisor only",
    );
    await page.getByRole("link", { name: /See what Donabach does/ }).click();
    await page.waitForURL("**/showcase/strategies");
    await page.locator("li[data-key]").first().waitFor();
    check(
      (await page.getByRole("link", { name: /Back to the household/ }).getAttribute("href")) === "/showcase" &&
        (await page.getByRole("link", { name: /See wealth over time/ }).getAttribute("href")) === "/showcase/wealth",
      "flow: the strategies screen goes back to the household and on to wealth over time",
    );
    await page.getByRole("link", { name: /See wealth over time/ }).click();
    await page.waitForURL("**/showcase/wealth");
    await page.locator(".recharts-wrapper").first().waitFor();
    await settle(page, 4);
    check(
      (await page.getByRole("button", { name: "Show what Donabach does" }).count()) === 0 &&
        (await lines(page).count()) === 4 &&
        (await page.getByRole("link", { name: /Back to the strategies/ }).getAttribute("href")) ===
          "/showcase/strategies" &&
        (await page.getByRole("link", { name: /Change the household/ }).getAttribute("href")) === "/showcase/whatif",
      "flow: moving on to the strategies from the advisor-only view reveals Donabach: wealth then has both lines, goes back to the strategies and on to 'Change the household' (/showcase/whatif)",
    );
    await page.getByRole("link", { name: /Change the household/ }).click();
    await page.waitForURL("**/showcase/whatif");
    await page.locator("fieldset").waitFor();
    check(
      (await page.getByRole("link", { name: /Back to wealth over time/ }).getAttribute("href")) ===
        "/showcase/wealth" && requests.showcase === 1,
      "flow: the what-if screen goes back to wealth over time, and the household was asked for once in the whole flow",
    );
    const nav = (await page.getByRole("navigation", { name: "Showcase progress" }).locator("li").allInnerTexts()).map(
      squash,
    );
    check(nav.length === 4 && /What if/.test(nav[3]), `flow: the header's four steps are ${nav.join(", ")}`);
    await context.close();
    const home = await newPage();
    await home.page.goto(base + "/", { waitUntil: "networkidle" });
    const entry = squash(await home.page.getByLabel("The showcase").innerText());
    check(
      /four screens/.test(entry) && !/three screens/.test(entry) && /adapts/.test(entry) && !/predict/i.test(entry),
      `home: the showcase entry says "four screens" and that the plan adapts ("${entry.slice(0, 80)}...")`,
    );
    await home.context.close();
  }

  // === The what-if screen =================================================================================================
  const shown = infos.map((i) => i.key);
  {
    const { context, page, issues, requests } = await newPage();
    await page.goto(base + "/showcase/whatif", { waitUntil: "networkidle" });
    await page.locator("fieldset").waitFor({ timeout: 90000 });
    await page.waitForTimeout(1200);
    const head = await page.getByRole("heading", { level: 1 }).innerText();
    const group = page.getByRole("group", { name: /What happens to the household/ });
    const labels = (await group.locator("label").allInnerTexts()).map(squash);
    const expectedLabels = ["No change", ...infos.map((i) => i.label)];
    check(
      squash(head) === "What if things change?" &&
        /Donabach searches its strategies across simulated futures again for the changed household, so the plan adapts\. Pick an event\./.test(
          await page.locator("main").innerText(),
        ) &&
        JSON.stringify(labels) === JSON.stringify(expectedLabels) &&
        (await group.getByRole("radio").count()) === expectedLabels.length &&
        (await group.getByRole("radio", { name: "No change" }).isChecked()),
      `whatif: the header and lede, and a labelled radio group "${expectedLabels.join(" | ")}" (the API's labels) with No change chosen`,
    );
    check(
      requests.list === 1 && shown.every((k) => requests.scenarios[k] === 1) && requests.showcase === 1,
      `whatif: both events were asked for as soon as the flow opened, once each (list ${requests.list}, ${shown.map((k) => `${k} ${requests.scenarios[k]}`).join(", ")})`,
    );
    // No change is the unchanged household, with no extra request.
    const none = squash(await page.locator("main").innerText());
    check(
      none.includes(`${ratePct(wealth.advantage.median_rate)} a year`) &&
        !/Before the event/.test(none) &&
        (await page.locator('[data-testid="event"]').count()) === 0 &&
        (await page.getByRole("heading", { name: "Year by year" }).count()) === 0,
      "whatif: No change shows the unchanged household's headline and wealth (data.wealth), with no event, no year table and no 'before' line",
    );
    await page.screenshot({ path: `${out}/r3-whatif-none-1280.png`, fullPage: true });

    // Keyboard: arrows move the choice.
    const radios = group.getByRole("radio");
    await radios.nth(0).focus();
    await page.keyboard.press("ArrowDown");
    const second = await radios.nth(1).isChecked();
    await page.keyboard.press("ArrowDown");
    const third = await radios.nth(2).isChecked();
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("ArrowUp");
    const first = await radios.nth(0).isChecked();
    const ring = await (async () => {
      await radios.nth(0).focus();
      return radios.nth(0).evaluate((el) => getComputedStyle(el.nextElementSibling).outlineStyle);
    })();
    check(
      second && third && first && ring === "solid",
      "whatif: the radio group answers the keyboard (Down, Down, Up, Up move the choice through the three) and the focused one shows a ring",
    );

    // Each event: everything on screen is the API's.
    for (const info of infos) {
      const sc = scenarios[info.key];
      const sw = sc.wealth;
      const adv = sw.advantage;
      const before = wealth.advantage;
      const name = `whatif "${info.label}"`;
      await group.getByRole("radio", { name: info.label }).check({ force: true });
      await page.locator('[data-testid="event"]').waitFor({ timeout: 5000 });
      await settle(page, 4);
      await page.mouse.move(2, 2);
      check(
        squash(await page.locator('[data-testid="event"]').innerText()) === squash(sc.event),
        `${name}: the quiet note above the results is the API's event sentence ("${sc.event.slice(0, 60)}...")`,
      );
      const headline = squash(await page.locator('section[aria-label^="Donabach\'s advantage"]').innerText());
      check(
        headline.startsWith(sw.liquidated_label) &&
          headline.includes(`${ratePct(adv.median_rate)} a year`) &&
          headline.includes(moreOrLess(adv.median_dollars, horizon)) &&
          headline.includes(`Donabach ${money(adv.plan_median_at_horizon)}`) &&
          headline.includes(`${sw.advisor_label} ${money(adv.advisor_median_at_horizon)}`) &&
          headline.includes(`Before the event: ${ratePct(before.median_rate)} a year`),
        `${name}: the headline pair is the event's median advantage (${ratePct(adv.median_rate)} a year, ${moreOrLess(adv.median_dollars, horizon)}), both medians (${money(adv.plan_median_at_horizon)} and ${money(adv.advisor_median_at_horizon)}), labelled "${sw.liquidated_label}", with the unchanged household's ${ratePct(before.median_rate)} beside it`,
      );
      check(
        headline.includes("In a bad market") &&
          headline.includes(money(adv.plan_p10_at_horizon)) &&
          headline.includes(`${sw.advisor_label} ${money(adv.advisor_p10_at_horizon)}`) &&
          headline.includes(`Donabach ${pct1(adv.plan_shortfall)}`) &&
          headline.includes(`${sw.advisor_label} ${pct1(adv.advisor_shortfall)}`) &&
          !headline.includes(sw.risk_adjusted_label) &&
          headline.includes(sw.heirs.label) &&
          headline.includes(money(sw.heirs.plan_median_at_horizon)) &&
          headline.includes(`${ratePct(sw.heirs.median_rate)} a year`),
        `${name}: the bad-market wealth (${money(adv.plan_p10_at_horizon)} and ${money(adv.advisor_p10_at_horizon)}) and the chances of running out of money are shown; the risk-adjusted advantage is NOT on this screen (it appears once, on the wealth screen); the heirs valuation is one small line ("${sw.heirs.label}")`,
      );
      const summary = (await page.locator('[data-testid="summary"] li').allInnerTexts()).map(squash);
      const replanSummary = (await page.locator('[data-testid="replan-summary"] li').allInnerTexts()).map(squash);
      check(
        JSON.stringify(summary) === JSON.stringify(sc.summary.map(squash)) &&
          JSON.stringify(replanSummary) === JSON.stringify(sc.replan_summary.map(squash)) &&
          ((await page.getByRole("heading", { name: "Planning again also changes" }).count()) === 1) ===
            sc.replan_summary.length > 0,
        `${name}: "What Donabach changes" lists the API's ${sc.summary.length} summary sentences and, under "Planning again also changes", its ${sc.replan_summary.length} replan_summary sentences, word for word`,
      );
      const replan = squash(await page.locator('[data-testid="replan"]').innerText());
      const word = sc.replan.median_dollars < 0 ? "costs" : "is worth";
      check(
        replan.includes(sc.plan_label) &&
          (!sc.plan_changed || replan.includes(`instead of ${sc.original_plan_label}`)) &&
          replan.includes(word) &&
          replan.includes(`${ratePct(sc.replan.median_rate)} a year`) &&
          replan.includes(signedMoney(sc.replan.median_dollars)),
        `${name}: the replan line says the strategy (${sc.plan_changed ? "changed" : "unchanged"}) and what planning again ${word} (${ratePct(sc.replan.median_rate)} a year, ${signedMoney(sc.replan.median_dollars)} at ${horizon}), with its sign`,
      );

      // The year table.
      const flagged = sc.years.filter((y) => y.responded.length || y.replanned.length);
      const table = page.getByRole("table", { name: /Year by year after the event/ });
      const ages = async () =>
        await table.locator("tbody tr").evaluateAll((trs) => trs.map((t) => +t.getAttribute("data-row-key")));
      const hot = async () =>
        table
          .locator('tbody tr[data-tone="highlight"]')
          .evaluateAll((trs) => trs.map((t) => +t.getAttribute("data-row-key")));
      const heads = (await table.locator("thead th").allInnerTexts()).map(squash);
      const toggle = page.getByRole("checkbox", { name: "Show only the years that changed" });
      check(
        JSON.stringify(heads) ===
          JSON.stringify([
            "Age",
            "Wages",
            "Roth conversion",
            "Gains realized tax-free",
            "Losses harvested",
            "Stock share",
          ]) && (await toggle.isChecked()),
        `${name}: the table's columns are Age, Wages, Roth conversion, Gains realized tax-free, Losses harvested, Stock share, and "Show only the years that changed" is on at first`,
      );
      check(
        sameSet(
          await ages(),
          flagged.map((y) => y.age),
        ) &&
          sameSet(
            await hot(),
            flagged.filter((y) => y.responded.length).map((y) => y.age),
          ),
        `${name}: with the filter on, the rows are exactly the ${flagged.length} years the API flags as responded or replanned (of ${sc.years.length}), and the ${flagged.filter((y) => y.responded.length).length} the event itself changed are highlighted`,
      );
      const tags = await table.locator('[data-testid="changed-tag"]').count();
      const emphasised = await table.locator("[data-differs]").count();
      const befores = (await table.locator("tbody td").allInnerTexts()).filter((t) => /before:/.test(t)).length;
      const flaggedCells = flagged.reduce(
        (n, y) => n + new Set([...y.responded, ...y.replanned].filter((k) => DECISIONS.includes(k))).size,
        0,
      );
      const tagText = squash(await table.locator('[data-testid="changed-tag"]').first().innerText());
      check(
        tags === flagged.length &&
          emphasised === flaggedCells &&
          befores === flaggedCells &&
          /Changed/.test(tagText) &&
          /in this year:/.test(tagText) &&
          (await table.locator('[data-testid="changed-tag"][data-kind="event"]').count()) ===
            flagged.filter((y) => y.responded.length).length &&
          (await table.locator('[data-testid="changed-tag"][data-kind="replan"]').count()) ===
            flagged.filter((y) => !y.responded.length).length,
        `${name}: every highlighted year has a visible "Changed" tag with an icon and text for screen readers (${tags}), and the ${flaggedCells} cells that differ are emphasised and say "before: ..." (${emphasised}, ${befores})`,
      );
      // A cell's numbers are the API's.
      const first = flagged[0];
      const firstRow = table.locator(`tbody tr[data-row-key="${first.age}"]`);
      const rowText = squash(await firstRow.innerText());
      check(
        rowText.includes(money(first.roth_conversion)) &&
          rowText.includes(money(first.wages)) &&
          (!first.responded.includes("wages") || rowText.includes(`before: ${money(first.base_wages)}`)) &&
          ((!first.replanned.includes("roth_conversion") && !first.responded.includes("roth_conversion")) ||
            rowText.includes(`before: ${money(first.base_roth_conversion)}`)),
        `${name}: the first changed year (${first.age}) shows the API's values, and "before" is the plan with no event`,
      );
      // Scrolled into view: the first highlighted row is inside the table's box.
      const inView = await page.evaluate(() => {
        const scroller = document.querySelector('[role="region"][aria-label^="Year by year"]');
        const row = scroller?.querySelector('tr[data-tone="highlight"]');
        if (!scroller || !row) return false;
        const s = scroller.getBoundingClientRect();
        const r = row.getBoundingClientRect();
        return r.top >= s.top && r.bottom <= s.bottom + 1;
      });
      check(inView, `${name}: the first highlighted row is in view inside the table when it first renders`);
      await toggle.uncheck();
      await page.waitForTimeout(200);
      check(
        sameSet(
          await ages(),
          sc.years.map((y) => y.age),
        ) &&
          sameSet(
            await hot(),
            flagged.filter((y) => y.responded.length).map((y) => y.age),
          ),
        `${name}: with the filter off, every one of the ${sc.years.length} years is a row (${sc.years[0].age} to ${sc.years.at(-1).age}), and exactly the years the event changed are highlighted`,
      );
      await toggle.check();

      // Wealth figure.
      const title = squash(await page.locator("#whatif-wealth-title").innerText());
      const w = sw.wealth;
      const last = w.ages.length - 1;
      const svg = await page
        .locator(".recharts-wrapper")
        .first()
        .evaluate((el) => el.textContent ?? "");
      const legend = (await page.locator("figure li").allInnerTexts()).map(squash);
      check(
        title === `Donabach and a ${sw.advisor_label.toLowerCase()} after the event` &&
          (await lines(page).count()) === 4 &&
          [w.plan_median[last], w.plan_p10[last], w.advisor_median[last], w.advisor_p10[last]].every((v) =>
            svg.includes(money(v)),
          ) &&
          legend.length === 4,
        `${name}: the wealth figure is titled "${title}" and shows the scenario's own end values (${money(w.plan_median[last])}, ${money(w.plan_p10[last])}, ${money(w.advisor_median[last])}, ${money(w.advisor_p10[last])})`,
      );
      const weak = await lowContrast(page);
      check(weak.length === 0, `${name}: all text has enough contrast${weak.length ? ` (${weak.join("; ")})` : ""}`);
      await page.screenshot({ path: `${out}/r3-whatif-${info.key}-1280.png`, fullPage: true });
    }
    // Cached: choosing again asks for nothing.
    const asked = JSON.stringify([requests.list, requests.scenarios, requests.showcase]);
    for (const label of [infos[0].label, "No change", infos[1].label, infos[0].label])
      await group.getByRole("radio", { name: label }).check({ force: true });
    await page.waitForTimeout(600);
    check(
      JSON.stringify([requests.list, requests.scenarios, requests.showcase]) === asked &&
        shown.every((k) => requests.scenarios[k] === 1),
      `whatif: choosing events again makes no request: each event was fetched exactly once (${shown.map((k) => `${k} ${requests.scenarios[k]}`).join(", ")})`,
    );
    check(issues.length === 0, `whatif: no console errors${issues.length ? ` (${issues[0]})` : ""}`);
    await context.close();
  }

  // --- a phone: both events at 390 and 320 ---
  for (const width of [390, 320]) {
    const { context, page, issues } = await newPage(width, 800);
    await page.goto(base + "/showcase/whatif", { waitUntil: "networkidle" });
    await page.locator("fieldset").waitFor({ timeout: 90000 });
    for (const info of infos) {
      await page.getByRole("radio", { name: info.label }).check({ force: true });
      await page.locator('[data-testid="event"]').waitFor();
      await settle(page, 4);
      await page.mouse.move(2, 2);
      await page.waitForTimeout(300);
      const layout = await layoutOf(page);
      const weak = await lowContrast(page);
      check(
        layout.pageOverflow <= 0 && layout.spill.length === 0 && layout.small.length === 0 && weak.length === 0,
        `whatif "${info.label}" at ${width}px: no overflow, nothing spills, text at least 14px, enough contrast${layout.spill.concat(layout.small, weak).length ? ` (${layout.spill.concat(layout.small, weak).join("; ")})` : ""}`,
      );
      if (width === 390) await page.screenshot({ path: `${out}/r3-whatif-${info.key}-390.png`, fullPage: true });
    }
    check(issues.length === 0, `whatif at ${width}px: no console errors`);
    await context.close();
  }
  {
    const { context, page } = await newPage(390, 844);
    await page.goto(base + "/showcase", { waitUntil: "networkidle" });
    await page.locator("article").first().waitFor({ timeout: 60000 });
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${out}/r3-household-390.png`, fullPage: true });
    await page.screenshot({ path: `${out}/r3-household-1280-placeholder.png` }).catch(() => undefined);
    await page.goto(base + "/showcase/wealth", { waitUntil: "networkidle" });
    await page.locator(".recharts-wrapper").first().waitFor();
    await settle(page, 2);
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/r3-wealth-advisor-390.png`, fullPage: true });
    await page.getByRole("button", { name: "Show what Donabach does" }).click();
    await settle(page, 4);
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/r3-wealth-both-390.png`, fullPage: true });
    await context.close();
  }

  // === An event that cannot be loaded: the message, a retry, and the rest of the screen untouched ========================
  {
    const failing = infos[0];
    const { context, page, requests } = await newPage();
    let fail = true;
    let hits = 0;
    await page.route(`**/api/showcase/scenarios/${failing.key}`, (route) => {
      hits++;
      return fail
        ? route.fulfill({
            status: 500,
            contentType: "application/json",
            body: JSON.stringify({ detail: "the e2e made this error up" }),
          })
        : route.fallback();
    });
    await page.goto(base + "/showcase/whatif", { waitUntil: "networkidle" });
    await page.locator("fieldset").waitFor({ timeout: 60000 });
    await page.waitForTimeout(500);
    // The other event is fine, and the picker stays.
    const other = infos[1];
    await page.getByRole("radio", { name: other.label }).check({ force: true });
    await page.locator('[data-testid="event"]').waitFor();
    const okay = squash(await page.locator('[data-testid="event"]').innerText()) === squash(scenarios[other.key].event);
    await page.getByRole("radio", { name: failing.label }).check({ force: true });
    const alert = page.getByRole("alert");
    await alert.first().waitFor({ timeout: 10000 });
    const text = squash(await alert.first().innerText());
    check(
      okay &&
        text.includes("the e2e made this error up") &&
        text.includes(failing.label) &&
        (await page.getByRole("radio").count()) === 3 &&
        (await page.locator('[data-testid="event"]').count()) === 0 &&
        (await page.getByRole("heading", { level: 1 }).count()) === 1,
      `whatif error: an event the API refuses shows its message ("${text.slice(0, 70)}...") in the results area only, with the other event and the picker intact`,
    );
    const before = hits;
    fail = false;
    await page.getByRole("button", { name: "Try again" }).click();
    await page.locator('[data-testid="event"]').waitFor({ timeout: 10000 });
    check(
      squash(await page.locator('[data-testid="event"]').innerText()) === squash(scenarios[failing.key].event) &&
        hits === before + 1 &&
        (await page.getByRole("alert").filter({ hasText: "made this error up" }).count()) === 0 &&
        requests.scenarios[other.key] === 1,
      `whatif error: 'Try again' asks for that event only and shows it (${hits} vs ${before}, other ${requests.scenarios[other.key]})`,
    );
    await context.close();
  }

  // === An event that is slow: a loading state in the results area only =================================================
  {
    const slow = infos[1];
    const { context, page } = await newPage();
    let release;
    const held = new Promise((r) => (release = r));
    await page.route(`**/api/showcase/scenarios/${slow.key}`, async (route) => {
      await held;
      await route.fallback();
    });
    await page.goto(base + "/showcase/whatif", { waitUntil: "domcontentloaded" });
    await page.locator("fieldset").waitFor({ timeout: 60000 });
    await page.getByRole("radio", { name: slow.label }).check({ force: true });
    await page.getByText(/Working out/).waitFor({ timeout: 5000 });
    check(
      (await page.getByRole("radio").count()) === 3 && (await page.locator('[data-testid="event"]').count()) === 0,
      "whatif loading: an event that is not ready yet shows a loading state in the results area, and the picker stays",
    );
    release();
    await page.locator('[data-testid="event"]').waitFor({ timeout: 10000 });
    check(true, "whatif loading: the event appears when its answer arrives");
    await context.close();
  }
}

if (isMain(import.meta.url)) await runAlone(runWhatIf, "what-if");
