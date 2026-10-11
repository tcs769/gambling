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
// The third series (the typical advisor) is also drawn dashed, so line style carries it as well as colour.
// Exits 1 if any gate fails.

import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");
const token = (name) => {
  const match = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (!match) throw new Error(`--${name} is not a hex colour in globals.css`);
  return match[1].toLowerCase();
};

const SERIES = { donabach: token("series-donabach"), ria: token("series-ria"), typical: token("series-typical") };
const SURFACES = { panel: token("panel"), cream: token("cream") };
const MIN_CONTRAST = 3;
const LIGHTNESS = [0.43, 0.77];
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

for (const [name, hex] of Object.entries(SERIES)) {
  const [L, a, b] = oklab(toLinear(hex));
  const C = Math.hypot(a, b);
  const hue = ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360;
  console.log(`${name.padEnd(9)} ${hex}  OKLCH L ${L.toFixed(3)} C ${C.toFixed(3)} hue ${hue.toFixed(0)}`);
  gate(L >= LIGHTNESS[0] && L <= LIGHTNESS[1] && C >= MIN_CHROMA, `${name}: lightness ${L.toFixed(2)} in ${LIGHTNESS.join("-")} and chroma ${C.toFixed(2)} >= ${MIN_CHROMA}`);
  for (const [surface, surfaceHex] of Object.entries(SURFACES)) {
    const ratio = contrast(hex, surfaceHex);
    // The charts sit on the panel; cream is reported only (the page background, for the legend and notes).
    if (surface === "panel") gate(ratio >= MIN_CONTRAST, `${name}: contrast ${ratio.toFixed(2)}:1 on the ${surface} (>= ${MIN_CONTRAST}:1)`);
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
    gate(normal >= MIN_NORMAL, `${names[i]} vs ${names[j]}: normal vision ${normal.toFixed(1)} >= ${MIN_NORMAL}`);
    gate(Math.min(...Object.values(cvd)) >= MIN_CVD, `${names[i]} vs ${names[j]}: worst colour-blind pair ${Math.min(...Object.values(cvd)).toFixed(1)} >= ${MIN_CVD}`);
  }
}

console.log(failures.length ? `\n${failures.length} gate(s) failed` : "\nAll gates passed");
process.exit(failures.length ? 1 : 0);
