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
/** The third series, the typical advisor: always drawn dashed too, so colour never carries it alone. */
export const SERIES_TYPICAL = "var(--series-typical)";
/** The fourth series, the adaptive (year-by-year) planner: always drawn dotted too, for the same reason. */
export const SERIES_ADAPTIVE = "var(--series-adaptive)";

/** Wash for the wide band (10th to 90th percentile) and the darker one inside it (25th to 75th). */
export const OUTER_BAND_OPACITY = 0.13;
export const INNER_BAND_OPACITY = 0.2;
/** A lighter wash for a secondary series' band, so two bands can overlap and both stay readable. */
export const LIGHT_BAND_OPACITY = 0.07;

/**
 * How a series' line is drawn. Colour never carries a series alone: the typical advisor is dashed and the adaptive
 * planner is dotted (the other two are solid), in the chart, the end-label key, the tooltip key and the legend swatch.
 */
export type LineStyle = "solid" | "dashed" | "dotted";

/** Where a line is drawn: the chart itself, the short key beside an end label or in a tooltip, the legend swatch. */
export type LineSize = "line" | "key" | "swatch";

const DASH: Record<LineSize, string> = { line: "7 5", key: "5 3.5", swatch: "6 4" };
/** A dash of almost no length with round caps is a dot: spaced a little over twice the line's width apart. */
const DOT: Record<LineSize, string> = { line: "0.1 6.5", key: "0.1 5.5", swatch: "0.1 6" };
/** Dots read better a touch thicker than a solid line's 2px. */
const DOT_WIDTH = 3;

/** The SVG stroke attributes for a series' line style at a size. */
export function lineStroke(style: LineStyle | undefined, size: LineSize) {
  switch (style) {
    case "dashed":
      return { strokeDasharray: DASH[size], strokeLinecap: "butt" as const, strokeWidth: 2 };
    case "dotted":
      return { strokeDasharray: DOT[size], strokeLinecap: "round" as const, strokeWidth: DOT_WIDTH };
    default:
      return { strokeDasharray: undefined, strokeLinecap: "round" as const, strokeWidth: 2 };
  }
}

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
 * (38 to 80 gives 38, 45, 50, ... 80.)
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
