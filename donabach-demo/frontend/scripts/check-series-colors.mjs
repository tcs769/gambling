// Checks the chart series colours in src/app/globals.css, so a colour change cannot quietly break them.
//
//   npm run check:colors
//
// The gates are the ones the dataviz validator uses for a categorical palette, run over every pair of
// series (any two can sit side by side on a chart):
//   - contrast against the panel the charts sit on: at least 3:1
//   - OKLCH lightness 0.43 to 0.77 and chroma of at least 0.10 (below that a hue reads as gray)
//   - distance between two series (OKLab Delta E x 100) under protanopia, deuteranopia and
//     tritanopia, simulated with Machado, Oliveira and Fernandes (2009) at severity 1.0: at least 8
//   - the same distance with normal vision: at least 15
// The third series (the typical advisor) is also drawn dashed and the fourth (the adaptive planner) dotted, so
// line style carries them as well as colour. With four series every pair is checked: six pairs.
//
// Both themes are checked. The light tokens are the ones in :root. The dark theme of the showcase flow re-declares
// the series for the dark panel (the `@media (prefers-color-scheme: dark)` block): the same gates, except that the
// lightness band is the validator's dark one, 0.48 to 0.67, since the colours have to read on a dark surface.
// The savings bar of the showcase household card puts the account colours side by side (--account-taxable,
// -pretax, -roth, -cash, in that order), so each neighbouring pair is checked in both themes, and each account's
// contrast on the panel.
// Exits 1 if any gate fails.

import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");

// The two places tokens are declared: :root (the light theme) and the dark block of the showcase flow.
const DARK_MARKER = "@media (prefers-color-scheme: dark)";
const darkAt = css.indexOf(DARK_MARKER);
if (darkAt < 0) throw new Error("globals.css has no dark theme block to check");
const THEMES = {
  light: { css: css.slice(0, darkAt), lightness: [0.43, 0.77] },
  dark: { css: css.slice(darkAt), lightness: [0.48, 0.67] },
};

const MIN_CONTRAST = 3;
const MIN_CHROMA = 0.1;
const MIN_CVD = 8;
const MIN_NORMAL = 15;

// Machado, Oliveira and Fernandes (2009), severity 1.0, applied to linear RGB.
const CVD = {
  protan: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  deutan: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]],
  tritan: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.3039]],
};

const toLinear = (hex) =>
  [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
const luminance = (hex) => {
  const [r, g, b] = toLinear(hex);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const oklab = ([r, g, b]) => {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
};
const seen = (hex, kind) => {
  const rgb = toLinear(hex);
  if (!kind) return rgb;
  return CVD[kind].map((row) => Math.min(1, Math.max(0, row[0] * rgb[0] + row[1] * rgb[1] + row[2] * rgb[2])));
};
const deltaE = (a, b, kind) => {
  const [p, q] = [oklab(seen(a, kind)), oklab(seen(b, kind))];
  return 100 * Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
};

const failures = [];
const gate = (ok, message) => {
  console.log(`${ok ? "  ok  " : " FAIL "} ${message}`);
  if (!ok) failures.push(message);
};

for (const [theme, { css: source, lightness }] of Object.entries(THEMES)) {
  console.log(`\n== ${theme} theme ==`);
  const token = (name) => {
    const match = source.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`));
    if (!match) throw new Error(`--${name} is not a hex colour in the ${theme} part of globals.css`);
    return match[1].toLowerCase();
  };
  const SERIES = {
    donabach: token("series-donabach"),
    ria: token("series-ria"),
    typical: token("series-typical"),
    adaptive: token("series-adaptive"),
  };
  const SURFACES = { panel: token("panel"), cream: token("cream") };
  const label = (text) => `${theme}: ${text}`;

  for (const [name, hex] of Object.entries(SERIES)) {
    const [L, a, b] = oklab(toLinear(hex));
    const C = Math.hypot(a, b);
    const hue = ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360;
    console.log(`${name.padEnd(9)} ${hex}  OKLCH L ${L.toFixed(3)} C ${C.toFixed(3)} hue ${hue.toFixed(0)}`);
    gate(L >= lightness[0] && L <= lightness[1] && C >= MIN_CHROMA, label(`${name}: lightness ${L.toFixed(2)} in ${lightness.join("-")} and chroma ${C.toFixed(2)} >= ${MIN_CHROMA}`));
    for (const [surface, surfaceHex] of Object.entries(SURFACES)) {
      const ratio = contrast(hex, surfaceHex);
      // The charts sit on the panel; cream is reported only (the page background, for the legend and notes).
      if (surface === "panel") gate(ratio >= MIN_CONTRAST, label(`${name}: contrast ${ratio.toFixed(2)}:1 on the ${surface} (>= ${MIN_CONTRAST}:1)`));
      else console.log(`        contrast ${ratio.toFixed(2)}:1 on the ${surface}`);
    }
  }

  const names = Object.keys(SERIES);
  for (let i = 0; i < names.length; i++) {
    for (let j = i + 1; j < names.length; j++) {
      const [x, y] = [SERIES[names[i]], SERIES[names[j]]];
      const normal = deltaE(x, y);
      const cvd = Object.fromEntries(Object.keys(CVD).map((kind) => [kind, deltaE(x, y, kind)]));
      console.log(
        `${names[i]} vs ${names[j]}: Delta E normal ${normal.toFixed(1)}, ` + Object.entries(cvd).map(([k, v]) => `${k} ${v.toFixed(1)}`).join(", "),
      );
      gate(normal >= MIN_NORMAL, label(`${names[i]} vs ${names[j]}: normal vision ${normal.toFixed(1)} >= ${MIN_NORMAL}`));
      gate(Math.min(...Object.values(cvd)) >= MIN_CVD, label(`${names[i]} vs ${names[j]}: worst colour-blind pair ${Math.min(...Object.values(cvd)).toFixed(1)} >= ${MIN_CVD}`));
    }
  }

  // The savings bar of the household card: the accounts' colours, in the bar's order, with each neighbouring pair next to each other.
  // An account token is declared once, in :root, as a var() of a series token or of --muted (cash, the de-emphasis gray); the dark
  // theme re-declares what it points at, so a token is looked up in this theme first and in the light part otherwise.
  const resolve = (name) => {
    const find = (text) => text.match(new RegExp(`--${name}:\\s*([^;]+);`));
    const match = find(source) ?? find(THEMES.light.css);
    if (!match) throw new Error(`--${name} is not declared in globals.css`);
    const value = match[1].trim();
    const ref = value.match(/^var\(--([\w-]+)\)$/);
    if (ref) return resolve(ref[1]);
    if (!/^#[0-9a-fA-F]{6}$/.test(value)) throw new Error(`--${name} is not a colour in globals.css`);
    return value.toLowerCase();
  };
  const ACCOUNTS = ["taxable", "pretax", "roth", "cash"].map((name) => [name, resolve(`account-${name}`)]);
  for (const [name, hex] of ACCOUNTS) {
    gate(contrast(hex, SURFACES.panel) >= MIN_CONTRAST, label(`account ${name} ${hex}: contrast ${contrast(hex, SURFACES.panel).toFixed(2)}:1 on the panel (>= ${MIN_CONTRAST}:1)`));
  }
  for (let i = 0; i + 1 < ACCOUNTS.length; i++) {
    const [[nameA, a], [nameB, b]] = [ACCOUNTS[i], ACCOUNTS[i + 1]];
    const normal = deltaE(a, b);
    const worst = Math.min(...Object.keys(CVD).map((kind) => deltaE(a, b, kind)));
    console.log(`savings bar, ${nameA} next to ${nameB}: Delta E normal ${normal.toFixed(1)}, worst colour-blind ${worst.toFixed(1)}`);
    gate(normal >= MIN_NORMAL && worst >= MIN_CVD, label(`savings bar: ${nameA} next to ${nameB}: normal vision ${normal.toFixed(1)} >= ${MIN_NORMAL}, worst colour-blind ${worst.toFixed(1)} >= ${MIN_CVD}`));
  }
}

console.log(failures.length ? `\n${failures.length} gate(s) failed` : "\nAll gates passed");
process.exit(failures.length ? 1 : 0);
