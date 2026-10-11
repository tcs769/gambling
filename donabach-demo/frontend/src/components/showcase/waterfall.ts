// The arithmetic and wording of the strategy waterfall, kept apart from the drawing so both are easy to check.
// Nothing here makes a number up: positions, totals and labels come from the API's bars and advantage.

import { money, rateDigits, signedMoney, signedPercent } from "@/lib/format";
import type { ShowcaseAnalysis } from "@/lib/types";
import { niceAxis, type Axis } from "./axis";

/** What the length of a bar encodes: dollars of median after-tax wealth at the horizon, or a yearly rate. */
export type Unit = "dollars" | "rate";

/** The same quantity in both units: a yearly rate (a fraction: 0.004 is 0.4% a year) and dollars at the horizon. */
export interface Amount {
  rate: number;
  dollars: number;
}

export interface WaterfallRow {
  /** The start (the advisor, 0), a strategy, or the total (Donabach). */
  kind: "start" | "strategy" | "total";
  key: string;
  label: string;
  /** What the strategy does, in the API's words (strategies only). */
  detail: string;
  /** Whether the strategy is switched on in the analysis the row comes from (the start and the total always are). */
  enabled: boolean;
  /** Where the bar starts and where it ends, in both units. A strategy that is off starts and ends at the same place. */
  from: Amount;
  to: Amount;
  /** What the row adds (for the total, everything: the headline). */
  delta: Amount;
}

const ZERO: Amount = { rate: 0, dollars: 0 };

/**
 * The rows of the waterfall, top to bottom: the advisor's result (the start, where everything is measured from), one
 * row per strategy in the order the API switched them on, and the total. Each strategy's bar starts where the one before
 * it ended (the API's running total), so the bars join up and the last one ends on the total.
 */
export function waterfallRows(analysis: ShowcaseAnalysis): WaterfallRow[] {
  const rows: WaterfallRow[] = [
    {
      kind: "start",
      key: "start",
      label: analysis.advisor_label,
      detail: "",
      enabled: true,
      from: ZERO,
      to: ZERO,
      delta: ZERO,
    },
  ];
  let before = ZERO;
  for (const bar of analysis.bars) {
    const after: Amount = { rate: bar.cumulative_rate, dollars: bar.cumulative_dollars };
    rows.push({
      kind: "strategy",
      key: bar.key,
      label: bar.label,
      detail: bar.detail,
      enabled: bar.enabled,
      from: before,
      to: after,
      delta: { rate: bar.delta_rate, dollars: bar.delta_dollars },
    });
    before = after;
  }
  const total: Amount = { rate: analysis.advantage.median_rate, dollars: analysis.advantage.median_dollars };
  rows.push({
    kind: "total",
    key: "total",
    label: "Donabach",
    detail: "",
    enabled: true,
    from: ZERO,
    to: total,
    delta: total,
  });
  return rows;
}

export type { Axis };

/**
 * The axis for one unit, from zero (the advisor's result) in clean steps. It has to hold every bar of every analysis given
 * (the analysis on screen, and the one with everything on, so switching a strategy off shrinks its bar against a scale that
 * stays put), and a strategy that lowers the total reaches below zero. A narrow chart asks for fewer intervals, so its tick
 * labels never touch.
 */
export function axisFor(unit: Unit, analyses: readonly ShowcaseAnalysis[], maxIntervals = 6): Axis {
  const values = [0, ...analyses.flatMap((a) => waterfallRows(a).flatMap((row) => [row.from[unit], row.to[unit]]))];
  return niceAxis(Math.min(...values), Math.max(...values), maxIntervals);
}

/** Where a value falls on an axis, as a percentage of its width. */
export const place = (axis: Axis, value: number): number => ((value - axis.min) / (axis.max - axis.min)) * 100;

/** "+0.53%", "−0.04%", "0.00%": a yearly rate with three decimals under 0.1% a year, as elsewhere in the app. */
export const ratePercent = (rate: number): string => signedPercent(rate, rate === 0 ? 2 : rateDigits(rate));

/** "+0.53% a year". */
export const rateText = (rate: number): string => `${ratePercent(rate)} a year`;

/** "+$720k at 80". */
export const dollarsText = (dollars: number, horizon: number): string => `${signedMoney(dollars)} at ${horizon}`;

/** A tick on the axis: dollars the way the app writes them, a rate without trailing zeros ("1%", "0.5%"). */
export function tickText(unit: Unit, value: number): string {
  if (unit === "dollars") return money(value);
  const percent = Number((Math.abs(value) * 100).toFixed(2));
  return `${value < 0 ? "−" : ""}${percent}%`;
}

/** What the axis measures, in words. */
export function axisCaption(unit: Unit, horizon: number): string {
  return unit === "dollars"
    ? `Change in median after-tax wealth at ${horizon}, in 2026 dollars, from the advisor's result`
    : "Change in the yearly growth rate of median after-tax wealth, from the advisor's result";
}

/** The strategy that adds the most dollars of the ones that are on, if any adds anything. */
export function biggestStep(analysis: ShowcaseAnalysis) {
  const on = analysis.bars.filter((bar) => bar.enabled);
  const best = on.reduce<(typeof on)[number] | undefined>(
    (top, bar) => (top === undefined || bar.delta_dollars > top.delta_dollars ? bar : top),
    undefined,
  );
  return best && best.delta_dollars > 0 ? best : undefined;
}
