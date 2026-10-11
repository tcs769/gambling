// Shared look for the charts. Colors are CSS variables so the series tokens in globals.css stay the
// single source of truth (they are validated for color-blind separation and contrast).

/** Height of the chart body, x-axis band included. Always at least 300px. */
export const CHART_HEIGHT = 380;

/** Charts glide to new values over this long when a re-plan arrives. */
export const ANIMATION_MS = 700;

/** Axis text uses the muted text token (never a series color), at a readable size. */
export const TICK_STYLE = { fill: "var(--muted-text)", fontSize: 14 } as const;

/** Gridlines and axes: solid hairlines, recessive. */
export const GRID_STROKE = "var(--line)";

/** The surface under the chart; markers get a ring in this color so they stay legible. */
export const SURFACE = "var(--panel)";

export const SERIES_DONABACH = "var(--series-donabach)";
export const SERIES_RIA = "var(--series-ria)";

/** Wash for the wide band (10th to 90th percentile) and the darker one inside it (25th to 75th). */
export const OUTER_BAND_OPACITY = 0.13;
export const INNER_BAND_OPACITY = 0.2;

/**
 * Clean y-axis ticks from zero: steps of 1, 2, 2.5 or 5 times a power of ten, the smallest step
 * that covers `max` in at most `maxIntervals` intervals (so $427k gets $0 to $500k by $100k, not
 * $0 to $450k by $90k).
 */
export function niceScale(max: number, maxIntervals = 7): { ticks: number[]; domainMax: number } {
  if (!Number.isFinite(max) || max <= 0) return { ticks: [0, 1], domainMax: 1 };
  const power = Math.pow(10, Math.floor(Math.log10(max / maxIntervals)));
  let step = power;
  for (const multiple of [1, 2, 2.5, 5, 10]) {
    step = multiple * power;
    if (Math.ceil(max / step - 1e-9) <= maxIntervals) break;
  }
  const intervals = Math.max(1, Math.ceil(max / step - 1e-9));
  return { ticks: Array.from({ length: intervals + 1 }, (_, i) => i * step), domainMax: intervals * step };
}

/**
 * Age ticks: the first age, then every fifth year, never two labels closer than three years.
 * (38 to 70 gives 38, 45, 50, ... 70.)
 */
export function ageTicks(ages: readonly number[]): number[] {
  if (ages.length === 0) return [];
  const ticks = [ages[0]];
  for (const age of ages) {
    if (age % 5 === 0 && age - ticks[ticks.length - 1] >= 3) ticks.push(age);
  }
  const last = ages[ages.length - 1];
  if (last - ticks[ticks.length - 1] >= 3) ticks.push(last);
  return ticks;
}
