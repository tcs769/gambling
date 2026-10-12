// Shared by the round-two checks (valuations.mjs, giving.mjs, styles.mjs): the words and numbers the way the screens write them
// (read from src/lib/format.ts), a browser page that records what the screen does, and the harness for running a module alone.

import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const trimZeros = (s) => (s.includes(".") ? s.replace(/\.?0+$/, "") : s);
/** $850, $4.2k, $40k, $250k, $1.24M. */
export const money = (value) => {
  const sign = value < 0 ? "−" : "";
  const abs = Math.abs(value);
  if (abs >= 999_500) return `${sign}$${trimZeros((abs / 1_000_000).toFixed(2))}M`;
  if (abs >= 100_000) return `${sign}$${Math.round(abs / 1_000)}k`;
  if (abs >= 1_000) return `${sign}$${trimZeros((abs / 1_000).toFixed(1))}k`;
  return `${sign}$${Math.round(abs)}`;
};
export const signedMoney = (value) => (Math.abs(value) < 0.5 ? "$0" : `${value > 0 ? "+" : ""}${money(value)}`);
/** Exact dollars: $7,500. */
export const exact = (value) =>
  `${Math.round(value) < 0 ? "−" : ""}$${Math.abs(Math.round(value)).toLocaleString("en-US")}`;
/** +1.61%, −0.04%, 0.00% (a true minus sign, and no sign on nothing). */
export const signedPercent = (fraction, digits = 2) => {
  const v = Number((fraction * 100).toFixed(digits));
  return v === 0 ? `${(0).toFixed(digits)}%` : `${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(digits)}%`;
};
/** A yearly rate the way the showcase writes it: two decimals, three under 0.1% a year. */
export const ratePct = (fraction) => signedPercent(fraction, fraction === 0 ? 2 : Math.abs(fraction) < 0.001 ? 3 : 2);
/** 0.995 -> "99.5%", 0.02 -> "2%". */
export const pct1 = (fraction) => `${Number((fraction * 100).toFixed(1))}%`;
export const pct0 = (fraction) => `${(fraction * 100).toFixed(0)}%`;
export const count = (n) => Math.round(n).toLocaleString("en-US");
export const years = (n) => `${n} ${n === 1 ? "year" : "years"}`;
export const squash = (text) => text.replace(/\s+/g, " ").trim();
/** What the showcase's heirs figure says about the dollars: "$1.18M more at 80". */
export const moreOrLess = (dollars, horizon) =>
  Math.abs(dollars) < 0.5
    ? `no difference at ${horizon}`
    : `${money(Math.abs(dollars))} ${dollars > 0 ? "more" : "less"} at ${horizon}`;
/** The figures as printed, for judging whether a range includes zero the way the screen does. */
export const printed = (fraction, digits = 2) => Number((fraction * 100).toFixed(digits));

/** The text the footer of a results screen carries about deductions, as the brief words it. */
export const FOOTER_TEXT = "the standard deduction (itemizing only for charitable gifts)";
export const OLD_FOOTER_TEXT = "standard deduction only (no itemizing)";

/** A browser page that records the console errors and the requests the screen makes to the API. */
export async function openPage(browser, { width = 1440, height = 900 } = {}) {
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  const issues = [];
  page.on("console", (m) => {
    if (m.type() === "error") issues.push(m.text());
  });
  page.on("pageerror", (e) => issues.push(`pageerror: ${e.message}`));
  return { context, page, issues };
}

/**
 * How the page lays out: text under 14px, how far `main` reaches past its own width (the demo's step navigation overflows the
 * window below about 720px by design, so the page itself is not asked), and anything that reaches past the panel it sits in.
 */
export function layoutOf(page, scope = "main section, main article, main aside") {
  return page.evaluate((selector) => {
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
    const main = document.querySelector("main");
    const spill = [];
    for (const panel of document.querySelectorAll(selector)) {
      const box = panel.getBoundingClientRect();
      for (const el of panel.querySelectorAll("*")) {
        if (el.closest(".sr-only,[hidden],table,svg,[data-track]")) continue;
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        if (r.right > box.right + 1 || r.left < box.left - 1)
          spill.push(`${el.tagName.toLowerCase()} "${(el.textContent ?? "").trim().slice(0, 24)}"`);
      }
    }
    return {
      small: [...new Set(small)].slice(0, 5),
      mainOverflow: main ? main.scrollWidth - main.clientWidth : 0,
      pageOverflow: document.documentElement.scrollWidth - window.innerWidth,
      spill: [...new Set(spill)].slice(0, 5),
    };
  }, scope);
}

/** Is this module the one being run (rather than imported by walkthrough.mjs)? */
export const isMain = (url) => !!process.argv[1] && url === pathToFileURL(resolve(process.argv[1])).href;

/** Run one module's checks on their own: a minimal harness with the same `check` the walkthrough has. */
export async function runAlone(run, label) {
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
    await run({ browser, base, out, check, notes });
  } catch (error) {
    check(false, `the ${label} run stopped: ${error.stack ?? error.message}`);
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
