// Both valuations of wealth at the horizon, everywhere it is shown as a result (round two, part A).
//
//   BASE_URL=http://localhost:3000 CHROMIUM_PATH=... node e2e/valuations.mjs
//
// Every expectation is read from the API's own answers: the plan the browser itself was sent (POST /api/plan: its settings carry
// the two labels, the rate and the note; its stats and baselines carry both valuations) and GET /showcase (the whole plan's
// wealth with the heirs block). The labels are compared with the API's strings, never with words typed here.

import { lowContrast } from "./showcase.mjs";
import {
  FOOTER_TEXT,
  OLD_FOOTER_TEXT,
  isMain,
  layoutOf,
  money,
  moreOrLess,
  openPage,
  pct0,
  pct1,
  ratePct,
  runAlone,
  signedMoney,
  signedPercent,
  squash,
} from "./lib.mjs";

const against = { good_ria: "a good RIA", typical_advisor: "a typical advisor" };
const MEASURES = [
  ["Median advantage", "median"],
  ["Risk-adjusted advantage", "risk_adjusted"],
];

/** The first sentence of a note, the way a person reads it (up to a full stop that is followed by a new sentence). */
const firstSentence = (note) => note.split(/(?<=\.)\s+(?=[A-Z])/)[0];

export async function runValuations({ browser, base, out, check, notes }) {
  const api = base + "/api";
  const getJson = async (path) => (await fetch(api + path)).json();

  // --- The Comparison screen: both valuations side by side, on first view --------------------------------------------------
  {
    const { context, page, issues } = await openPage(browser, { width: 1440 });
    // The year-by-year job is not what is looked at here and costs the API a minute of work: ask for the plan without it.
    await page.route("**/api/plan", async (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}");
      await route.continue({ postData: JSON.stringify({ ...body, adaptive: false }) });
    });
    const planResponse = page.waitForResponse(
      (r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/plan",
    );
    await page.goto(base + "/compare", { waitUntil: "networkidle" });
    const plan = await (await planResponse).json();
    await page
      .getByText(/Where the advantage comes from/)
      .first()
      .waitFor({ timeout: 120000 });
    await page.waitForTimeout(1200);
    const s = plan.settings;
    const horizon = s.horizon_age;
    const { liquidated_label: liquidated, heirs_label: heirs } = s;
    const main = squash(await page.locator("main").innerText());

    check(
      typeof liquidated === "string" &&
        liquidated.length > 0 &&
        typeof heirs === "string" &&
        heirs.length > 0 &&
        liquidated !== heirs,
      `compare api: the plan's settings carry the two labels ("${liquidated}", "${heirs}"), the rate (${pct0(s.heirs_rate)}) and the heirs note (${s.heirs_note.length} characters)`,
    );
    check(
      main.includes(liquidated) && main.includes(heirs),
      "compare: both labels are on the screen, word for word as the API gives them, with no click needed",
    );

    // The advantage panel: both valuations in every cell, each with its figure, its 90% range and its dollars.
    let advantageOk = true;
    const seen = [];
    for (const baseline of plan.baselines) {
      for (const [label, value] of MEASURES) {
        const group = page.getByRole("group", { name: `${label} against ${against[baseline.key]}` });
        for (const [id, text, a] of [
          ["liquidated", liquidated, baseline.advantage],
          ["heirs", heirs, baseline.advantage_heirs],
        ]) {
          const block = group.locator(`[data-valuation="${id}"]`);
          const visible = await block.isVisible();
          const t = squash(await block.innerText());
          const dollars = a[`${value}_dollars`];
          const ok =
            visible &&
            t.includes(text) &&
            t.includes(`${signedPercent(a[value])} a year`) &&
            t.includes(
              `90% range: ${signedPercent(a[`${value}_low`])} to ${signedPercent(a[`${value}_high`])} when the futures are resampled`,
            ) &&
            t.includes(signedMoney(dollars));
          advantageOk &&= ok;
          seen.push(`${id} ${value} vs ${baseline.key} ${signedPercent(a[value])}`);
        }
      }
    }
    check(
      advantageOk,
      `compare: every advantage cell (2 measures x 2 advisors) shows ${liquidated} and ${heirs}, each with its own figure, range and dollars as the API has them (${seen.slice(0, 4).join("; ")}, ...)`,
    );
    const heirsMedian = plan.baselines[0].advantage_heirs.median;
    check(
      plan.baselines.every(
        (b) =>
          b.advantage_heirs.median !== b.advantage.median ||
          b.advantage_heirs.median_dollars !== b.advantage.median_dollars,
      ),
      `compare api: the heirs advantage is its own measurement, not the liquidated one repeated (${signedPercent(heirsMedian)} against ${signedPercent(plan.baselines[0].advantage.median)} a year against a good RIA)`,
    );

    // The baseline cards: the plan's and each advisor's median wealth (and bad case) under both valuations.
    const cards = [
      [
        "donabach",
        "the Donabach plan",
        { liquidated: plan.stats.typical_outcome, heirs: plan.stats.typical_outcome_heirs },
      ],
      ...plan.baselines.map((b) => [b.key, b.label, { liquidated: b.outcome, heirs: b.outcome_heirs }]),
    ];
    let cardsOk = true;
    const figures = [];
    for (const [key, name, outcomes] of cards) {
      const card = page.locator(`article[aria-labelledby="baseline-${key}"]`);
      for (const [id, text] of [
        ["liquidated", liquidated],
        ["heirs", heirs],
      ]) {
        const section = card.locator(`section[data-valuation="${id}"]`);
        const t = squash(await section.innerText());
        const o = outcomes[id];
        const ok =
          (await section.isVisible()) &&
          t.includes(text) &&
          t.includes(`Typical outcome at ${horizon} ${money(o.median)}`) &&
          t.includes(`Bad case (10th percentile) ${money(o.p10)}`);
        cardsOk &&= ok;
        figures.push(`${name}, ${id} ${money(o.median)}`);
      }
    }
    check(
      cardsOk,
      `compare: the plan's card and both advisors' cards each give the typical outcome and the bad case under ${liquidated} and ${heirs}, as the API has them (${figures.slice(0, 4).join("; ")}, ...)`,
    );
    check(
      main.includes(`Lifetime taxes ${money(plan.stats.lifetime_taxes)}`) &&
        main.includes(`Chance of a shortfall ${pct1(plan.stats.shortfall_chance)}`),
      "compare: the figures that have one value whichever way wealth is valued (lifetime taxes, chance of a shortfall) are unchanged",
    );

    // "How these are valued": folded away, and the API's note, word for word, with the rate, when opened.
    const how = page.getByRole("button", { name: "How these are valued" });
    const note = squash(s.heirs_note);
    const closedText = squash(await page.locator("main").innerText());
    check(
      (await how.getAttribute("aria-expanded")) === "false" && !closedText.includes(note),
      "compare: 'How these are valued' is a disclosure, folded away until opened",
    );
    await how.click();
    await page.waitForTimeout(500);
    const region = squash(await page.locator(`[id="${await how.getAttribute("aria-controls")}"]`).innerText());
    check(
      (await how.getAttribute("aria-expanded")) === "true" &&
        region.includes(note) &&
        region.includes(pct0(s.heirs_rate)) &&
        region.includes(liquidated) &&
        region.includes(heirs),
      `compare: opened, 'How these are valued' gives the API's heirs note word for word, with the rate (${pct0(s.heirs_rate)}), and says what ${liquidated} is`,
    );

    // The panels that are liquidated by construction say so.
    const total = squash(await page.locator("p", { hasText: "Total:" }).innerText());
    check(
      total.includes(`under “${liquidated}”`) && main.includes(`After-tax wealth, in 2026 dollars · ${liquidated}`),
      `compare: the chart and "Where the advantage comes from" are labelled ${liquidated}`,
    );

    // Layout at the desktop width, the footer, and contrast.
    const layout = await layoutOf(page);
    check(layout.pageOverflow <= 0, `compare: no horizontal overflow at 1440px (${layout.pageOverflow}px)`);
    check(
      layout.small.length === 0,
      `compare: no visible text under 14px${layout.small.length ? ` (${layout.small.join(", ")})` : ""}`,
    );
    check(
      layout.spill.length === 0,
      `compare: nothing spills out of its panel${layout.spill.length ? ` (${layout.spill.join(", ")})` : ""}`,
    );
    const weak = await lowContrast(page);
    check(weak.length === 0, `compare: all text has enough contrast${weak.length ? ` (${weak.join("; ")})` : ""}`);
    const footer = squash(await page.locator("footer").innerText());
    check(
      footer.includes(FOOTER_TEXT) && !footer.includes(OLD_FOOTER_TEXT),
      `compare: the footer's simplifications read "${FOOTER_TEXT}" and no longer say "${OLD_FOOTER_TEXT}"`,
    );
    check(issues.length === 0, `compare: no console errors${issues.length ? ` (${issues[0]})` : ""}`);
    await page.screenshot({ path: `${out}/valuations-compare-1440.png`, fullPage: true });

    // A what-if: every figure of both valuations says how far it moved.
    await page.route("**/api/plan/whatif", async (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}");
      await route.continue({ postData: JSON.stringify({ ...body, adaptive: false }) });
    });
    await page
      .getByRole("button", { name: /What if/i })
      .first()
      .click();
    await page
      .getByRole("button", { name: /Retire at 57/ })
      .first()
      .click();
    await page
      .getByText(/What-if applied/)
      .first()
      .waitFor({ timeout: 120000 });
    await page.waitForTimeout(1500);
    const heirsCard = squash(
      await page.locator('article[aria-labelledby="baseline-donabach"] section[data-valuation="heirs"]').innerText(),
    );
    const heirsCells = await page
      .locator('[role="group"][aria-label*="advantage against"] [data-valuation="heirs"]')
      .allInnerTexts();
    check(
      /(?:Up|Down) [\d.$,kM]+ from your plan|No change from your plan/.test(heirsCard) &&
        heirsCells.length === 4 &&
        heirsCells.every((t) =>
          /(?:Up|Down) [\d.]+ percentage points? from your plan|No change from your plan/.test(t),
        ),
      `compare with a what-if: the ${heirs} figures (the plan's card and all four advantage cells) show how far they moved`,
    );
    await context.close();
  }

  // --- The same screen at a phone's and a tablet's width, with the plan the API sent served as it was ----------------------
  {
    const { context: seed, page: seedPage } = await openPage(browser, { width: 1440 });
    await seedPage.route("**/api/plan", async (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}");
      await route.continue({ postData: JSON.stringify({ ...body, adaptive: false }) });
    });
    const asked = seedPage.waitForResponse(
      (r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/plan",
    );
    await seedPage.goto(base + "/compare", { waitUntil: "networkidle" });
    const planJson = await (await asked).json();
    await seed.close();
    for (const width of [390, 768]) {
      const { context, page, issues } = await openPage(browser, { width, height: 900 });
      await page.route("**/api/plan", (route) => route.fulfill({ json: planJson }));
      await page.goto(base + "/compare", { waitUntil: "networkidle" });
      await page
        .getByText(/Where the advantage comes from/)
        .first()
        .waitFor({ timeout: 60000 });
      await page.waitForTimeout(800);
      // The panels this round changed (the note on how wealth is valued, the advantage, the cards): nothing in them may reach past
      // the panel, and so past the window. (The chart of "Where the advantage comes from" is older and is not asked here.)
      const ours = [
        'section[aria-label="How wealth at the horizon is valued"]',
        'section[aria-labelledby="advantage-title"]',
        'section[aria-labelledby="baselines-title"] article',
      ].join(", ");
      const layout = await layoutOf(page, ours);
      const reach = await page.evaluate(
        (selector) =>
          Math.max(
            0,
            ...[...document.querySelectorAll(selector)].map((el) =>
              Math.round(el.getBoundingClientRect().right - window.innerWidth),
            ),
          ),
        ours,
      );
      const both = squash(await page.locator("main").innerText());
      check(
        reach <= 0 &&
          layout.spill.length === 0 &&
          layout.small.length === 0 &&
          both.includes(planJson.settings.heirs_label),
        `compare at ${width}px: both valuations fit (nothing in the note, the advantage panel or the cards reaches past its panel or the window, no text under 14px)${layout.spill.length ? ` (${layout.spill.join(", ")})` : ""}${reach > 0 ? ` (${reach}px past the window)` : ""}`,
      );
      check(issues.length === 0, `compare at ${width}px: no console errors${issues.length ? ` (${issues[0]})` : ""}`);
      if (width === 390) await page.screenshot({ path: `${out}/valuations-compare-390.png`, fullPage: true });
      await context.close();
    }
  }

  // --- The showcase wealth screen: the lines and the headline are liquidated, the heirs block sits under the headline --------
  const showcase = await getJson("/showcase");
  const { wealth } = showcase;
  const horizon = wealth.horizon_age;
  const { heirs } = wealth;
  check(
    typeof wealth.liquidated_label === "string" &&
      wealth.liquidated_label.length > 0 &&
      typeof heirs.label === "string" &&
      heirs.note.length > 0 &&
      typeof heirs.median_rate === "number" &&
      typeof heirs.median_dollars === "number" &&
      !Object.keys(heirs).some((k) => k.startsWith("risk_adjusted")),
    `showcase api: the wealth carries "${wealth.liquidated_label}" and a heirs block ("${heirs.label}": the rate, the note, the two medians and the median advantage) with no risk-adjusted figure`,
  );
  {
    const { context, page, issues } = await openPage(browser, { width: 1440 });
    await page.goto(base + "/showcase/wealth", { waitUntil: "networkidle" });
    await page.locator(".recharts-wrapper").first().waitFor({ timeout: 90000 });
    await page.getByRole("button", { name: "Show what Donabach does" }).click();
    await page.getByRole("heading", { level: 2, name: "Median advantage" }).waitFor({ timeout: 10000 });
    await page.waitForTimeout(1500);
    const mainBefore = squash(await page.locator("main").innerText());
    const headline = squash(await page.locator('section[aria-label^="Donabach\'s advantage"]').innerText());
    const chartPanel = squash(await page.locator('section[aria-labelledby="wealth-title"]').innerText());
    check(
      headline.startsWith(wealth.liquidated_label) && chartPanel.includes(wealth.liquidated_label),
      `showcase wealth: the headline and the chart are labelled "${wealth.liquidated_label}", as the API words it`,
    );

    const block = page.locator('section[aria-labelledby="heirs-title"]');
    const blockText = squash(await block.innerText());
    check(
      (await block.isVisible()) &&
        blockText.startsWith(heirs.label) &&
        blockText.includes(`Donabach, typical (median) ${money(heirs.plan_median_at_horizon)}`) &&
        blockText.includes(`${wealth.advisor_label}, typical (median) ${money(heirs.advisor_median_at_horizon)}`),
      `showcase wealth: under the headline a "${heirs.label}" block gives the typical (median) wealth for Donabach (${money(heirs.plan_median_at_horizon)}) and the ${wealth.advisor_label.toLowerCase()} (${money(heirs.advisor_median_at_horizon)}), as the API has them`,
    );
    check(
      blockText.includes(
        `Median advantage ${ratePct(heirs.median_rate)} a year ${moreOrLess(heirs.median_dollars, horizon)}`,
      ),
      `showcase wealth: and the median advantage a year and in dollars (${ratePct(heirs.median_rate)} a year, ${moreOrLess(heirs.median_dollars, horizon)})`,
    );
    // The block sits between the headline and the chart.
    const order = await page.evaluate(() => {
      const top = (el) => el.getBoundingClientRect().top;
      const headlineBox = document.querySelector('section[aria-label^="Donabach\'s advantage"]');
      const heirsBox = document.querySelector('section[aria-labelledby="heirs-title"]');
      const chart = document.querySelector('section[aria-labelledby="wealth-title"]');
      return top(headlineBox) < top(heirsBox) && top(heirsBox) < top(chart);
    });
    check(order, "showcase wealth: the heirs block is under the headline and above the chart");

    // The note: its first sentence on the screen (the rate in it), the rest behind a disclosure.
    const first = squash(firstSentence(heirs.note));
    const rest = squash(
      heirs.note.slice(heirs.note.indexOf(firstSentence(heirs.note)) + firstSentence(heirs.note).length),
    );
    const fold = block.getByRole("button", { name: new RegExp(`^Why ${pct0(heirs.rate)}`) });
    check(
      blockText.includes(first) &&
        first.includes(pct0(heirs.rate)) &&
        rest.length > 0 &&
        !mainBefore.includes(rest.slice(0, 60)) &&
        (await fold.getAttribute("aria-expanded")) === "false",
      `showcase wealth: the first sentence of the API's note (the rate, ${pct0(heirs.rate)}) is on the screen and the rest of it is folded away`,
    );
    await fold.click();
    await page.waitForTimeout(500);
    const opened = squash(await block.innerText());
    check(
      opened.includes(rest),
      "showcase wealth: opened, the disclosure gives the rest of the API's note, word for word",
    );

    // The risk-adjusted advantage is still shown once, on the headline, and there is none in the heirs block.
    const main = squash(await page.locator("main").innerText());
    check(
      main.split(wealth.risk_adjusted_label).length - 1 === 1 &&
        main.split(squash(wealth.risk_adjusted_explanation)).length - 1 === 1 &&
        !/risk[- ]adjusted|certainty|risk aversion/i.test(opened),
      `showcase wealth: the risk-adjusted advantage still appears once on this screen ("${wealth.risk_adjusted_label}", its explanation once) and the heirs block has no risk-adjusted word or number`,
    );
    check(
      (await page.getByRole("heading", { level: 2, name: "Median advantage" }).count()) === 1,
      "showcase wealth: the headline's 'Median advantage' is still the only heading of that name",
    );

    const layout = await layoutOf(page);
    const weak = await lowContrast(page);
    check(
      layout.pageOverflow <= 0 && layout.small.length === 0 && layout.spill.length === 0 && weak.length === 0,
      `showcase wealth: with the heirs block open there is no overflow, no text under 14px, nothing spilling out of a panel and enough contrast${weak.length ? ` (${weak.join("; ")})` : ""}`,
    );
    const footer = squash(await page.locator("footer").innerText());
    check(
      footer.includes(FOOTER_TEXT) && !footer.includes(OLD_FOOTER_TEXT),
      "showcase wealth: the footer's simplifications read 'the standard deduction (itemizing only for charitable gifts)'",
    );
    check(issues.length === 0, `showcase wealth: no console errors${issues.length ? ` (${issues[0]})` : ""}`);
    await page.screenshot({ path: `${out}/valuations-wealth-1440.png`, fullPage: true });
    await context.close();

    // At a phone's width.
    const phone = await openPage(browser, { width: 390 });
    await phone.page.goto(base + "/showcase/wealth", { waitUntil: "networkidle" });
    await phone.page.locator(".recharts-wrapper").first().waitFor({ timeout: 90000 });
    await phone.page.getByRole("button", { name: "Show what Donabach does" }).click();
    await phone.page.getByRole("heading", { level: 2, name: "Median advantage" }).waitFor({ timeout: 10000 });
    await phone.page.waitForTimeout(1500);
    const phoneLayout = await layoutOf(phone.page);
    check(
      phoneLayout.mainOverflow <= 0 && phoneLayout.spill.length === 0 && phoneLayout.small.length === 0,
      `showcase wealth at 390px: the heirs block fits${phoneLayout.spill.length ? ` (${phoneLayout.spill.join(", ")})` : ""}`,
    );
    await phone.page.screenshot({ path: `${out}/valuations-wealth-390.png`, fullPage: true });
    await phone.context.close();
  }

  // --- The strategies screen is not touched: the median only, liquidated, no mention of heirs --------------------------------
  {
    const { context, page } = await openPage(browser, { width: 1440 });
    await page.goto(base + "/showcase/strategies", { waitUntil: "networkidle" });
    await page
      .locator(showcase.waterfall.bars.length > 0 ? "li[data-key]" : "main h1")
      .first()
      .waitFor({ timeout: 90000 });
    // Everything the screen holds but its footer (the footer's own "not modeled" line speaks of taxes paid by heirs): the folded
    // sentences count too.
    const content = squash(
      await page.evaluate(() => {
        const copy = document.querySelector("main").cloneNode(true);
        copy.querySelector("footer")?.remove();
        return copy.textContent ?? "";
      }),
    );
    const footer = squash(await page.locator("footer").innerText());
    check(
      !content.includes(heirs.label) && !/heirs/i.test(content) && !content.includes(wealth.liquidated_label),
      "showcase waterfall: the screen is not touched (median only, liquidated): no heirs figure or label, and no valuation label added",
    );
    check(
      footer.includes(FOOTER_TEXT) && !footer.includes(OLD_FOOTER_TEXT),
      "showcase waterfall: the footer's simplifications read 'the standard deduction (itemizing only for charitable gifts)'",
    );
    await context.close();
  }
  {
    const { context, page } = await openPage(browser, { width: 1440 });
    await page.goto(base + "/showcase", { waitUntil: "networkidle" });
    await page.getByRole("heading", { level: 1 }).waitFor({ timeout: 90000 });
    const footer = squash(await page.locator("footer").innerText());
    check(
      footer.includes(FOOTER_TEXT) && !footer.includes(OLD_FOOTER_TEXT),
      "showcase household: the footer's simplifications read 'the standard deduction (itemizing only for charitable gifts)'",
    );
    await context.close();
  }
  void notes;
}

if (isMain(import.meta.url)) await runAlone(runValuations, "valuations");
