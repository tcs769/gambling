import { niceScale } from "@/components/charts/chartTheme";

export interface Axis {
  min: number;
  max: number;
  ticks: number[];
}

/**
 * An axis that holds [min, max] and zero, in clean steps (1, 2, 2.5 or 5 times a power of ten) that run through zero: a series
 * that goes below zero (a strategy that lowers the total, a bad-market future that runs out of money) gets room and ticks
 * below it. `maxIntervals` is how many steps the larger side may take, so a narrow chart asks for fewer ticks.
 */
export function niceAxis(min: number, max: number, maxIntervals: number): Axis {
  if (!(max > 0) && !(min < 0)) return { min: 0, max: 1, ticks: [0] };
  const { ticks } = niceScale(Math.max(max, -min), maxIntervals);
  const step = ticks[1] - ticks[0];
  const up = max > 0 ? Math.ceil(max / step - 1e-9) : 0;
  const down = min < 0 ? Math.ceil(-min / step - 1e-9) : 0;
  const all: number[] = [];
  for (let i = -down; i <= Math.max(up, 1); i++) all.push(i * step);
  return { min: -down * step, max: Math.max(up, 1) * step, ticks: all };
}
