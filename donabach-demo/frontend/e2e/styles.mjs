// The planning-style switch on the Plan screen (round two, part C): Equity-first | Balanced | Liability-matched | All three side by side.
//
//   BASE_URL=http://localhost:3000 CHROMIUM_PATH=... node e2e/styles.mjs
//
// Every figure on screen is compared with the plan the API sent the browser for that style (read from the browser's own POST
// /api/plan responses), and the requests the switch makes are read from what the browser sends: one /plan call per style, on
// the same household and seed. Loading and failure are looked at per column with the API held back or refusing.

import { lowContrast } from "./showcase.mjs";
import {
  isMain,
  layoutOf,
  money,
  openPage,
  pct1,
  printed,
  runAlone,
  signedMoney,
  signedPercent,
  squash,
  years,
} from "./lib.mjs";

const STYLES = ["equity_first", "balanced", "liability_matched"];
const NAME = { equity_first: "Equity-first", balanced: "Balanced", liability_matched: "Liability-matched" };
const ALL = "All three side by side";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const EPSILON = 1e-9;

/** The chip words for a plan's reserve and stock choices, as the screen says them. */
const chipWords = (choices) => ({
  reserve: choices.reserve === "off" ? "Off" : years(Number(choices.reserve)),
  stock: choices.reserve !== "off" ? "Everything outside the reserve" : `${choices.stock_share}% stocks`,
});

/** Does any advantage of this plan (both valuations, both measures) have a 90% range that includes zero, as printed? */
const spansZero = (plan) =>
  [plan.stats.advantage, plan.stats.advantage_heirs].some((a) =>
    ["median", "risk_adjusted"].some((m) => printed(a[`${m}_low`]) <= 0 && printed(a[`${m}_high`]) >= 0),
  );

/**
 * What a plan's figures say on screen, section by section, against the API's plan. `scope` holds the sections (a column of the
 * side-by-side view, or the page for a single style) and `id` is their prefix.
 */
async function figuresMatch(scope, id, plan) {
  const h = plan.settings.horizon_age;
  const s = plan.stats;
  const ria = plan.baselines.find((b) => b.key === "good_ria");
  const sectionText = async (suffix) =>
    squash(await scope.locator(`section[aria-labelledby="${id}-${suffix}"]`).innerText());
  const wealth = await sectionText("wealth");
  let ok =
    wealth.startsWith(plan.settings.liquidated_label) &&
    wealth.includes(`Typical outcome at ${h} ${money(s.typical_outcome.median)}`) &&
    wealth.includes(`Bad case (10th percentile) ${money(s.typical_outcome.p10)}`);
  const advantage = await sectionText("advantage");
  ok &&= advantage.startsWith("Advantage over a good RIA");
  for (const [label, a] of [
    [plan.settings.liquidated_label, s.advantage],
    [plan.settings.heirs_label, s.advantage_heirs],
  ]) {
    const group = squash(
      await scope
        .locator(
          `section[aria-labelledby="${id}-advantage"] [role="group"][aria-label="Advantage over a good RIA, ${label}"]`,
        )
        .innerText(),
    );
    ok &&= group.startsWith(label);
    for (const [name, m] of [
      ["Median advantage", "median"],
      ["Risk-adjusted advantage", "risk_adjusted"],
    ]) {
      const spans = printed(a[`${m}_low`]) <= 0 && printed(a[`${m}_high`]) >= 0;
      ok &&=
        group.includes(`${name} ${signedPercent(a[m])} a year`) &&
        group.includes(
          `${signedMoney(a[`${m}_dollars`])} at ${h} · 90% range ${signedPercent(a[`${m}_low`])} to ${signedPercent(a[`${m}_high`])}`,
        ) &&
        // the dagger is on the figure of a range that includes zero, and only there
        group.includes(`${name} ${signedPercent(a[m])} a year †`) === spans;
    }
  }
  const risks = await sectionText("risks");
  ok &&=
    risks.includes(`Lifetime taxes ${money(s.lifetime_taxes)} A good RIA: ${money(s.ria_lifetime_taxes)}`) &&
    risks.includes(
      `Chance of running out of money ${pct1(s.shortfall_chance)} A good RIA: ${pct1(ria.shortfall_chance)}`,
    ) &&
    risks.includes(
      `Chance of selling stocks in a falling year to pay for goals or spending ${pct1(s.forced_sale_chance)} A good RIA: ${pct1(s.ria_forced_sale_chance)}`,
    );
  return ok;
}

/** The two limits of a liability-matched plan on screen, against the API's `liability`. */
async function limitsMatch(scope, id, plan) {
  const l = plan.liability;
  const text = squash(await scope.locator(`section[aria-labelledby="${id}-limits"]`).innerText());
  const within = (v, limit) => (v <= limit + EPSILON ? "within" : "above");
  const noHigher = (v, limit) => (v <= limit + EPSILON ? "no higher" : "higher");
  return (
    text.includes(
      l.feasible
        ? "Both limits are met on the futures it was chosen on."
        : "No strategy met both limits on the futures it was chosen on, so this is the one that came closest.",
    ) &&
    text.includes(`Stocks sold in a falling year to pay for goals or spending ${pct1(l.forced_sale_chance)}`) &&
    text.includes(
      `On fresh futures: ${within(l.forced_sale_chance, l.forced_sale_limit)} the ${pct1(l.forced_sale_limit)} limit`,
    ) &&
    text.includes(
      `On the futures it was chosen on: ${pct1(l.chosen_on_forced_sale_chance)}, ${within(l.chosen_on_forced_sale_chance, l.forced_sale_limit)} the limit`,
    ) &&
    text.includes(`Running out of money ${pct1(l.ruin_chance)}`) &&
    text.includes(
      `On fresh futures: ${noHigher(l.ruin_chance, l.advisor_ruin_chance)} than a good RIA's ${pct1(l.advisor_ruin_chance)}`,
    ) &&
    text.includes(
      `On the futures it was chosen on: ${pct1(l.chosen_on_ruin_chance)} against ${pct1(l.chosen_on_advisor_ruin_chance)}, ${noHigher(l.chosen_on_ruin_chance, l.chosen_on_advisor_ruin_chance)}`,
    ) &&
    text.includes(`Spending reserve ${years(l.reserve_years)}`)
  );
}

export async function runStyles({ browser, base, out, check, notes }) {
  const radio = (page, name) => page.getByRole("radio", { name, exact: true });
  const waitFor = async (answers, style, seconds = 420) => {
    for (let i = 0; i < seconds * 2 && !answers[style]; i++) await sleep(500);
    if (!answers[style]) throw new Error(`the ${style} plan never arrived`);
    return answers[style];
  };
  const answers = {}; // by style, the first plan the API sent this browser in that style
  const log = []; // every plan it sent, in the order they arrived, with the request each answers
  const requests = []; // what this browser asked of /plan

  // === One browser through the whole switch: the default, each style on its own, all three, and toggling back =====================
  {
    const { context, page, issues } = await openPage(browser, { width: 1440 });
    const yearDetails = [];
    let whatIf = null;
    page.on("request", (r) => {
      if (r.method() !== "POST") return;
      const { pathname } = new URL(r.url());
      if (pathname === "/api/plan") requests.push(r.postDataJSON());
      if (pathname === "/api/plan/year-detail") yearDetails.push(r.postDataJSON());
    });
    page.on("response", async (r) => {
      if (r.request().method() !== "POST") return;
      const { pathname } = new URL(r.url());
      if (pathname === "/api/plan") {
        const request = r.request().postDataJSON();
        const json = await r.json().catch(() => null);
        log.push({ style: request.planning_style, request, json });
        answers[request.planning_style] ??= json;
      }
      if (pathname === "/api/plan/whatif") whatIf = await r.json().catch(() => null);
    });
    // The year-by-year job of the what-if is not what is looked at here (and costs the API a minute): ask for none.
    await page.route("**/api/plan/whatif", async (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}");
      await route.continue({ postData: JSON.stringify({ ...body, adaptive: false }) });
    });

    await page.goto(base + "/plan", { waitUntil: "networkidle" });
    await page
      .getByText(/Hold (the next \d+ years of what you will need|\d+% of)/)
      .first()
      .waitFor({ timeout: 120000 });
    const equity = await waitFor(answers, "equity_first");
    const group = page.getByRole("radiogroup", { name: "Planning style" });
    const names = (
      await group.getByRole("radio").evaluateAll((els) => els.map((el) => el.closest("label")?.innerText.trim() ?? ""))
    ).map(squash);
    check(
      JSON.stringify(names) === JSON.stringify([...STYLES.map((s) => NAME[s]), ALL]) &&
        (await radio(page, "Equity-first").isChecked()),
      `styles: the Plan screen has a "Planning style" radio group (${names.join(" | ")}) with Equity-first chosen to start with`,
    );
    check(
      squash(await page.locator("#strategy-sentence").innerText()) === squash(equity.strategy.sentence) &&
        requests.length === 1 &&
        requests[0].planning_style === "equity_first" &&
        equity.settings.planning_style === "equity_first" &&
        equity.liability === null,
      "styles: Equity-first is what the screen shows, as before: the equity-first plan's own sentence, from one /plan call that names its style",
    );
    check(
      (await group.getAttribute("aria-describedby")) !== null &&
        squash(await page.locator(`[id="${await group.getAttribute("aria-describedby")}"]`).innerText()).length > 20,
      "styles: the group is labelled 'Planning style' and described by a line on the chosen style",
    );

    // --- Balanced, by keyboard -------------------------------------------------------------------------------------------
    await radio(page, "Equity-first").focus();
    await page.keyboard.press("ArrowRight");
    check(
      (await radio(page, "Balanced").isChecked()) &&
        (await page.evaluate(() => document.activeElement?.closest("label")?.innerText.trim())) === "Balanced",
      "styles: the arrow key moves the choice (and the focus) to Balanced: the switch is a real radio group",
    );
    const sawBusy = await page
      .getByText("Planning in the balanced style…")
      .waitFor({ timeout: 4000 })
      .then(
        () => true,
        () => false,
      );
    const balanced = await waitFor(answers, "balanced");
    check(
      requests.length === 2 &&
        requests[1].planning_style === "balanced" &&
        requests[1].seed === equity.settings.seed &&
        requests[1].adaptive === false &&
        JSON.stringify(requests[1].household) === JSON.stringify(requests[0].household) &&
        JSON.stringify(requests[1].shock) === JSON.stringify(requests[0].shock) &&
        balanced.settings.planning_style === "balanced" &&
        balanced.settings.seed === equity.settings.seed &&
        balanced.settings.eval_seed === equity.settings.eval_seed,
      `styles: Balanced calls /plan with planning_style "balanced" on the same household and the same seed (${requests[1].seed}), asking for no year-by-year job; the answer is on the same futures (eval seed ${balanced.settings.eval_seed})`,
    );
    if (!sawBusy)
      notes.push(
        "styles: the balanced plan came too quickly to see its loading state in the single view (it is checked per column below)",
      );
    await page
      .locator("#strategy-sentence")
      .filter({ hasText: balanced.strategy.sentence.slice(0, 40) })
      .waitFor({ timeout: 60000 });
    check(
      squash(await page.locator("#strategy-sentence").innerText()) === squash(balanced.strategy.sentence) &&
        (await page.getByText(balanced.planner_label).count()) >= 1,
      "styles: Balanced shows its own plan: the strategy sentence and planner label are the API's for that style",
    );
    check(
      await figuresMatch(page, "style-results", balanced),
      "styles: Balanced's results panel gives its wealth, its advantage (both measures, both valuations), taxes and risks, all as the API has them",
    );
    const rows = await page.locator("tr[data-row-key]").count();
    check(
      rows === balanced.rows.length &&
        (await page.getByRole("radio", { name: "Year-by-year plan" }).isDisabled()) &&
        (await page.getByText("The year-by-year planner runs for the equity-first plan only").count()) === 1,
      `styles: its year table lists the fixed strategy's ${balanced.rows.length} years, says the year-by-year planner is for the equity-first plan only, and the year-by-year choice waits`,
    );
    await page.locator("tr[data-row-key]").nth(3).click();
    await page.getByRole("dialog").waitFor({ timeout: 30000 });
    for (let i = 0; i < 100 && yearDetails.length === 0; i++) await sleep(100);
    check(
      yearDetails.length >= 1 &&
        JSON.stringify(yearDetails.at(-1).choices) === JSON.stringify(balanced.strategy.choices),
      "styles: a year opened in Balanced's table asks the API about Balanced's own strategy, not the default one",
    );
    await page.keyboard.press("Escape");
    check(
      (await page.getByRole("heading", { name: "Model recommendation" }).count()) === 1,
      "styles: Balanced keeps the model recommendation panel (the planner consults it for this style)",
    );

    // --- Liability-matched ------------------------------------------------------------------------------------------------
    await radio(page, "Balanced").focus();
    await page.keyboard.press("ArrowRight");
    check(await radio(page, "Liability-matched").isChecked(), "styles: the next arrow key moves to Liability-matched");
    const sawLiabilityBusy = await page
      .getByText("Planning in the liability-matched style…")
      .waitFor({ timeout: 4000 })
      .then(
        () => true,
        () => false,
      );
    const liability = await waitFor(answers, "liability_matched");
    check(
      sawLiabilityBusy,
      "styles: while the liability-matched plan is searched for (it takes the longest) the screen says so, with a spinner, and the switch stays usable",
    );
    check(
      requests.length === 3 &&
        requests[2].planning_style === "liability_matched" &&
        requests[2].seed === equity.settings.seed &&
        liability.settings.planning_style === "liability_matched" &&
        liability.liability !== null &&
        typeof liability.liability.feasible === "boolean",
      `styles: Liability-matched calls /plan with planning_style "liability_matched" on the same seed, and its answer carries the two limits (reserve ${liability.liability?.reserve_years} years, feasible ${liability.liability?.feasible})`,
    );
    await page
      .locator("#strategy-sentence")
      .filter({ hasText: liability.strategy.sentence.slice(0, 40) })
      .waitFor({ timeout: 60000 });
    check(
      squash(await page.locator("#strategy-sentence").innerText()) === squash(liability.strategy.sentence) &&
        (await figuresMatch(page, "style-results", liability)),
      "styles: Liability-matched shows its own plan and its figures as the API has them",
    );
    check(
      await limitsMatch(page, "style-results", liability),
      `styles: it shows the two limits it was chosen under: stocks sold in a falling year against the ${pct1(liability.liability.forced_sale_limit)} limit, running out of money against the good RIA's, whether both were met (${liability.liability.feasible ? "yes" : "no"}), the reserve (${years(liability.liability.reserve_years)}), as the API has them`,
    );
    check(
      (await page.getByRole("heading", { name: "Model recommendation" }).count()) === 0,
      "styles: and no model recommendation panel (the API does not consult the recommender for this style)",
    );

    // --- All three side by side: from the three calls, on one screen -------------------------------------------------------
    await radio(page, "Liability-matched").focus();
    await page.keyboard.press("ArrowRight");
    check(await radio(page, ALL).isChecked(), "styles: the next arrow key lands on 'All three side by side'");
    await page.locator('article[data-style="liability_matched"][data-status="ready"]').waitFor({ timeout: 30000 });
    check(
      requests.length === 3 &&
        STYLES.every((s) => requests.some((r) => r.planning_style === s)) &&
        new Set([equity, balanced, liability].map((p) => p.settings.seed)).size === 1,
      `styles: 'All three side by side' needed no new call: one /plan call per style (${requests.map((r) => r.planning_style).join(", ")}), all three answers on seed ${equity.settings.seed}`,
    );
    const plans = { equity_first: equity, balanced, liability_matched: liability };
    let columnsOk = true;
    const lines = [];
    for (const style of STYLES) {
      const column = page.locator(`article[data-style="${style}"]`);
      const plan = plans[style];
      const id = `style-${style}`;
      const ready =
        (await column.getAttribute("data-status")) === "ready" && (await column.getAttribute("aria-busy")) === null;
      const heading = squash(await column.locator(`#${id}-name`).innerText());
      const planText = squash(await column.locator(`section[aria-labelledby="${id}-plan"]`).innerText());
      const chips = squash(
        await column
          .getByRole("list", { name: `The reserve and stock choices in the ${NAME[style]} plan` })
          .innerText(),
      );
      const words = chipWords(plan.strategy.choices);
      const okFigures = await figuresMatch(column, id, plan);
      const okLimits =
        style === "liability_matched"
          ? await limitsMatch(column, id, plan)
          : (await column.locator(`section[aria-labelledby="${id}-limits"]`).count()) === 0;
      const ok =
        ready &&
        heading === NAME[style] &&
        planText.includes(plan.strategy.label) &&
        chips.includes(`Spending reserve ${words.reserve}`) &&
        chips.includes(`Stock share ${words.stock}`) &&
        okFigures &&
        okLimits;
      columnsOk &&= ok;
      lines.push(`${NAME[style]} ${money(plan.stats.typical_outcome.median)}`);
    }
    check(
      columnsOk,
      `styles: each column gives the plan's label, its reserve and stock choices in words, wealth, advantage (both measures, both valuations), taxes, the chance of running out of money and of selling stocks in a falling year beside the good RIA's, as the API has them (${lines.join(", ")} typical)`,
    );
    const fold = page.locator('article[data-style="balanced"]').getByRole("button", { name: "The plan in words" });
    check(
      (await fold.getAttribute("aria-expanded")) === "false",
      "styles: each column's whole sentence is folded away until opened",
    );
    await fold.click();
    await page.waitForTimeout(400);
    check(
      squash(await page.locator('article[data-style="balanced"]').innerText()).includes(
        squash(balanced.strategy.sentence),
      ),
      "styles: opened, it gives the API's whole sentence for that plan",
    );
    const note = squash(await page.locator('section[aria-labelledby="styles-title"] > p').last().innerText());
    const anyZero = STYLES.some((s) => spansZero(plans[s]));
    check(
      anyZero
        ? note.startsWith("† The 90% range includes zero")
        : note.startsWith("No advantage here has a 90% range that includes zero"),
      `styles: the note under the columns says what a dagger means, or that none is needed (${anyZero ? "a range includes zero" : "none does"})`,
    );

    // The columns are side by side with their sections lined up.
    const geometry = await page.evaluate(() => {
      const columns = [...document.querySelectorAll("article[data-style]")].map((a) => a.getBoundingClientRect());
      const tops = (suffix) =>
        [...document.querySelectorAll(`article[data-style] section[aria-labelledby$="-${suffix}"]`)].map((el) =>
          Math.round(el.getBoundingClientRect().top),
        );
      return {
        lefts: columns.map((c) => Math.round(c.left)),
        tops: columns.map((c) => Math.round(c.top)),
        widths: columns.map((c) => Math.round(c.width)),
        wealth: tops("wealth"),
        advantage: tops("advantage"),
        risks: tops("risks"),
      };
    });
    const aligned = (xs) => xs.length === 3 && Math.max(...xs) - Math.min(...xs) <= 1;
    check(
      geometry.lefts[0] < geometry.lefts[1] &&
        geometry.lefts[1] < geometry.lefts[2] &&
        aligned(geometry.tops) &&
        Math.min(...geometry.widths) >= 300 &&
        aligned(geometry.wealth) &&
        aligned(geometry.advantage) &&
        aligned(geometry.risks),
      `styles: at 1440px the three columns stand side by side (widths ${geometry.widths.join(", ")}px) with their sections lined up row by row (wealth at ${geometry.wealth.join(", ")}, advantage at ${geometry.advantage.join(", ")}, taxes and risks at ${geometry.risks.join(", ")})`,
    );
    const layout = await layoutOf(page);
    check(
      layout.pageOverflow <= 0 && layout.small.length === 0 && layout.spill.length === 0,
      `styles: the side-by-side view has no horizontal overflow, no text under 14px and nothing spilling out of its columns${layout.spill.length ? ` (${layout.spill.join(", ")})` : ""}`,
    );
    const weak = await lowContrast(page);
    check(
      weak.length === 0,
      `styles: all text of the side-by-side view has enough contrast${weak.length ? ` (${weak.join("; ")})` : ""}`,
    );
    await page.screenshot({ path: `${out}/styles-plan-all-1440.png`, fullPage: true });

    // --- Toggling back is instant: the answers are kept for the session --------------------------------------------------
    const instant = async (name, sentence) => {
      const started = Date.now();
      await radio(page, name).check({ force: true });
      await page
        .locator("#strategy-sentence")
        .filter({ hasText: sentence.slice(0, 40) })
        .waitFor({ timeout: 2000 });
      return Date.now() - started;
    };
    const toEquity = await instant("Equity-first", equity.strategy.sentence);
    const toBalanced = await instant("Balanced", balanced.strategy.sentence);
    const toLiability = await instant("Liability-matched", liability.strategy.sentence);
    check(
      requests.length === 3 && Math.max(toEquity, toBalanced, toLiability) < 1500,
      `styles: toggling back is instant and asks for nothing (${toEquity}, ${toBalanced} and ${toLiability} ms; still ${requests.length} /plan calls)`,
    );
    await radio(page, ALL).check({ force: true });
    await page.locator('article[data-style="liability_matched"][data-status="ready"]').waitFor({ timeout: 5000 });
    check(requests.length === 3, "styles: and back to all three: still no new call");

    // --- The household changes (a what-if): every style is planned again on the new household ---------------------------------
    await radio(page, "Balanced").check({ force: true });
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
      .waitFor({ timeout: 180000 });
    for (let i = 0; i < 960 && requests.length < 4; i++) await sleep(500);
    const asked = requests[3];
    check(
      requests.length === 4 &&
        asked.planning_style === "balanced" &&
        asked.household.goals.retirement_age === 57 &&
        asked.seed === whatIf.plan.settings.seed &&
        JSON.stringify(asked.shock) === JSON.stringify(whatIf.shock) &&
        JSON.stringify(asked.household) === JSON.stringify(whatIf.household),
      "styles: a what-if changes the household, so Balanced is planned again on that household (retire at 57), with the what-if's own seed and shock",
    );
    for (
      let i = 0;
      i < 960 && !log.some((e) => e.style === "balanced" && e.request.household.goals.retirement_age === 57);
      i++
    )
      await sleep(500);
    const newBalanced = log.find((e) => e.style === "balanced" && e.request.household.goals.retirement_age === 57).json;
    await page
      .locator('section[aria-labelledby="style-results-wealth"]')
      .filter({ hasText: money(newBalanced.stats.typical_outcome.median) })
      .waitFor({ timeout: 60000 });
    check(
      newBalanced !== balanced && (await figuresMatch(page, "style-results", newBalanced)),
      `styles: and the screen then shows that plan (typical ${money(newBalanced.stats.typical_outcome.median)}, not the earlier ${money(balanced.stats.typical_outcome.median)})`,
    );
    await page.getByRole("button", { name: /Reset/i }).first().click();
    await page
      .getByText(/What-if applied/)
      .first()
      .waitFor({ state: "detached", timeout: 30000 });
    await page
      .locator('section[aria-labelledby="style-results-wealth"]')
      .filter({ hasText: money(balanced.stats.typical_outcome.median) })
      .waitFor({ timeout: 5000 });
    check(
      requests.length === 4 && (await figuresMatch(page, "style-results", balanced)),
      "styles: after a reset the first household's Balanced plan is back at once, kept from before (no new call)",
    );
    check(issues.length === 0, `styles: no console errors${issues.length ? ` (${issues[0]})` : ""}`);
    await context.close();
  }

  // === One column at a time: loading and failure belong to the column that has them ============================================
  {
    const { context, page } = await openPage(browser, { width: 1440 });
    const MESSAGE = "the e2e made this error up";
    let release;
    const held = new Promise((resolve) => (release = resolve));
    let refuse = true;
    const seen = { balanced: 0, liability_matched: 0 };
    const got = {};
    page.on("response", async (r) => {
      if (r.request().method() === "POST" && new URL(r.url()).pathname === "/api/plan" && r.ok()) {
        got[r.request().postDataJSON().planning_style] = await r.json().catch(() => null);
      }
    });
    await page.route("**/api/plan", async (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}");
      if (body.planning_style === "balanced") {
        seen.balanced++;
        await held;
      }
      if (body.planning_style === "liability_matched") {
        seen.liability_matched++;
        if (refuse)
          return route.fulfill({
            status: 500,
            contentType: "application/json",
            body: JSON.stringify({ detail: MESSAGE }),
          });
      }
      await route.continue({ postData: JSON.stringify({ ...body, adaptive: false }) });
    });
    await page.goto(base + "/plan", { waitUntil: "networkidle" });
    await page
      .getByText(/Hold (the next \d+ years of what you will need|\d+% of)/)
      .first()
      .waitFor({ timeout: 120000 });
    await radio(page, ALL).check({ force: true });
    const liabilityColumn = page.locator('article[data-style="liability_matched"]');
    const balancedColumn = page.locator('article[data-style="balanced"]');
    const equityColumn = page.locator('article[data-style="equity_first"]');
    await liabilityColumn.locator('[role="alert"]').waitFor({ timeout: 60000 });
    const alertText = squash(await liabilityColumn.locator('[role="alert"]').innerText());
    check(
      (await liabilityColumn.getAttribute("data-status")) === "failed" &&
        alertText.includes(MESSAGE) &&
        alertText.includes("Try again"),
      `styles: when the API refuses one plan the failure is shown in that column, with the API's own message ("${MESSAGE}") and a way to ask again`,
    );
    check(
      (await balancedColumn.getAttribute("aria-busy")) === "true" &&
        (await balancedColumn.getAttribute("data-status")) === "loading" &&
        (await balancedColumn.getByText("Planning in the balanced style…").count()) === 1 &&
        (await equityColumn.getAttribute("aria-busy")) === null &&
        (await equityColumn.getAttribute("data-status")) === "ready" &&
        (await equityColumn.locator('[role="alert"]').count()) === 0 &&
        (await balancedColumn.locator('[role="alert"]').count()) === 0,
      "styles: while the balanced plan is still being searched for, only its column shows a loading state; the failed column's alert is not in the others",
    );
    // The finished column stays usable meanwhile.
    const equityFold = equityColumn.getByRole("button", { name: "The plan in words" });
    await equityFold.click();
    await page.waitForTimeout(400);
    for (let i = 0; i < 100 && !got.equity_first; i++) await sleep(100);
    check(
      (await equityFold.getAttribute("aria-expanded")) === "true" &&
        squash(await equityColumn.innerText()).includes(squash(got.equity_first.strategy.sentence)),
      "styles: and the finished column stays usable meanwhile (its whole sentence opens)",
    );
    release();
    await balancedColumn.and(page.locator('[data-status="ready"]')).waitFor({ timeout: 300000 });
    check(
      (await liabilityColumn.getAttribute("data-status")) === "failed" &&
        (await balancedColumn.locator('[role="alert"]').count()) === 0,
      "styles: when the held column arrives it fills in by itself, and the other column's failure stays where it was",
    );
    refuse = false;
    await liabilityColumn.getByRole("button", { name: "Try again, Liability-matched plan" }).click();
    await liabilityColumn.and(page.locator('[data-status="loading"]')).waitFor({ timeout: 10000 });
    await liabilityColumn.and(page.locator('[data-status="ready"]')).waitFor({ timeout: 420000 });
    check(
      seen.liability_matched === 2 &&
        (await figuresMatch(liabilityColumn, "style-liability_matched", got.liability_matched)) &&
        (await limitsMatch(liabilityColumn, "style-liability_matched", got.liability_matched)),
      "styles: 'Try again' asks for that style's plan once more and the column fills in with the API's figures and limits",
    );
    await context.close();
  }

  // === The same view at a tablet's, a phone's and the narrowest phone's width, with the plans served as the API sent them =========
  {
    const serve = async (page) =>
      page.route("**/api/plan", (route) => {
        const style = JSON.parse(route.request().postData() ?? "{}").planning_style;
        // As the API sent it, but without a year-by-year job to follow.
        return route.fulfill({ json: { ...answers[style], adaptive: null, adaptive_job: null } });
      });
    for (const width of [1100, 768, 390, 320]) {
      const { context, page, issues } = await openPage(browser, { width, height: 900 });
      await serve(page);
      await page.goto(base + "/plan", { waitUntil: "networkidle" });
      await page.locator("#strategy-sentence").waitFor({ timeout: 60000 });
      const group = page.getByRole("radiogroup", { name: "Planning style" });
      const faces = await group.evaluate((el) =>
        [...el.querySelectorAll("label")].map((l) => ({
          left: l.getBoundingClientRect().left,
          right: l.getBoundingClientRect().right,
          top: l.getBoundingClientRect().top,
        })),
      );
      const fits = faces.every((f) => f.left >= 0 && f.right <= width);
      check(
        faces.length === 4 && fits,
        `styles at ${width}px: the four choices of the switch are all on screen (${faces.map((f) => Math.round(f.right)).join(", ")} right edges, window ${width})`,
      );
      await radio(page, ALL).check({ force: true });
      await page.locator('article[data-style="liability_matched"][data-status="ready"]').waitFor({ timeout: 30000 });
      await page.waitForTimeout(500);
      const columns = await page.evaluate(() =>
        [...document.querySelectorAll("article[data-style]")].map((a) => {
          const r = a.getBoundingClientRect();
          return {
            left: Math.round(r.left),
            top: Math.round(r.top),
            bottom: Math.round(r.bottom),
            width: Math.round(r.width),
          };
        }),
      );
      const stacked =
        columns[1].top >= columns[0].bottom - 1 &&
        columns[2].top >= columns[1].bottom - 1 &&
        columns.every((c) => Math.abs(c.left - columns[0].left) <= 1);
      const side =
        columns[0].left < columns[1].left &&
        columns[1].left < columns[2].left &&
        Math.abs(columns[0].top - columns[2].top) <= 1;
      check(
        width >= 1100 ? side : stacked,
        width >= 1100
          ? `styles at ${width}px: the columns stand side by side (${columns.map((c) => c.width).join(", ")}px wide)`
          : `styles at ${width}px: the columns are stacked, one above the other (${columns.map((c) => c.width).join(", ")}px wide)`,
      );
      const layout = await layoutOf(page);
      check(
        layout.mainOverflow <= 0 && layout.spill.length === 0 && layout.small.length === 0,
        `styles at ${width}px: nothing reaches past the page's content or out of its column, and no text is under 14px${layout.spill.length ? ` (${layout.spill.join(", ")})` : ""}${layout.mainOverflow > 0 ? ` (main overflows by ${layout.mainOverflow}px)` : ""}`,
      );
      if (width === 390) {
        const weak = await lowContrast(page);
        check(
          weak.length === 0,
          `styles at ${width}px: all text has enough contrast${weak.length ? ` (${weak.join("; ")})` : ""}`,
        );
        await page.screenshot({ path: `${out}/styles-plan-all-390.png`, fullPage: true });
      }
      if (width === 320) {
        const stacksSwitch = new Set(faces.map((f) => Math.round(f.top))).size === 4;
        check(
          stacksSwitch,
          "styles at 320px: the switch's four choices sit one above the other, each a full-width target",
        );
        await page.screenshot({ path: `${out}/styles-plan-all-320.png`, fullPage: true });
      }
      check(issues.length === 0, `styles at ${width}px: no console errors${issues.length ? ` (${issues[0]})` : ""}`);
      await context.close();
    }
  }
}

if (isMain(import.meta.url)) await runAlone(runStyles, "styles");
