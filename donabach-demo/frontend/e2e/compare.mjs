// Compare (/compare) as the mockup draws it: heading and lede, the navy strip, the two cards equal the plan's comparison; navy right card;
// 40px serif wealth, bars, ministack; stacks under 900px; follows the plan on screen.
import { isMain, runAlone, newPage, dollarsWhole, visibleText } from "./portal.mjs";
import { DISCLAIMER, wealthM, feeLine, signedPct2, planFromApi, toInvest } from "./invest-lib.mjs";

const rgb = (s) => s.match(/\d+/g).slice(0, 3).map(Number);

export async function runCompare({ browser, base, check }) {
  const plan = await planFromApi(base);
  const c = plan.comparison;
  const { context, page, issues } = await newPage(browser);
  await toInvest(page, base);
  await page.getByRole("button", { name: "Compare" }).click();
  await page.waitForURL("**/compare");
  const t = (id) => page.getByTestId(id).innerText();

  check(
    (await page.locator("h1").innerText()) === "Compared with a standard advisor",
    "title: Compared with a standard advisor",
  );
  check(
    (await page.locator("main .lede").innerText()) === "The same household, managed two ways.",
    "lede as the mockup",
  );
  const more = `${wealthM(c.dollars_more)} more at 80`;
  check((await t("dollars-more")) === more, `strip: ${more}`);
  check(
    (await t("rate-per-year")) === `${signedPct2(c.rate_per_year)} a year`,
    `strip: ${signedPct2(c.rate_per_year)} a year`,
  );
  check((await page.getByTestId("compare-strip").innerText()).includes("With Waramoug"), "strip starts With Waramoug");
  const strip = rgb(await page.getByTestId("compare-strip").evaluate((e) => getComputedStyle(e).backgroundColor));
  check(strip.join() === "31,58,95", "the strip is navy");
  check(
    (await t("wealth-advisor")) === wealthM(c.advisor.wealth_80) &&
      (await t("wealth-waramoug")) === wealthM(c.waramoug.wealth_80),
    `cards: ${wealthM(c.advisor.wealth_80)} vs ${wealthM(c.waramoug.wealth_80)}`,
  );

  const wealthStyle = async (side) =>
    page
      .getByTestId(`wealth-${side}`)
      .evaluate((e) => [getComputedStyle(e).fontSize, getComputedStyle(e).fontFamily, getComputedStyle(e).color]);
  const [aSize, aFont] = await wealthStyle("advisor");
  const [wSize, , wColor] = await wealthStyle("waramoug");
  check(aSize === "40px" && wSize === "40px" && /Cambria/.test(aFont), "the wealth figures are 40px serif");
  check(rgb(wColor).join() === "31,58,95", "the Waramoug figure is navy");
  const adv = page.getByTestId("card-advisor");
  const war = page.getByTestId("card-waramoug");
  const ab = await adv.boundingBox();
  const wb = await war.boundingBox();
  check(ab.x < wb.x && Math.abs(ab.y - wb.y) < 2, "the advisor is on the left, Waramoug on the right, side by side");
  check(
    (await adv.locator("h2").innerText()) === c.advisor.title && (await war.locator("h2").innerText()) === "Waramoug",
    "card titles: Standard wealth advisor, Waramoug",
  );
  const headBg = async (card) => rgb(await card.locator("h2").evaluate((e) => getComputedStyle(e).backgroundColor));
  const aHead = await headBg(adv);
  check(aHead.join() !== "31,58,95" && Math.abs(aHead[0] - aHead[2]) < 25, `the advisor header is gray (${aHead})`);
  check((await headBg(war)).join() === "31,58,95", "the Waramoug header is navy");
  check(
    rgb(await war.evaluate((e) => getComputedStyle(e).borderTopColor)).join() === "31,58,95",
    "the Waramoug card has a navy border",
  );

  for (const [side, card, el, two] of [
    ["advisor", c.advisor, adv, true],
    ["waramoug", c.waramoug, war, false],
  ]) {
    const txt = (await el.innerText()).replace(/\s+/g, " ");
    for (const l of [
      "Projected at 80",
      "Mix",
      "Accounts",
      "Roth conversion this year",
      "Yearly fee",
    ])
      check(txt.includes(l), `${side}: row "${l}"`);
    check(
      txt.includes("Harvesting losses") === (c.advisor.harvesting !== c.waramoug.harvesting),
      `${side}: the Harvesting losses row is there only when the two sides differ`,
    );
    check((await t(`mix-${side}`)) === card.mix_text, `${side}: mix text "${card.mix_text}"`);
    const stackH = await el.getByTestId("mix-bar").evaluate((e) => Math.round(e.getBoundingClientRect().height));
    check(stackH === 14, `${side}: the stacked bar is 14px`);
    check(
      (await el.getByTestId("mix-bar").locator("span").count()) === card.mix.filter((m) => m.share >= 0.0005).length,
      `${side}: stacked bar segments`,
    );
    check(
      card.accounts.every((a) => txt.includes(a)),
      `${side}: accounts lines`,
    );
    if (c.advisor.harvesting !== c.waramoug.harvesting) check(txt.includes(card.harvesting), `${side}: harvesting`);
    check(
      txt.includes(
        card.roth_conversion > 0.5
          ? `Roth conversion this year ${dollarsWhole(card.roth_conversion)}`
          : "Roth conversion this year None",
      ),
      `${side}: Roth conversion`,
    );
    check(
      (await t(`fee-${side}`)) === feeLine(card.fee_dollars, card.fee_rate, two),
      `${side}: fee ${feeLine(card.fee_dollars, card.fee_rate, two)}`,
    );
    check(card.harvested_so_far > 0 === /: \$[\d,]+ so far/.test(txt), `${side}: a harvest amount shows only above 0`);
  }
  const widths = await page
    .locator("article [aria-hidden='true'] > i[data-side]")
    .evaluateAll((els) =>
      els.map((e) => e.getBoundingClientRect().width / e.parentElement.getBoundingClientRect().width),
    );
  check(
    widths.length === 2 && Math.abs(widths[0] - c.advisor.bar) < 0.01 && Math.abs(widths[1] - 1) < 0.01,
    `wealth bars scaled by bar (${widths.map((w) => w.toFixed(3))})`,
  );

  // stacks under 900px
  await page.setViewportSize({ width: 800, height: 900 });
  const a2 = await adv.boundingBox();
  const w2 = await war.boundingBox();
  check(w2.y > a2.y + a2.height - 1, "under 900px the cards stack");
  check(
    (await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 0,
    "no sideways scrolling at 800",
  );
  await page.setViewportSize({ width: 1440, height: 900 });

  // wording, one disclaimer
  const { text, attrs, title } = await visibleText(page);
  check(text.split(DISCLAIMER).length === 2, "exactly one disclaimer");
  check(
    !/\bplans?\b|\bmodels?\b|simulat|donabach|gracchi|tanaka|\bAI\b|predict|learned|trained/i.test(
      [text, ...attrs].join("\n").replace(DISCLAIMER, ""),
    ) && title === "Waramoug",
    "no forbidden wording; title Waramoug",
  );

  // follows the plan on screen: Back, Back, job loss, Compare
  await page.getByRole("button", { name: "Back" }).click();
  await page.waitForURL("**/invest");
  await page.getByRole("button", { name: "Back" }).click();
  await page.waitForURL("**/goals");
  await page.getByRole("radio", { name: "Job loss next year" }).check();
  await page.getByRole("button", { name: "Invest", exact: true }).click();
  await page.waitForURL("**/invest");
  await page.getByRole("button", { name: "Compare" }).click();
  await page.waitForURL("**/compare");
  const jl = await planFromApi(base, {
    patch: { income_change: "job_loss" },
    event: "job_loss",
    previous: plan.plan_id,
    label: "Income: job loss next year",
  });
  check(
    (await t("wealth-waramoug")) === wealthM(jl.comparison.waramoug.wealth_80) &&
      (await t("wealth-advisor")) === wealthM(jl.comparison.advisor.wealth_80),
    "after a change both cards follow the rebuilt portfolio",
  );
  check(
    (await t("dollars-more")) === `${wealthM(jl.comparison.dollars_more)} more at 80` &&
      (await t("rate-per-year")) === `${signedPct2(jl.comparison.rate_per_year)} a year`,
    "and so does the strip",
  );
  check(issues.length === 0, `no console errors (${issues.join(" | ")})`);
  await context.close();
}

if (isMain(import.meta.url)) await runAlone(runCompare, "compare");
