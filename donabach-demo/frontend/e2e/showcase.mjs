// The showcase flow (/showcase, /showcase/strategies, /showcase/wealth), walked in a real browser.
//
// Called from walkthrough.mjs (it shares that script's `check`, helpers and browser), or on its own for a quick run:
//
//   BASE_URL=http://localhost:3000 CHROMIUM_PATH=... node e2e/showcase.mjs
//
// Every expectation is read from the API's own responses: GET /showcase (the card, the waterfall with every strategy on, the whole
// plan's wealth over time, the footer's note) and POST /showcase/analysis (the median-only waterfall for a set of strategies). The
// card's numbers, one bar per strategy with its percent and dollars, the total, what switching a strategy off does, the headline
// and the four lines are all checked against them. Nothing about the household is typed here, so any household the API serves is
// checked the same way (a strategy or goal that is not there is simply not looked for).

import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

// --- Words and numbers the way the screens write them (read from format.ts: money, signedMoney, signedPercent, count) --------------------
const trimZeros = (s) => (s.includes(".") ? s.replace(/\.?0+$/, "") : s);
const money = (value) => {
  const sign = value < 0 ? "−" : "";
  const abs = Math.abs(value);
  if (abs >= 999_500) return `${sign}$${trimZeros((abs / 1_000_000).toFixed(2))}M`;
  if (abs >= 100_000) return `${sign}$${Math.round(abs / 1_000)}k`;
  if (abs >= 1_000) return `${sign}$${trimZeros((abs / 1_000).toFixed(1))}k`;
  return `${sign}$${Math.round(abs)}`;
};
const signedMoney = (value) => (Math.abs(value) < 0.5 ? "$0" : `${value > 0 ? "+" : ""}${money(value)}`);
const exact = (value) => `${Math.round(value) < 0 ? "−" : ""}$${Math.abs(Math.round(value)).toLocaleString("en-US")}`;
const signedPercent = (fraction, digits = 2) => {
  const v = Number((fraction * 100).toFixed(digits));
  return v === 0 ? `${(0).toFixed(digits)}%` : `${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(digits)}%`;
};
// A yearly rate: two decimals, three under 0.1% a year, and "0.00%" for exactly nothing.
const ratePct = (fraction) => signedPercent(fraction, fraction === 0 ? 2 : Math.abs(fraction) < 0.001 ? 3 : 2);
const pct0 = (fraction) => `${(fraction * 100).toFixed(0)}%`;
const pct1 = (fraction) => `${Number((fraction * 100).toFixed(1))}%`;
const count = (n) => Math.round(n).toLocaleString("en-US");
const squash = (text) => text.replace(/\s+/g, " ").trim();
const list = (items) =>
  items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
const noun = (n) => `${n} ${n === 1 ? "strategy" : "strategies"}`;
const strategiesOn = (on, total) => (on === total ? `All ${noun(on)} on` : `${on} of ${noun(total)} on`);

// --- Contrast: WCAG, for the text on the showcase screens -------------------------------------------------------
/** Every visible piece of text on the page against the surface behind it: under 4.5:1 (3:1 for large text) is listed. */
async function lowContrast(page) {
  return page.evaluate(() => {
    const parse = (css) => {
      const m = css.match(/rgba?\(([^)]+)\)/);
      if (!m) return null;
      const [r, g, b, a = 1] = m[1]
        .split(/[ ,/]+/)
        .filter(Boolean)
        .map(Number);
      return { r, g, b, a };
    };
    const over = (top, under) => ({
      r: top.r * top.a + under.r * (1 - top.a),
      g: top.g * top.a + under.g * (1 - top.a),
      b: top.b * top.a + under.b * (1 - top.a),
      a: 1,
    });
    const channel = (v) => {
      const c = v / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    };
    const lum = (c) => 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
    const ratio = (a, b) => {
      const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
      return (hi + 0.05) / (lo + 0.05);
    };
    // The colour of the surface behind an element: the nearest backgrounds, laid over each other.
    const surface = (el) => {
      const layers = [];
      for (let node = el; node; node = node.parentElement) {
        const c = parse(getComputedStyle(node).backgroundColor);
        if (c && c.a > 0) {
          layers.push(c);
          if (c.a >= 1) break;
        }
      }
      return layers.reduceRight((under, layer) => over(layer, under), { r: 255, g: 255, b: 255, a: 1 });
    };
    const faded = (el) => {
      for (let node = el; node; node = node.parentElement) if (+getComputedStyle(node).opacity < 1) return true;
      return false;
    };
    const out = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const text = n.textContent.trim();
      const el = n.parentElement;
      if (!text || !el || el.closest("script,style,noscript,nextjs-portal,[hidden],.sr-only")) continue;
      const style = getComputedStyle(el);
      const box = el.getBoundingClientRect();
      if (style.visibility === "hidden" || style.display === "none" || box.width < 2 || box.height < 2 || faded(el))
        continue;
      const isSvg = el instanceof SVGElement;
      const fg = parse(isSvg ? style.fill : style.color);
      if (!fg) continue;
      const bg = surface(isSvg ? (el.closest("svg")?.parentElement ?? el) : el);
      const size = parseFloat(style.fontSize);
      const large = size >= 24 || (size >= 18.66 && +style.fontWeight >= 700);
      const r = ratio(over(fg, bg), bg);
      if (r < (large ? 3 : 4.5)) out.push(`${r.toFixed(2)}:1 "${text.slice(0, 36)}" (${size}px)`);
    }
    return [...new Set(out)].slice(0, 6);
  });
}

/**
 * Run in the page: starts watching for a loading placeholder (a panel that is aria-busy, or a "Loading ..." label in main).
 * `window.__placeholder` says whether one has been on screen since.
 */
function watchPlaceholders() {
  window.__placeholder = false;
  const look = () => {
    const main = document.querySelector("main");
    if (main && (main.querySelector('[aria-busy="true"]') || /Loading (the|wealth)/.test(main.textContent ?? "")))
      window.__placeholder = true;
  };
  new MutationObserver(look).observe(document.body, {
    subtree: true,
    childList: true,
    attributes: true,
    characterData: true,
  });
  const frame = () => {
    look();
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

/**
 * @param {object} t
 * @param {import("playwright-core").Browser} t.browser
 * @param {string} t.base the app's address
 * @param {string} t.out where screenshots go
 * @param {(ok: boolean, message: string) => void} t.check
 * @param {string[]} t.notes
 */
export async function runShowcase({ browser, base, out, check, notes }) {
  mkdirSync(out, { recursive: true });
  const api = base + "/api";
  const getJson = async (path) => (await fetch(api + path)).json();
  const postJson = async (path, body) =>
    (
      await fetch(api + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
    ).json();

  // The API's own answers: the household with its card, the waterfall with every strategy on, the whole plan's wealth over time and
  // the footer's note; and the waterfall (median only) for a set of strategies.
  const started = Date.now();
  const showcase = await getJson("/showcase");
  const seconds = ((Date.now() - started) / 1000).toFixed(1);
  const { card, waterfall: full, wealth } = showcase;
  const horizon = full.horizon_age;
  const keys = full.bars.map((b) => b.key);
  const analysisFor = (on) => postJson("/showcase/analysis", { enabled: on });
  check(
    keys.length > 0 && full.enabled.length === keys.length,
    `showcase api: GET /showcase answers with the household and ${noun(keys.length)}, all on (${seconds}s here)`,
  );
  const medianOnly = (w) =>
    typeof w.advantage?.median_rate === "number" &&
    !Object.keys(w.advantage).some((k) => k.startsWith("risk_adjusted"));
  const oneOff = keys.length > 0 ? await analysisFor(keys.slice(1)) : full;
  check(
    !("analysis" in showcase) &&
      medianOnly(full) &&
      medianOnly(oneOff) &&
      typeof wealth.advantage.risk_adjusted_rate === "number" &&
      typeof wealth.risk_adjusted_label === "string" &&
      wealth.risk_adjusted_explanation.length > 0 &&
      showcase.footer_note.length > 0,
    "showcase api: the household answer carries the waterfall (median only), the whole plan's wealth with both measures of the advantage, and the footer's note; the analysis answer is a median-only waterfall",
  );

  const newPage = async (width = 1440, scheme = "light", height = 900) => {
    const context = await browser.newContext({ viewport: { width, height }, colorScheme: scheme });
    const page = await context.newPage();
    const issues = [];
    const requests = { showcase: 0, analysis: [] };
    page.on("console", (m) => {
      if (m.type() === "error") issues.push(m.text());
    });
    page.on("pageerror", (e) => issues.push(`pageerror: ${e.message}`));
    page.on("request", (r) => {
      const { pathname } = new URL(r.url());
      if (r.method() === "GET" && pathname === "/api/showcase") requests.showcase++;
      if (r.method() === "POST" && pathname === "/api/showcase/analysis")
        requests.analysis.push(JSON.parse(r.postData() ?? "{}"));
    });
    return { context, page, issues, requests };
  };

  /** Console errors, text under 14px, horizontal overflow: the demo's checks for every screen. */
  const audit = async (page, issues, name, shot) => {
    await page.waitForTimeout(400);
    if (shot) await page.screenshot({ path: `${out}/${shot}.png`, fullPage: true });
    const result = await page.evaluate(() => {
      const small = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (!node.textContent.trim()) continue;
        const el = node.parentElement;
        if (!el || el.closest("script,style,noscript,[hidden],nextjs-portal,.sr-only")) continue;
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (
          style.visibility === "hidden" ||
          style.display === "none" ||
          +style.opacity === 0 ||
          rect.width < 2 ||
          rect.height < 2
        )
          continue;
        const size = parseFloat(style.fontSize);
        if (size < 13.99) small.push(`${size}px "${node.textContent.trim().slice(0, 40)}"`);
      }
      return {
        small: [...new Set(small)].slice(0, 6),
        overflow: document.documentElement.scrollWidth - window.innerWidth,
      };
    });
    check(issues.length === 0, `${name}: no console errors${issues.length ? ` (${issues[0]})` : ""}`);
    issues.length = 0;
    check(
      result.small.length === 0,
      `${name}: no visible text under 14px${result.small.length ? ` (${result.small.join(", ")})` : ""}`,
    );
    check(result.overflow <= 0, `${name}: no horizontal overflow (${result.overflow}px)`);
  };

  /** The footer of a showcase screen: the API's own line first, on a line of its own, then the disclaimers the other screens carry. */
  const footerLine = async (page, name) => {
    const lines = (await page.locator("footer p").allInnerTexts()).map(squash);
    check(
      lines.length >= 2 &&
        lines[0] === squash(showcase.footer_note) &&
        /^Prototype for illustration only/.test(lines[1]),
      `${name}: the footer opens with the API's own line, word for word ("${showcase.footer_note}"), ahead of the disclaimers`,
    );
  };

  // The strategies screen is the median advantage only: nothing on it, shown or folded away, speaks of the risk-adjusted one. Its
  // words are looked for in everything the page holds (the folded sentences and the live region too), and its two figures are looked for
  // unless the screen has the same text for a figure of its own.
  const riskWords = /risk[- ]adjusted|risk aversion|wealth you can count on|bad futures weigh/i;
  const ownTexts = new Set(
    full.bars.flatMap((b) => [
      `${ratePct(b.delta_rate)} a year`,
      `${ratePct(b.cumulative_rate)} a year`,
      `${signedMoney(b.delta_dollars)} at ${horizon}`,
      `${signedMoney(b.cumulative_dollars)} at ${horizon}`,
    ]),
  );
  const riskFigures = [
    `${ratePct(wealth.advantage.risk_adjusted_rate)} a year`,
    `${signedMoney(wealth.advantage.risk_adjusted_dollars)} at ${horizon}`,
  ].filter((figure) => !ownTexts.has(figure) && figure !== `${ratePct(full.advantage.median_rate)} a year`);
  const withoutRiskAdjusted = async (page) => {
    const text = squash(
      await page.evaluate(
        () =>
          `${document.querySelector("main")?.textContent ?? ""} ${document.querySelector("footer")?.textContent ?? ""}`,
      ),
    );
    return (
      !riskWords.test(text) &&
      !text.includes(squash(wealth.risk_adjusted_explanation)) &&
      !text.includes(wealth.risk_adjusted_label) &&
      riskFigures.every((figure) => !text.includes(figure))
    );
  };

  const settled = (page) =>
    page.waitForFunction(
      () =>
        document.querySelector('[data-stale="true"]') === null && document.querySelector("[aria-busy='true']") === null,
      null,
      {
        timeout: 60000,
      },
    );
  const settleLines = (page, n) =>
    page
      .waitForFunction(
        (want) => {
          const lines = [...document.querySelectorAll("path.recharts-line-curve")];
          return (
            lines.length === want && lines.every((l) => !(l.getAttribute("stroke-dasharray") ?? "").includes("px"))
          );
        },
        n,
        { timeout: 10000 },
      )
      .catch(() => notes.push("showcase: the chart lines were still animating at the check"));

  // === The home page leads in, and asks for the household before the link is followed ====================================
  {
    const { context, page, issues, requests } = await newPage();
    await page.goto(base + "/", { waitUntil: "networkidle" });
    const entry = page.getByRole("link", { name: /Open the showcase/ });
    await entry.waitFor({ timeout: 20000 });
    check(
      (await entry.getAttribute("href")) === "/showcase",
      "showcase entry: the home page has a clear link, 'Open the showcase', that goes to /showcase",
    );
    check(
      requests.showcase === 1,
      `showcase entry: the household is asked for as soon as the link is on the home page, before anyone clicks (${requests.showcase} request)`,
    );
    await entry.hover();
    await entry.focus();
    await page.waitForTimeout(300);
    check(
      requests.showcase === 1,
      `showcase entry: hovering and focusing the link do not ask again while the answer is fresh (${requests.showcase} request)`,
    );
    const asksDark = await newPage(1440, "dark");
    await asksDark.page.goto(base + "/", { waitUntil: "networkidle" });
    const homeBackground = await asksDark.page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    check(
      homeBackground === "rgb(251, 247, 238)",
      `light theme only: the home page stays light when the system asks for dark (background ${homeBackground})`,
    );
    await asksDark.context.close();
    await audit(page, issues, "home with the showcase link");
    // Followed after the answer is in: the household card draws at once, with no placeholder and no second request.
    await page.evaluate(watchPlaceholders);
    const clicked = Date.now();
    await entry.click();
    await page.waitForURL("**/showcase");
    await page.locator("article").first().waitFor({ timeout: 5000 });
    const sinceClick = Date.now() - clicked;
    const placeholder = await page.evaluate(() => window.__placeholder);
    check(
      !placeholder && requests.showcase === 1 && sinceClick < 1000,
      `showcase entry: following the link opens the household card in ${sinceClick} ms with no loading placeholder and no second request`,
    );
    await context.close();
  }

  // Followed before the household has arrived: the first screen waits for that same request (never a second one), then shows it.
  {
    const { context, page, requests } = await newPage();
    let release;
    const held = new Promise((r) => (release = r));
    await page.route("**/api/showcase", async (route) => {
      await held;
      await route.fallback();
    });
    const asked = page.waitForRequest((r) => new URL(r.url()).pathname === "/api/showcase" && r.method() === "GET");
    await page.goto(base + "/", { waitUntil: "domcontentloaded" });
    await asked;
    await page.getByRole("link", { name: /Open the showcase/ }).click();
    await page.waitForURL("**/showcase");
    await page.getByText("Loading the household").waitFor({ timeout: 10000 });
    release();
    await page.locator("article").first().waitFor({ timeout: 90000 });
    check(
      requests.showcase === 1 && (await page.getByRole("heading", { level: 1 }).innerText()) === showcase.name,
      "showcase entry: followed before the household has arrived, the first screen waits for that same request (no second one) and then shows the household",
    );
    await context.close();
  }

  // The request is made again when the link is hovered or focused if the first one never produced an answer.
  {
    const { context, page, requests } = await newPage();
    let calls = 0;
    await page.route("**/api/showcase", (route) => {
      calls++;
      return calls === 1
        ? route.fulfill({
            status: 500,
            contentType: "application/json",
            body: JSON.stringify({ detail: "the e2e made this error up" }),
          })
        : route.fallback();
    });
    await page.goto(base + "/", { waitUntil: "networkidle" });
    const entry = page.getByRole("link", { name: /Open the showcase/ });
    await entry.waitFor({ timeout: 20000 });
    const first = requests.showcase;
    const second = page.waitForRequest((r) => new URL(r.url()).pathname === "/api/showcase" && r.method() === "GET");
    await Promise.all([second, entry.hover()]);
    await page.waitForLoadState("networkidle");
    await page.evaluate(watchPlaceholders);
    await entry.click();
    await page.waitForURL("**/showcase");
    await page.locator("article").first().waitFor({ timeout: 5000 });
    check(
      first === 1 &&
        requests.showcase === 2 &&
        !(await page.evaluate(() => window.__placeholder)) &&
        (await page.locator("main").innerText()).includes(showcase.name),
      "showcase entry: if the first request failed, hovering the link asks again, and the flow then opens with the household in hand",
    );
    await context.close();
  }

  // === Screen 1: the household card ======================================================================================
  {
    const { context, page, issues, requests } = await newPage();
    await page.goto(base + "/showcase", { waitUntil: "networkidle" });
    await page.getByRole("heading", { level: 1 }).waitFor({ timeout: 90000 });
    const body = squash(await page.locator("main").innerText());
    check(
      squash(await page.getByRole("heading", { level: 1 }).innerText()) === showcase.name &&
        body.includes(showcase.type_label) &&
        body.includes(showcase.tagline),
      `showcase household: the title block is the API's name, type label and tagline ("${showcase.name}")`,
    );

    // The header: three steps, in place of the demo's seven, and the brand still leads home.
    const nav = page.getByRole("navigation", { name: "Showcase progress" });
    const steps = (await nav.locator("li").allInnerTexts()).map(squash);
    check(
      JSON.stringify(steps) === JSON.stringify(["1 Household", "2 Strategies", "3 Wealth"]) &&
        (await nav.locator('[aria-current="step"]').innerText()).includes("Household") &&
        (await page.getByRole("navigation", { name: "Progress", exact: true }).count()) === 0 &&
        (await page.getByRole("link", { name: "Donabach home" }).getAttribute("href")) === "/",
      "showcase header: a three-step navigation (Household, Strategies, Wealth) with this step marked, instead of the seven steps; the brand links home",
    );

    // People, children, income and savings.
    const cardText = squash(await page.locator('article[aria-label="Household summary"]').innerText());
    const kids = card.children_ages;
    const kidsText =
      kids.length === 0
        ? "No children"
        : kids.length === 1
          ? `1 child, age ${kids[0]}`
          : `${kids.length} children, ages ${list(kids)}`;
    check(
      card.people.every(
        (p) =>
          cardText.includes(p.label) &&
          cardText.includes(`Age ${p.age}`) &&
          cardText.includes(`${exact(p.wages)} a year in wages`),
      ) && cardText.includes(kidsText),
      `showcase household: ${card.people.length === 1 ? "the earner" : `all ${card.people.length} earners`} with age and wages, and the children (${kidsText}), are the API's`,
    );
    check(
      cardText.includes(`Household income ${exact(card.annual_income)} a year`) &&
        cardText.includes(`Total saved ${exact(card.total_savings)}`),
      `showcase household: annual income (${exact(card.annual_income)}) and total saved (${exact(card.total_savings)}) are the API's`,
    );

    // Where the savings are: a segment for each account with something in it, a legend with every account's dollars and share, the taxable callout.
    const legend = (
      await page
        .getByRole("list", { name: /Savings by account/ })
        .locator("li")
        .allInnerTexts()
    ).map(squash);
    check(
      legend.length === card.accounts.length &&
        card.accounts.every(
          (a, i) =>
            legend[i].includes(a.label) &&
            legend[i].includes(exact(a.value)) &&
            legend[i].includes(`${pct0(a.share)} of savings`),
        ),
      `showcase household: the legend lists all ${card.accounts.length} accounts in the API's order with dollars and share (${card.accounts.map((a) => `${a.key} ${exact(a.value)}`).join(", ")})`,
    );
    const segments = await page
      .locator('section[aria-labelledby="card-savings"] div[aria-hidden="true"] span[data-account]')
      .evaluateAll((els) =>
        els.map((el) => ({ key: el.getAttribute("data-account"), grow: parseFloat(el.style.flexGrow) })),
      );
    const drawn = card.accounts.filter((a) => a.share > 0);
    check(
      segments.length === drawn.length &&
        drawn.every((a, i) => segments[i].key === a.key && Math.abs(segments[i].grow - a.share) < 1e-5),
      `showcase household: the savings bar has a segment for each account with money in it, as wide as its share (${drawn.map((a) => `${a.key} ${pct0(a.share)}`).join(", ")})`,
    );
    const taxable = card.accounts.find((a) => a.key === "taxable");
    const callout = page.locator('section[aria-labelledby="card-savings"] p[data-account="taxable"]');
    if (taxable && (taxable.value > 0 || (taxable.basis ?? 0) > 0)) {
      const text = squash(await callout.innerText());
      check(
        text.includes(`Cost basis ${exact(taxable.basis)}`) &&
          (taxable.unrealized_gain > 0
            ? text.includes(`Unrealized gain ${exact(taxable.unrealized_gain)}`)
            : text.includes("No unrealized gain")),
        `showcase household: the taxable account's basis (${exact(taxable.basis)}) and unrealized gain (${exact(taxable.unrealized_gain)}) are called out`,
      );
    } else {
      check(
        (await callout.count()) === 0,
        "showcase household: with no taxable account there is no basis and gain callout",
      );
    }

    // What they are saving for: a marker on the line for each goal, in order of date, and every goal's detail sentence.
    const goalItems = (await page.locator('section[aria-labelledby="card-goals"] ol > li').allInnerTexts()).map(squash);
    const dated = card.goals
      .filter((g) => typeof g.years_from_now === "number")
      .sort((a, b) => a.years_from_now - b.years_from_now);
    const startAge = card.people[0].age;
    check(
      goalItems.length === dated.length &&
        dated.every(
          (g, i) =>
            goalItems[i].includes(g.label) &&
            goalItems[i].includes(g.detail) &&
            goalItems[i].includes(`Age ${startAge + g.years_from_now}`),
        ),
      `showcase household: the goals are on a timeline in the order they happen, each with its age and the API's detail (${dated.map((g) => `${g.label} at ${startAge + g.years_from_now}`).join(", ")})`,
    );
    const marks = await page
      .locator("section[aria-labelledby=card-goals] [data-goal]:not(li)")
      .evaluateAll((els) => els.map((el) => ({ key: el.getAttribute("data-goal"), left: parseFloat(el.style.left) })));
    const span = Math.max(1, horizon - startAge);
    check(
      marks.length === dated.length &&
        dated.every(
          (g, i) =>
            marks[i].key === g.key && Math.abs(marks[i].left - Math.min(1, g.years_from_now / span) * 100) < 0.01,
        ),
      `showcase household: each goal's marker sits where it falls between today (age ${startAge}) and age ${horizon}`,
    );
    const ends = squash(await page.locator('section[aria-labelledby="card-goals"]').innerText());
    check(
      ends.includes(`Today, age ${startAge}`) && ends.includes(`Age ${horizon}`),
      `showcase household: the timeline runs from today (age ${startAge}) to the horizon (age ${horizon})`,
    );

    // What stands out: exactly the API's notes.
    const notesOnScreen = (await page.locator('section[aria-labelledby="card-notes"] li').allInnerTexts()).map(squash);
    check(
      JSON.stringify(notesOnScreen) === JSON.stringify(card.notes.map(squash)) &&
        (card.notes.length > 0 || (await page.locator("#card-notes").count()) === 0),
      `showcase household: "What stands out" lists the API's ${card.notes.length} note${card.notes.length === 1 ? "" : "s"}${card.notes.length === 0 ? " (none, so no section)" : ""}`,
    );
    check(
      (await page.getByRole("link", { name: /Back to the demo home/ }).getAttribute("href")) === "/",
      "showcase household: a back link goes to the demo's home",
    );
    const next = page.getByRole("link", { name: /See the strategies/ });
    check(
      (await next.getAttribute("href")) === "/showcase/strategies",
      "showcase household: the primary button goes on to the strategies",
    );
    await audit(page, issues, "showcase 1 household", "showcase-1-household");

    await footerLine(page, "showcase household");
    const weak = await lowContrast(page);
    check(
      weak.length === 0,
      `showcase household (light): all text has enough contrast${weak.length ? ` (${weak.join("; ")})` : ""}`,
    );

    // Moving on keeps the household (it is loaded once for the whole flow).
    await next.click();
    await page.waitForURL("**/showcase/strategies");
    await page
      .locator(keys.length > 0 ? "li[data-key]" : "main h1")
      .first()
      .waitFor({ timeout: 30000 });
    check(
      requests.showcase === 1,
      `showcase flow: the household is asked of the API once for the whole flow (${requests.showcase} request)`,
    );
    await context.close();
  }

  // === The three screens at a phone's width, a tablet's and a desktop's =================================================
  const screens = [
    ["/showcase", "household", "article"],
    ["/showcase/strategies", "strategies", keys.length > 0 ? "li[data-key]" : "main h1"],
    ["/showcase/wealth", "wealth", ".recharts-wrapper"],
  ];
  for (const [path, label, waitFor] of screens) {
    for (const width of [390, 768, 1280]) {
      const { context, page, issues } = await newPage(width);
      await page.goto(base + path, { waitUntil: "networkidle" });
      await page.locator(waitFor).first().waitFor({ timeout: 90000 });
      await page.waitForTimeout(label === "wealth" ? 2500 : 600);
      const name = `showcase ${label} at ${width}px`;
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      check(overflow <= 0, `${name}: no horizontal overflow (${overflow}px)`);
      const spill = await page.evaluate(() => {
        // Nothing may reach past the panel it sits in (things inside a scrolling table are clipped on purpose).
        const out = [];
        for (const panel of document.querySelectorAll("main section, main article, main aside")) {
          const box = panel.getBoundingClientRect();
          for (const el of panel.querySelectorAll("*")) {
            if (el.closest(".sr-only,[hidden],table,svg,[data-track]") || !el.getBoundingClientRect().width) continue;
            const r = el.getBoundingClientRect();
            if (r.right > box.right + 1 || r.left < box.left - 1)
              out.push(`${el.tagName.toLowerCase()} "${(el.textContent ?? "").trim().slice(0, 24)}"`);
          }
        }
        return [...new Set(out)].slice(0, 4);
      });
      check(
        spill.length === 0,
        `${name}: nothing spills out of its panel${spill.length ? ` (${spill.join(", ")})` : ""}`,
      );
      if (width !== 768) {
        const weak = await lowContrast(page);
        check(weak.length === 0, `${name}: all text has enough contrast${weak.length ? ` (${weak.join("; ")})` : ""}`);
      }
      check(issues.length === 0, `${name}: no console errors${issues.length ? ` (${issues[0]})` : ""}`);
      if (width !== 768) await page.screenshot({ path: `${out}/showcase-${label}-${width}.png`, fullPage: true });
      await context.close();
    }
  }

  // === The flow is light, whatever the system asks for ===================================================================
  /** What makes a page light: the colour scheme it declares, its page and text colours and the design tokens' values. */
  const lightFacts = (page) =>
    page.evaluate(() => {
      const root = getComputedStyle(document.documentElement);
      const body = getComputedStyle(document.body);
      const tokens = [
        "--cream",
        "--panel",
        "--espresso",
        "--brown",
        "--gold",
        "--muted-text",
        "--line",
        "--series-donabach",
        "--series-ria",
      ].map((token) => root.getPropertyValue(token).trim());
      return {
        asksDark: matchMedia("(prefers-color-scheme: dark)").matches,
        scheme: root.colorScheme,
        background: body.backgroundColor,
        text: body.color,
        tokens,
      };
    });
  for (const [path, label, waitFor] of screens) {
    const dark = await newPage(1280, "dark");
    await dark.page.goto(base + path, { waitUntil: "networkidle" });
    await dark.page.locator(waitFor).first().waitFor({ timeout: 90000 });
    await dark.page.waitForTimeout(label === "wealth" ? 2500 : 600);
    const asked = await lightFacts(dark.page);
    const plain = await newPage(1280, "light");
    await plain.page.goto(base + path, { waitUntil: "networkidle" });
    await plain.page.locator(waitFor).first().waitFor({ timeout: 90000 });
    const normal = await lightFacts(plain.page);
    check(
      asked.asksDark &&
        !normal.asksDark &&
        asked.scheme === "light" &&
        asked.background === "rgb(251, 247, 238)" &&
        JSON.stringify({ ...asked, asksDark: null }) === JSON.stringify({ ...normal, asksDark: null }),
      `light theme only: the ${label} screen stays light when the system asks for dark (colour scheme ${asked.scheme}, background ${asked.background}, the same colours and tokens as with a light setting)`,
    );
    const weak = await lowContrast(dark.page);
    check(
      weak.length === 0 && dark.issues.length === 0,
      `light theme only: the ${label} screen's text is as legible when the system asks for dark${weak.length ? ` (${weak.join("; ")})` : ""}${dark.issues.length ? ` (${dark.issues[0]})` : ""}`,
    );
    await dark.context.close();
    await plain.context.close();
  }

  // === Screen 2: the waterfall ==========================================================================================
  if (keys.length > 0) {
    const { context, page, issues, requests } = await newPage();
    await page.goto(base + "/showcase/strategies", { waitUntil: "networkidle" });
    await page.locator("li[data-key]").first().waitFor({ timeout: 90000 });
    await page.waitForTimeout(500);
    const rows = page.locator('ol[aria-label^="What each strategy adds"] > li');
    const advantage = full.advantage;
    const advisor = full.advisor_label;

    // One bar for each strategy, in the API's order, between the advisor's result and Donabach's.
    const kinds = await rows.evaluateAll((els) =>
      els.map((el) => `${el.getAttribute("data-kind")}:${el.getAttribute("data-key")}`),
    );
    check(
      JSON.stringify(kinds) === JSON.stringify(["start:start", ...keys.map((k) => `strategy:${k}`), "total:total"]),
      `showcase waterfall: the advisor's result, then one row for each of the ${keys.length} strategies in the API's order, then the total (${keys.join(", ")})`,
    );

    // Every row shows both the percent a year and the dollars at the horizon, whichever one the bar's length shows.
    const rowByKey = (key) => page.locator(`ol[aria-label^="What each strategy adds"] > li[data-key="${key}"]`);
    let bothLabels = true;
    for (const bar of full.bars) {
      const text = squash(await rowByKey(bar.key).innerText());
      bothLabels &&=
        text.includes(`${signedMoney(bar.delta_dollars)} at ${horizon}`) &&
        text.includes(`${ratePct(bar.delta_rate)} a year`) &&
        text.includes(bar.label);
    }
    check(
      bothLabels,
      `showcase waterfall: each strategy's row shows its percent a year and its dollars at ${horizon}, both from the API (${full.bars
        .slice(0, 2)
        .map((b) => `${b.label}: ${ratePct(b.delta_rate)} a year, ${signedMoney(b.delta_dollars)}`)
        .join("; ")}...)`,
    );
    const totalRow = squash(await rowByKey("total").innerText());
    check(
      totalRow.includes(`${signedMoney(advantage.median_dollars)} at ${horizon}`) &&
        totalRow.includes(`${ratePct(advantage.median_rate)} a year`) &&
        totalRow.includes(`Median ${money(advantage.plan_median_at_horizon)} at ${horizon}`),
      `showcase waterfall: the last row is Donabach's total, ${ratePct(advantage.median_rate)} a year and ${signedMoney(advantage.median_dollars)} at ${horizon}, as the API has it`,
    );
    const startRow = squash(await rowByKey("start").innerText());
    check(
      startRow.includes(advisor) &&
        startRow.includes(`Median ${money(advantage.advisor_median_at_horizon)} at ${horizon}`) &&
        startRow.includes("0 = the advisor's result"),
      `showcase waterfall: the first row is the ${advisor.toLowerCase()}'s result, the zero everything is measured from (median ${money(advantage.advisor_median_at_horizon)})`,
    );
    const barSum = full.bars.reduce((s, b) => s + b.delta_dollars, 0);
    check(
      Math.abs(barSum - advantage.median_dollars) < 1,
      `showcase waterfall: the API's bars add up to the headline (${signedMoney(barSum)} against ${signedMoney(advantage.median_dollars)})`,
    );

    // The total, in large type, with the advisor's and Donabach's medians and what they are measured on.
    const totalPanel = squash(await page.locator('section[aria-labelledby="total-title"]').innerText());
    check(
      totalPanel.includes(`${ratePct(advantage.median_rate)} a year`) &&
        totalPanel.includes(`${signedMoney(advantage.median_dollars)} at ${horizon}`) &&
        totalPanel.includes(`Median of ${count(full.n_paths)} simulated futures`) &&
        totalPanel.includes(`${advisor} ${money(advantage.advisor_median_at_horizon)}`) &&
        totalPanel.includes(`Donabach ${money(advantage.plan_median_at_horizon)}`),
      `showcase waterfall: the total reads "${ratePct(advantage.median_rate)} a year, ${signedMoney(advantage.median_dollars)} at ${horizon}, median of ${count(full.n_paths)} simulated futures", with the two medians (${money(advantage.advisor_median_at_horizon)} and ${money(advantage.plan_median_at_horizon)})`,
    );

    // A switch for every strategy, labelled with its name, all on; what a strategy does is there on demand and read out with the switch.
    let switches = true;
    for (const bar of full.bars) {
      const s = page.getByRole("switch", { name: bar.label, exact: true });
      switches &&= (await s.count()) === 1 && (await s.isChecked());
    }
    check(switches, `showcase waterfall: every strategy has a switch labelled with its name, all ${keys.length} on`);
    check(
      await withoutRiskAdjusted(page),
      `showcase waterfall: the median advantage only: no risk-adjusted word or figure (${riskFigures.join(", ") || "none that differs from its own"}) anywhere on the screen`,
    );
    const probe = full.bars[0];
    const info = page.getByRole("button", { name: `What “${probe.label}” does` });
    const detailId = await info.getAttribute("aria-controls");
    check(
      (await info.getAttribute("aria-expanded")) === "false" && !(await page.locator(`[id="${detailId}"]`).isVisible()),
      `showcase waterfall: what "${probe.label}" does is folded away until asked for`,
    );
    await info.click();
    const detailText = squash(await page.locator(`[id="${detailId}"]`).innerText());
    const describedBy = await page
      .getByRole("switch", { name: probe.label, exact: true })
      .getAttribute("aria-describedby");
    check(
      (await info.getAttribute("aria-expanded")) === "true" &&
        detailText === squash(probe.detail) &&
        describedBy === detailId,
      `showcase waterfall: it opens to the API's own sentence ("${probe.detail.slice(0, 48)}..."), which is also the switch's description`,
    );
    await info.click();
    await page.getByRole("button", { name: /Explain each strategy/ }).click();
    const allDetails = (
      await page
        .locator("li[data-kind=strategy] p[id]")
        .evaluateAll((els) => els.map((el) => ({ shown: !el.hidden, text: el.textContent })))
    ).map((d) => ({ ...d, text: squash(d.text) }));
    check(
      allDetails.length === keys.length &&
        allDetails.every((d, i) => d.shown && d.text === squash(full.bars[i].detail)),
      "showcase waterfall: 'Explain each strategy' shows every strategy's sentence at once",
    );
    await page.getByRole("button", { name: /Hide the explanations/ }).click();

    // What the bars' length shows: a segmented control; the geometry follows it and both labels stay.
    const widthOf = (key) =>
      page.locator(`li[data-key="${key}"] [data-track] > span[data-kind]`).evaluate((el) => parseFloat(el.style.width));
    const radios = page.getByRole("radiogroup", { name: "What the length of a bar shows" });
    check(
      (await radios.getByRole("radio").count()) === 2 &&
        (await radios.getByRole("radio", { name: `Dollars at ${horizon}` }).isChecked()),
      `showcase waterfall: a segmented control chooses what the bars' length shows (dollars at ${horizon}, percent a year), dollars to begin with`,
    );
    const [first, second] = [
      full.bars.find((b) => b.delta_dollars > 0 && b.delta_rate > 0),
      full.bars.filter((b) => b.delta_dollars > 0 && b.delta_rate > 0)[1],
    ];
    if (first && second) {
      const dollarsRatio = (await widthOf(first.key)) / (await widthOf(second.key));
      check(
        Math.abs(dollarsRatio / (first.delta_dollars / second.delta_dollars) - 1) < 0.02,
        `showcase waterfall: in dollars two bars are as long as their dollars (${first.label} against ${second.label}: ${dollarsRatio.toFixed(2)} for ${(first.delta_dollars / second.delta_dollars).toFixed(2)})`,
      );
      await radios.getByRole("radio", { name: "Percent a year" }).check();
      await page.waitForTimeout(900);
      const rateRatio = (await widthOf(first.key)) / (await widthOf(second.key));
      const afterText = squash(await rowByKey(first.key).innerText());
      check(
        Math.abs(rateRatio / (first.delta_rate / second.delta_rate) - 1) < 0.02 &&
          afterText.includes(`${signedMoney(first.delta_dollars)} at ${horizon}`) &&
          afterText.includes(`${ratePct(first.delta_rate)} a year`),
        `showcase waterfall: in percent a year the same bars are as long as their rates (${rateRatio.toFixed(2)} for ${(first.delta_rate / second.delta_rate).toFixed(2)}), and both labels are still on every row`,
      );
      await radios.getByRole("radio", { name: `Dollars at ${horizon}` }).check();
    } else {
      notes.push(
        "showcase waterfall: fewer than two strategies add anything here, so the bar lengths were not compared across the two units",
      );
    }

    // The chart's table twin: every number, row by row, with the running total.
    await page.getByRole("button", { name: "View as table" }).click();
    const table = page.getByRole("table", { name: /What each strategy adds to median after-tax wealth/ });
    await table.waitFor();
    const tableRows = (await table.locator("tbody tr").allInnerTexts()).map(squash);
    check(
      tableRows.length === keys.length + 2 &&
        full.bars.every(
          (b, i) =>
            tableRows[i + 1].includes(b.label) &&
            tableRows[i + 1].includes(signedMoney(b.delta_dollars)) &&
            tableRows[i + 1].includes(ratePct(b.delta_rate)) &&
            tableRows[i + 1].includes(signedMoney(b.cumulative_dollars)) &&
            tableRows[i + 1].includes(ratePct(b.cumulative_rate)),
        ) &&
        tableRows[tableRows.length - 1].includes(signedMoney(advantage.median_dollars)),
      `showcase waterfall: the table twin has a row for the advisor, each of the ${keys.length} strategies and the total, with each change and running total as the API has them`,
    );
    check(
      await withoutRiskAdjusted(page),
      "showcase waterfall: nor does the table twin, the explanations or the plan in words (folded text included)",
    );
    await page.getByRole("button", { name: "View as chart" }).click();

    // Switching one off: the API is asked for the new set, the whole waterfall and the total are the API's answer for it.
    if (keys.length >= 1) {
      const off = full.bars[Math.min(1, keys.length - 1)];
      const onSet = keys.filter((k) => k !== off.key);
      const expected = await analysisFor(onSet);
      const live = page.locator("p[role=status]");
      check(
        (await live.count()) === 1,
        "showcase waterfall: a live region (aria-live polite) is there to announce the recomputed total",
      );
      // Hold the answer back a moment, to see the state while it is worked out.
      let release;
      const held = new Promise((r) => (release = r));
      await page.route("**/api/showcase/analysis", async (route) => {
        await held;
        await route.fallback();
      });
      const before = squash(await page.locator('section[aria-labelledby="total-title"]').innerText());
      const beforeCount = requests.analysis.length;
      await page.getByRole("switch", { name: off.label, exact: true }).click();
      await page.waitForFunction(() => document.querySelector('[data-stale="true"]') !== null, null, { timeout: 5000 });
      const during = squash(await page.locator('section[aria-labelledby="total-title"]').innerText());
      check(
        (await page.getByRole("switch", { name: off.label, exact: true }).isChecked()) === false &&
          during === before &&
          /Recomputing/.test(await page.locator("main").innerText()) &&
          (await live.innerText()).includes("Recomputing"),
        "showcase waterfall: switching a strategy off moves its switch at once, keeps the previous bars and total on screen, says it is recomputing, and announces it",
      );
      await page.waitForTimeout(400);
      const dimmedNow = await page.evaluate(
        () => +getComputedStyle(document.querySelector('li[data-kind="strategy"] [data-track]')).opacity,
      );
      check(
        dimmedNow < 1,
        `showcase waterfall: while it recomputes the previous bars are dimmed (opacity ${dimmedNow})`,
      );
      release();
      await settled(page);
      await page.unroute("**/api/showcase/analysis");
      check(
        requests.analysis.length === beforeCount + 1 &&
          JSON.stringify(requests.analysis.at(-1)) === JSON.stringify({ enabled: onSet }),
        `showcase waterfall: exactly one request went out, asking for the other ${onSet.length} strategies on (${JSON.stringify(requests.analysis.at(-1))})`,
      );
      const after = squash(await page.locator('section[aria-labelledby="total-title"]').innerText());
      const eh = expected.advantage;
      check(
        after.includes(`${ratePct(eh.median_rate)} a year`) &&
          after.includes(`${signedMoney(eh.median_dollars)} at ${horizon}`) &&
          after.includes(strategiesOn(onSet.length, keys.length)) &&
          after.includes(`Donabach ${money(eh.plan_median_at_horizon)}`),
        `showcase waterfall: the total is the API's for that set (${ratePct(eh.median_rate)} a year, ${signedMoney(eh.median_dollars)} at ${horizon}, Donabach ${money(eh.plan_median_at_horizon)}), not the old one`,
      );
      let barsOk = true;
      for (const bar of expected.bars) {
        const text = squash(await rowByKey(bar.key).innerText());
        barsOk &&=
          text.includes(`${signedMoney(bar.delta_dollars)} at ${horizon}`) &&
          text.includes(`${ratePct(bar.delta_rate)} a year`);
      }
      check(
        barsOk,
        "showcase waterfall: every bar was measured again: each row shows the API's numbers for the new set",
      );
      // A strategy that is on but changes nothing given the ones before it says so (and no other row does).
      const idleKeys = expected.bars
        .filter((b) => b.enabled && b.delta_dollars === 0 && b.delta_rate === 0)
        .map((b) => b.key);
      let idleNotes = true;
      for (const bar of expected.bars) {
        const text = squash(await rowByKey(bar.key).innerText());
        idleNotes &&= text.includes("On, but it adds nothing here") === idleKeys.includes(bar.key);
      }
      check(
        idleNotes,
        idleKeys.length
          ? `showcase waterfall: a strategy that is on but adds nothing with the others off says so (${idleKeys.join(", ")}), and no other row does`
          : "showcase waterfall: no strategy that is on changes nothing in this set, so no row carries the 'adds nothing' note",
      );
      await page.waitForTimeout(1000); // the bars glide to their new places over 700ms
      const ghost = await page.locator(`li[data-key="${off.key}"] [data-track] > span[data-kind]`).evaluate((el) => {
        const s = getComputedStyle(el);
        return {
          off: el.getAttribute("data-off"),
          border: s.borderTopStyle,
          fill: s.backgroundColor,
          width: el.getBoundingClientRect().width,
        };
      });
      const offText = squash(await rowByKey(off.key).innerText());
      check(
        ghost.off === "true" &&
          ghost.border === "dashed" &&
          /rgba\(0, 0, 0, 0\)|transparent/.test(ghost.fill) &&
          ghost.width > 8 &&
          offText.includes("0.00% a year") &&
          offText.includes("$0 at"),
        `showcase waterfall: "${off.label}", switched off, is an empty dashed-outline bar with 0 (0.00% a year, $0 at ${horizon})`,
      );
      const said = await live.innerText();
      check(
        said.includes(`Recomputed: ${strategiesOn(onSet.length, keys.length)}`) &&
          said.includes(`${ratePct(eh.median_rate)} a year`) &&
          said.includes(`${signedMoney(eh.median_dollars)} at ${horizon}`) &&
          said.includes(`median of ${count(expected.n_paths)} simulated futures`),
        "showcase waterfall: the recomputed total is announced to screen readers (aria-live), with the strategies on, the yearly rate, the dollars and the number of futures",
      );
      check(
        await page.getByRole("button", { name: "Switch every strategy on" }).isVisible(),
        "showcase waterfall: with a strategy off, a button puts every strategy back on",
      );

      // Back on: the answer it already has is used at once (no new request), and the numbers are the first ones again.
      const asked = requests.analysis.length;
      await page.getByRole("switch", { name: off.label, exact: true }).click();
      await page.waitForTimeout(600);
      const restored = squash(await page.locator('section[aria-labelledby="total-title"]').innerText());
      check(
        requests.analysis.length === asked &&
          restored.includes(`${ratePct(advantage.median_rate)} a year`) &&
          restored.includes(`${signedMoney(advantage.median_dollars)} at ${horizon}`),
        "showcase waterfall: switching it back on shows the first numbers again, from the answer already held (no new request)",
      );
    }

    // Two changes in quick succession: the first answer, held back, must not win over the second.
    if (keys.length >= 2) {
      const [a, b] = [full.bars[0], full.bars[1]];
      const expectedBoth = await analysisFor(keys.filter((k) => k !== a.key && k !== b.key));
      let lateFirst;
      const heldFirst = new Promise((r) => (lateFirst = r));
      let calls = 0;
      await page.route("**/api/showcase/analysis", async (route) => {
        calls++;
        if (calls === 1) {
          await heldFirst; // the first change's answer is slow
          await route.fallback().catch(() => {});
        } else await route.fallback();
      });
      await page.getByRole("switch", { name: a.label, exact: true }).click();
      await page.getByRole("switch", { name: b.label, exact: true }).click();
      await page.waitForFunction(() => document.querySelector('[data-stale="true"]') === null, null, {
        timeout: 30000,
      });
      lateFirst(); // now the stale answer arrives
      await page.waitForTimeout(800);
      const finalText = squash(await page.locator('section[aria-labelledby="total-title"]').innerText());
      check(
        finalText.includes(`${ratePct(expectedBoth.advantage.median_rate)} a year`) &&
          finalText.includes(`${signedMoney(expectedBoth.advantage.median_dollars)} at ${horizon}`) &&
          !(await page.getByRole("switch", { name: a.label, exact: true }).isChecked()) &&
          !(await page.getByRole("switch", { name: b.label, exact: true }).isChecked()),
        `showcase waterfall: two quick changes (${a.label}, then ${b.label}): the numbers are the API's for both off, and an older answer that arrives late is ignored`,
      );
      await page.unroute("**/api/showcase/analysis");
      await page.getByRole("button", { name: "Switch every strategy on" }).click();
      await settled(page);
    }

    // The API refuses: its message is shown, the switches go back to what the numbers are for.
    {
      const message = "unknown strategies ['e2e']; expected some of []";
      await page.route("**/api/showcase/analysis", (route) =>
        route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: message }) }),
      );
      const target = full.bars[keys.length - 1];
      const beforeError = squash(await page.locator('section[aria-labelledby="total-title"]').innerText());
      await page.getByRole("switch", { name: target.label, exact: true }).click();
      const alert = page.getByRole("alert").filter({ hasText: "could not be applied" });
      await alert.waitFor({ timeout: 10000 });
      await page.waitForTimeout(300);
      check(
        (await alert.innerText()).includes(message) &&
          (await page.getByRole("switch", { name: target.label, exact: true }).isChecked()) &&
          squash(await page.locator('section[aria-labelledby="total-title"]').innerText()) === beforeError,
        "showcase waterfall: when the API refuses a change its own message is shown, the switch goes back and the numbers on screen stay as they were",
      );
      await page.unroute("**/api/showcase/analysis");
      await alert.getByRole("button", { name: "Dismiss" }).click();
      check(
        (await page.getByRole("alert").filter({ hasText: "could not be applied" }).count()) === 0,
        "showcase waterfall: the message can be dismissed",
      );
      issues.length = 0; // the browser logged the 422 this test made up as a console error: it is not one of the page's
    }

    // The keyboard does all of it: Tab to a switch, Space flips it.
    if (keys.length >= 1) {
      const last = full.bars[keys.length - 1];
      const s = page.getByRole("switch", { name: last.label, exact: true });
      await s.focus();
      await page.keyboard.press("Space");
      check((await s.isChecked()) === false, "showcase waterfall: a switch answers the keyboard (Space flips it)");
      const outline = await s.evaluate((el) => getComputedStyle(el.nextElementSibling).outlineStyle);
      await settled(page);
      check(outline === "solid", "showcase waterfall: the focused switch shows a focus ring");
      await page.keyboard.press("Space");
      await settled(page);
    }

    const weak = await lowContrast(page);
    check(
      weak.length === 0,
      `showcase waterfall (light): all text has enough contrast${weak.length ? ` (${weak.join("; ")})` : ""}`,
    );
    await footerLine(page, "showcase waterfall");
    await audit(page, issues, "showcase 2 strategies", "showcase-2-strategies");
    check(
      (await page.getByRole("link", { name: /Back to the household/ }).getAttribute("href")) === "/showcase",
      "showcase waterfall: a back link goes to the household",
    );
    check(
      (await page.getByRole("link", { name: /See wealth over time/ }).getAttribute("href")) === "/showcase/wealth",
      "showcase waterfall: the primary button goes on to wealth over time",
    );
    await context.close();
  } else {
    // A household for which no strategy differs from the advisor's: nothing to switch.
    notes.push(
      "showcase: this household has no strategy that differs from the advisor's, so the waterfall's switches were not exercised",
    );
    const { context, page } = await newPage();
    await page.goto(base + "/showcase/strategies", { waitUntil: "networkidle" });
    await page.getByRole("heading", { level: 1 }).waitFor({ timeout: 90000 });
    check(
      /nothing to switch on or off/.test(squash(await page.locator("main").innerText())),
      "showcase waterfall: with no strategy that differs from the advisor's the screen says there is nothing to switch",
    );
    await context.close();
  }

  // === Screen 3: wealth over time: the whole plan, whatever was switched on the way =====================================
  // A direct visit shows the screen as the API's whole plan makes it: the baseline the next checks compare with.
  let baseline = "";
  {
    const { context, page, requests } = await newPage();
    await page.goto(base + "/showcase/wealth", { waitUntil: "networkidle" });
    await page.locator(".recharts-wrapper").first().waitFor({ timeout: 90000 });
    await settleLines(page, 4);
    baseline = squash(await page.locator("main").innerText());
    check(
      requests.showcase === 1 &&
        requests.analysis.length === 0 &&
        baseline.includes(`${ratePct(wealth.advantage.median_rate)} a year`),
      "showcase wealth: opened directly, it loads the household once and shows the whole plan, asking for no analysis",
    );
    await context.close();
  }
  {
    const { context, page, issues, requests } = await newPage();
    // Go the way a person does: the strategies screen, two strategies off, then on to the wealth screen.
    await page.goto(base + "/showcase/strategies", { waitUntil: "networkidle" });
    await page
      .locator(keys.length > 0 ? "li[data-key]" : "main h1")
      .first()
      .waitFor({ timeout: 90000 });
    const offBars = keys.length >= 3 ? [full.bars[1], full.bars[2]] : keys.length >= 1 ? [full.bars[0]] : [];
    for (const bar of offBars) await page.getByRole("switch", { name: bar.label, exact: true }).click();
    const onSet = keys.filter((k) => !offBars.some((b) => b.key === k));
    await settled(page);
    const posted = requests.analysis.length;
    await page.getByRole("link", { name: /See wealth over time/ }).click();
    await page.waitForURL("**/showcase/wealth");
    await page.locator(".recharts-wrapper").first().waitFor({ timeout: 30000 });
    await settleLines(page, 4);
    await page.mouse.move(2, 2); // the pointer that clicked the link may be over the chart, whose tooltip is not part of the screen
    await page.waitForTimeout(1200);
    const main = squash(await page.locator("main").innerText());
    check(
      requests.showcase === 1,
      `showcase wealth: moving between the screens does not load the household again (${requests.showcase} request)`,
    );

    // It is the whole plan, and says so: nothing about the switches reaches it, and it never asks for anything.
    check(
      main === baseline,
      offBars.length
        ? `showcase wealth: with ${noun(offBars.length)} switched off on the strategies screen (${offBars.map((b) => b.label).join(", ")}), this screen is exactly what a direct visit shows`
        : "showcase wealth: this screen is exactly what a direct visit shows",
    );
    check(
      main.includes("The whole plan, with every strategy on") &&
        !/strategies off|strategy off|Recomputing|Switch every strategy/i.test(main) &&
        (await page.getByRole("link", { name: "Change the strategies" }).count()) === 0 &&
        (await page.locator('[data-stale="true"], [aria-busy="true"]').count()) === 0,
      "showcase wealth: the subtitle says it is the whole plan with every strategy on, and there is no strategy state bar, no 'Change the strategies' link and nothing recomputing or dimmed",
    );
    check(
      requests.analysis.length === posted,
      `showcase wealth: this screen never asks the API for an analysis (${requests.analysis.length - posted} requests since it opened)`,
    );

    // The headline: the median advantage, and the risk-adjusted one once, with the API's line on what it is.
    const adv = wealth.advantage;
    const medianCell = squash(
      await page.locator("h2", { hasText: "Median advantage" }).locator("xpath=..").innerText(),
    );
    check(
      medianCell.includes(`${ratePct(adv.median_rate)} a year`) &&
        medianCell.includes(
          adv.median_dollars >= 0
            ? `${money(adv.median_dollars)} more at ${horizon}`
            : `${money(-adv.median_dollars)} less at ${horizon}`,
        ),
      `showcase wealth: the headline is ${ratePct(adv.median_rate)} a year and ${money(Math.abs(adv.median_dollars))} ${adv.median_dollars >= 0 ? "more" : "less"} at ${horizon} (median), as the API has it`,
    );
    const riskCell = squash(
      await page.locator("h2", { hasText: wealth.risk_adjusted_label }).locator("xpath=..").innerText(),
    );
    check(
      riskCell.includes(`${ratePct(adv.risk_adjusted_rate)} a year`) &&
        riskCell.includes(`${signedMoney(adv.risk_adjusted_dollars)} at ${horizon}`) &&
        riskCell.includes(squash(wealth.risk_adjusted_explanation)),
      `showcase wealth: the "${wealth.risk_adjusted_label}" is ${ratePct(adv.risk_adjusted_rate)} a year, ${signedMoney(adv.risk_adjusted_dollars)} at ${horizon}, with the API's own explanation, word for word`,
    );
    const explanationLines = await page
      .locator("p", { hasText: squash(wealth.risk_adjusted_explanation).slice(0, 40) })
      .count();
    check(
      explanationLines === 1 &&
        main.split(wealth.risk_adjusted_label).length - 1 === 1 &&
        main.split(squash(wealth.risk_adjusted_explanation)).length - 1 === 1,
      "showcase wealth: the risk-adjusted advantage is shown once (its label, its figure and its one explanation, each once on the screen)",
    );
    check(
      /nine in ten/.test(main) && /10th percentile/.test(main),
      "showcase wealth: a line says what the 10th percentile is (a bad-market future: nine in ten do better)",
    );

    // The four lines: two for each entity, the typical future solid and the bad market dashed, in the app's colours.
    const lines = await page.evaluate(() =>
      [...document.querySelectorAll("path.recharts-line-curve")].map((l) => ({
        stroke: l.getAttribute("stroke"),
        dash: l.getAttribute("stroke-dasharray"),
      })),
    );
    check(
      lines.length === 4 &&
        lines.filter((l) => /donabach/.test(l.stroke)).length === 2 &&
        lines.filter((l) => /ria/.test(l.stroke)).length === 2 &&
        lines.filter((l) => l.dash).length === 2 &&
        ["donabach", "ria"].every((e) => lines.filter((l) => l.stroke.includes(e) && l.dash).length === 1),
      "showcase wealth: the chart draws four lines, two for Donabach (amber) and two for the advisor (blue), the bad-market one of each dashed",
    );
    const legend = (await page.getByRole("list", { name: "Chart legend" }).locator("li").allInnerTexts()).map(squash);
    check(
      legend.length === 4 &&
        legend.some((t) => t === "Donabach, typical (median)") &&
        legend.some((t) => t === "Donabach, bad market (10th percentile)") &&
        legend.some((t) => t === `${wealth.advisor_label}, typical (median)`) &&
        legend.some((t) => t === `${wealth.advisor_label}, bad market (10th percentile)`) &&
        (await page.getByRole("list", { name: "Chart legend" }).locator("line[stroke-dasharray]").count()) === 2,
      `showcase wealth: the legend names the four lines and marks the two bad-market lines as dashed (${legend.join("; ")})`,
    );
    const w = wealth.wealth;
    const lastIndex = w.ages.length - 1;
    // The end labels are SVG text: the value and the name are two spans, with a gap but no space character between them.
    const svgText = (await page.locator(".recharts-wrapper svg text").allTextContents()).join("|").replace(/\s+/g, "");
    const endLabel = (value, name) => `${money(value)}${name}`.replace(/\s+/g, "");
    check(
      svgText.includes(endLabel(w.plan_median[lastIndex], "Donabach, typical")) &&
        svgText.includes(endLabel(w.plan_p10[lastIndex], "Donabach, bad market")) &&
        svgText.includes(endLabel(w.advisor_median[lastIndex], `${wealth.advisor_label}, typical`)) &&
        svgText.includes(endLabel(w.advisor_p10[lastIndex], `${wealth.advisor_label}, bad market`)),
      `showcase wealth: each line is labelled at its end with its value at ${w.ages[lastIndex]} (${money(w.plan_median[lastIndex])}, ${money(w.plan_p10[lastIndex])}, ${money(w.advisor_median[lastIndex])}, ${money(w.advisor_p10[lastIndex])})`,
    );
    check(
      w.ages[0] === card.people[0].age && w.ages[lastIndex] === horizon,
      `showcase wealth: the lines run from today's age (${w.ages[0]}) to the horizon (${w.ages[lastIndex]})`,
    );

    // The tooltip lists all four lines at the age under the cursor.
    const wrapper = page.locator(".recharts-wrapper").first();
    await wrapper.scrollIntoViewIfNeeded();
    const box = await wrapper.boundingBox();
    await page.mouse.move(box.x + box.width * 0.4, box.y + box.height * 0.5);
    await page.waitForTimeout(500);
    const tipText = squash(await page.locator(".recharts-tooltip-wrapper").first().innerText());
    const tipAge = Number((tipText.match(/Age (\d+)/) ?? [])[1]);
    const at = w.ages.indexOf(tipAge);
    // The value leads and the name follows, a margin apart: no space character between them in the text.
    const tipCompact = tipText.replace(/\s+/g, "");
    const tipLine = (value, name) => `${money(value)}${name}`.replace(/\s+/g, "");
    check(
      at >= 0 &&
        tipCompact.includes(tipLine(w.plan_median[at], "Donabach, typical")) &&
        tipCompact.includes(tipLine(w.plan_p10[at], "Donabach, bad market")) &&
        tipCompact.includes(tipLine(w.advisor_median[at], `${wealth.advisor_label}, typical`)) &&
        tipCompact.includes(tipLine(w.advisor_p10[at], `${wealth.advisor_label}, bad market`)),
      `showcase wealth: hovering the chart shows a tooltip with all four values at that age (age ${tipAge}: ${at >= 0 ? [w.plan_median[at], w.plan_p10[at], w.advisor_median[at], w.advisor_p10[at]].map(money).join(", ") : "?"})`,
    );
    await page.mouse.move(2, 2);

    // And by keyboard: the chart takes focus, the arrow keys move along the ages.
    await wrapper.locator("svg").first().focus();
    for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(300);
    const keyTip = squash(await page.locator(".recharts-tooltip-wrapper").first().innerText());
    check(
      new RegExp(`Age ${w.ages[3]}\\b`).test(keyTip),
      `showcase wealth: the chart answers the keyboard too (three presses of the right arrow show age ${w.ages[3]})`,
    );

    // What a bad market does: the two 10th-percentile values at the horizon and the chance of running out of money, for both.
    const bad = squash(await page.locator('section[aria-label^="The 10th percentile"]').innerText());
    check(
      bad.includes(`Donabach ${money(adv.plan_p10_at_horizon)}`) &&
        bad.includes(`${wealth.advisor_label} ${money(adv.advisor_p10_at_horizon)}`) &&
        bad.includes("nine in ten do better"),
      `showcase wealth: the 10th percentile at ${horizon} is shown for both (${money(adv.plan_p10_at_horizon)} with Donabach, ${money(adv.advisor_p10_at_horizon)} with the advisor)`,
    );
    const risk = squash(await page.locator('section[aria-label="Chance of running out of money"]').innerText());
    check(
      risk.includes(`Donabach ${pct1(adv.plan_shortfall)}`) &&
        risk.includes(`${wealth.advisor_label} ${pct1(adv.advisor_shortfall)}`),
      `showcase wealth: the chance of running out of money is shown for both (${pct1(adv.plan_shortfall)} with Donabach, ${pct1(adv.advisor_shortfall)} with the advisor)`,
    );

    // The table twin: a row for every age, the four values for each.
    await page.getByRole("button", { name: "View as table" }).click();
    const wealthTable = page.getByRole("table", { name: /After-tax wealth by age/ });
    await wealthTable.waitFor();
    const heads = (await wealthTable.locator("thead th").allInnerTexts()).map(squash);
    const tableData = (await wealthTable.locator("tbody tr").allInnerTexts()).map((t) => squash(t));
    check(
      heads.length === 5 &&
        tableData.length === w.ages.length &&
        [0, Math.floor(lastIndex / 2), lastIndex].every(
          (i) =>
            tableData[i] ===
            `${w.ages[i]} ${money(w.plan_median[i])} ${money(w.plan_p10[i])} ${money(w.advisor_median[i])} ${money(w.advisor_p10[i])}`,
        ),
      `showcase wealth: the table twin has a row for each of the ${w.ages.length} ages with the four values (${heads.join(" / ")})`,
    );
    await page.getByRole("button", { name: "View as chart" }).click();
    await settleLines(page, 4);
    const weak = await lowContrast(page);
    check(
      weak.length === 0,
      `showcase wealth (light): all text has enough contrast${weak.length ? ` (${weak.join("; ")})` : ""}`,
    );
    await footerLine(page, "showcase wealth");
    await audit(page, issues, "showcase 3 wealth", "showcase-3-wealth");
    check(
      (await page.getByRole("link", { name: /Explore the full demo/ }).getAttribute("href")) === "/",
      "showcase wealth: the primary button leads on to the full demo",
    );
    check(
      requests.analysis.length === posted,
      `showcase wealth: after hovering, the keyboard and the table it still has asked for no analysis (${requests.analysis.length - posted} requests)`,
    );

    // The way back: the switches are as they were left, and the strategies screen still shows what they came to.
    const back = page.getByRole("link", { name: /Back to the strategies/ });
    check(
      (await back.getAttribute("href")) === "/showcase/strategies",
      "showcase wealth: a back link goes to the strategies",
    );
    await back.click();
    await page.waitForURL("**/showcase/strategies");
    await page
      .locator(keys.length > 0 ? "li[data-key]" : "main h1")
      .first()
      .waitFor();
    if (offBars.length) {
      let still = true;
      for (const bar of full.bars)
        still &&=
          (await page.getByRole("switch", { name: bar.label, exact: true }).isChecked()) ===
          !offBars.some((b) => b.key === bar.key);
      const totalNow = squash(await page.locator('section[aria-labelledby="total-title"]').innerText());
      check(
        still && requests.showcase === 1 && totalNow.includes(strategiesOn(onSet.length, keys.length)),
        `showcase wealth: back on the strategies screen the switches and the waterfall are as they were left (${offBars.map((b) => b.label).join(", ")} off)`,
      );
    }
    await context.close();
  }

  // A change still being worked out when the person moves on: the wealth screen does not wait for it, show it or follow it.
  if (keys.length >= 1) {
    const { context, page, requests } = await newPage();
    await page.goto(base + "/showcase/strategies", { waitUntil: "networkidle" });
    await page.locator("li[data-key]").first().waitFor({ timeout: 90000 });
    const off = full.bars[keys.length - 1];
    const onSet = keys.filter((k) => k !== off.key);
    const expected = await analysisFor(onSet);
    let release;
    const held = new Promise((r) => (release = r));
    await page.route("**/api/showcase/analysis", async (route) => {
      await held;
      await route.fallback();
    });
    await page.getByRole("switch", { name: off.label, exact: true }).click();
    await page.getByRole("link", { name: /See wealth over time/ }).click();
    await page.waitForURL("**/showcase/wealth");
    await page.locator(".recharts-wrapper").first().waitFor({ timeout: 30000 });
    await settleLines(page, 4);
    await page.mouse.move(2, 2);
    await page.waitForTimeout(500);
    const pending = squash(await page.locator("main").innerText());
    check(
      pending === baseline &&
        !/Recomputing/.test(pending) &&
        (await page.locator('[data-stale="true"], [aria-busy="true"]').count()) === 0,
      "showcase wealth: opened while a change is still being worked out, it shows the whole plan at once, nothing dimmed and nothing recomputing: it does not wait for the change",
    );
    const answered = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/showcase/analysis");
    release();
    await answered;
    await page.waitForTimeout(500);
    check(
      squash(await page.locator("main").innerText()) === baseline && requests.analysis.length === 1,
      "showcase wealth: when the answer arrives the screen is unchanged, and no second request went out",
    );
    await page.getByRole("link", { name: /Back to the strategies/ }).click();
    await page.waitForURL("**/showcase/strategies");
    await page.locator("li[data-key]").first().waitFor();
    await settled(page);
    const shown = squash(await page.locator('section[aria-labelledby="total-title"]').innerText());
    check(
      !(await page.getByRole("switch", { name: off.label, exact: true }).isChecked()) &&
        shown.includes(`${ratePct(expected.advantage.median_rate)} a year`) &&
        shown.includes(strategiesOn(onSet.length, keys.length)),
      `showcase wealth: back on the strategies screen the change has landed there (${ratePct(expected.advantage.median_rate)} a year with ${off.label} off)`,
    );
    await context.close();
  }

  // Reduced motion: nothing glides or eases in, and the chart's lines are drawn at once.
  {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.goto(base + "/showcase/strategies", { waitUntil: "networkidle" });
    await page
      .locator(keys.length > 0 ? "li[data-key]" : "main h1")
      .first()
      .waitFor({ timeout: 90000 });
    const durations = await page.evaluate(() => {
      const bar = document.querySelector("li[data-kind=strategy] [data-track] > span[data-kind]") ?? document.body;
      const seconds = (css) => Math.max(...css.split(",").map((d) => parseFloat(d)));
      return {
        bar: seconds(getComputedStyle(bar).transitionDuration),
        screen: seconds(getComputedStyle(document.querySelector("[data-showcase] > div")).animationDuration),
      };
    });
    check(
      durations.bar < 0.01 && durations.screen < 0.01,
      `reduced motion: the bars do not glide and the screen does not ease in (${durations.bar}s, ${durations.screen}s)`,
    );
    await page.goto(base + "/showcase/wealth", { waitUntil: "networkidle" });
    await page.locator(".recharts-wrapper").first().waitFor({ timeout: 30000 });
    await page.waitForTimeout(150);
    const dashes = await page.evaluate(() =>
      [...document.querySelectorAll("path.recharts-line-curve")].map((l) => l.getAttribute("stroke-dasharray") ?? ""),
    );
    check(
      dashes.length === 4 && dashes.every((d) => !d.includes("px")),
      "reduced motion: the chart's lines are drawn at once, not drawn in",
    );
    await context.close();
  }

  // === Every screen is there at once: Household -> Strategies -> Wealth -> Strategies, once the household has loaded ====
  {
    const { context, page, requests } = await newPage();
    await page.goto(base + "/showcase", { waitUntil: "networkidle" });
    await page.locator("article").first().waitFor({ timeout: 90000 });
    await page.waitForTimeout(800); // the way on has been prefetched by now
    await page.evaluate(watchPlaceholders);
    const strategiesTarget = keys.length > 0 ? "li[data-key]" : "main h1";
    const hops = [
      ["See the strategies", "/showcase/strategies", strategiesTarget],
      ["See wealth over time", "/showcase/wealth", ".recharts-wrapper"],
      ["Back to the strategies", "/showcase/strategies", strategiesTarget],
      ["Back to the household", "/showcase", "article"],
    ];
    const taken = [];
    for (const [name, path, target] of hops) {
      // Clicked and timed inside the page, so that nothing but the app is in the figure.
      const ms = await page.evaluate(
        ({ name, path, target }) =>
          new Promise((resolve) => {
            const link = [...document.querySelectorAll("a")].find((a) => (a.textContent ?? "").trim().startsWith(name));
            if (!link) return resolve(Infinity);
            const started = performance.now();
            const giveUp = setTimeout(() => resolve(Infinity), 5000);
            const look = () => {
              if (location.pathname === path && document.querySelector(target)) {
                clearTimeout(giveUp);
                resolve(performance.now() - started);
              } else requestAnimationFrame(look);
            };
            link.click();
            look();
          }),
        { name, path, target },
      );
      taken.push(`${name.toLowerCase()}: ${Math.round(ms)} ms`);
      await page.waitForTimeout(400);
    }
    const placeholder = await page.evaluate(() => window.__placeholder);
    check(
      taken.every((t) => parseInt(t.split(": ")[1], 10) < 1000),
      `showcase flow: every screen shows its content within 1,000 ms of the click (${taken.join("; ")})`,
    );
    check(
      !placeholder && requests.showcase === 1 && requests.analysis.length === 0,
      `showcase flow: going Household, Strategies, Wealth, Strategies and back shows no loading placeholder and asks the API for nothing more (${requests.showcase} household request, ${requests.analysis.length} analyses)`,
    );
    await context.close();
  }

  // === The footer's line is the API's, word for word, and only once the household is in ===================================
  {
    const made = "Results for this household. The e2e made this line up (7.7% a year).";
    const { context, page } = await newPage();
    let release;
    const held = new Promise((r) => (release = r));
    await page.route("**/api/showcase", async (route) => {
      await held;
      const response = await route.fetch();
      await route.fulfill({ response, json: { ...(await response.json()), footer_note: made } });
    });
    await page.goto(base + "/showcase", { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { level: 1 }).waitFor({ timeout: 20000 });
    await page.waitForTimeout(500);
    check(
      (await page.locator("footer").count()) === 0 &&
        !(await page.locator("body").innerText()).includes("Results for this household"),
      "showcase footer: while the household is still loading there is no footer line",
    );
    release();
    await page.locator("article").first().waitFor({ timeout: 90000 });
    const firstLine = async () => squash((await page.locator("footer p").first().innerText()) ?? "");
    const lines = [["household", await firstLine()]];
    await page.getByRole("link", { name: /See the strategies/ }).click();
    await page.waitForURL("**/showcase/strategies");
    await page
      .locator(keys.length > 0 ? "li[data-key]" : "footer p")
      .first()
      .waitFor({ timeout: 30000 });
    lines.push(["strategies", await firstLine()]);
    await page.getByRole("link", { name: /See wealth over time/ }).click();
    await page.waitForURL("**/showcase/wealth");
    await page.locator(".recharts-wrapper").first().waitFor({ timeout: 30000 });
    lines.push(["wealth", await firstLine()]);
    check(
      lines.every(([, line]) => line === made),
      `showcase footer: the screens write the API's footer_note as it is, with no number of their own (${lines.map(([name]) => name).join(", ")}: "${made}")`,
    );
    await context.close();
  }

  // The API cannot be reached: the screen says so, with a way to try again.
  {
    const { context, page } = await newPage();
    let fail = true;
    await page.route("**/api/showcase", (route) =>
      fail
        ? route.fulfill({
            status: 500,
            contentType: "application/json",
            body: JSON.stringify({ detail: "the e2e made this error up" }),
          })
        : route.fallback(),
    );
    await page.goto(base + "/showcase", { waitUntil: "networkidle" });
    const alert = page.getByRole("alert");
    await alert.first().waitFor({ timeout: 15000 });
    check(
      (await alert.first().innerText()).includes("the e2e made this error up"),
      "showcase household: when the API fails the screen shows its message",
    );
    fail = false;
    await page.getByRole("button", { name: "Try again" }).click();
    await page.getByRole("heading", { level: 1, name: showcase.name }).waitFor({ timeout: 60000 });
    check(true, "showcase household: 'Try again' loads the household");
    await context.close();
  }
}

// Run on its own: a minimal harness around the same checks.
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const { chromium } = await import("playwright-core");
  const base = process.env.BASE_URL ?? "http://localhost:3000";
  const out = resolve(process.env.OUT_DIR ?? new URL("../../.screenshots", import.meta.url).pathname);
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ["--no-sandbox"],
  });
  const failures = [];
  const notes = [];
  let checks = 0;
  const check = (ok, message) => {
    checks++;
    if (!ok) failures.push(message);
    console.log(`${ok ? "  ok  " : " FAIL "} ${message}`);
  };
  try {
    await runShowcase({ browser, base, out, check, notes });
  } catch (error) {
    check(false, `the showcase run stopped: ${error.message}`);
  }
  await browser.close();
  for (const n of notes) console.log(` note  ${n}`);
  console.log(
    failures.length
      ? `\n${failures.length} of ${checks} check(s) failed:\n - ${failures.join("\n - ")}`
      : `\nAll checks passed (${checks} of ${checks})`,
  );
  process.exit(failures.length ? 1 : 0);
}
