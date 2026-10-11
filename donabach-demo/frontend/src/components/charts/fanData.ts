import type { FanSeries } from "@/lib/types";

/** Quantiles of one quantity by age: the shape of FanSeries and IncomeForecast alike. */
export type Quantiles = Pick<FanSeries, "ages" | "p10" | "p25" | "p50" | "p75" | "p90">;

export interface QuantileValues {
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

/** One line (median) with its bands, as the fan chart draws it. */
export interface FanLineSpec {
  /** Stable per entity: colors and data keys follow it, never the position in the list. */
  id: string;
  /** Full name for the legend and the tooltip. */
  name: string;
  /** Short name beside the line's end. */
  endName: string;
  /** A CSS color (a series token). */
  color: string;
  fan: Quantiles;
  /** Also draw the darker 25th-to-75th percentile band. */
  innerBand?: boolean;
  /** Lines of detail under this line's median in the tooltip. */
  details?: (q: QuantileValues) => string[];
}

export type FanRow = { age: number } & { [key: string]: unknown };

export const medianKey = (id: string) => `${id}_p50`;
export const outerKey = (id: string) => `${id}_outer`;
export const innerKey = (id: string) => `${id}_inner`;
export const quantileKey = (id: string) => `${id}_q`;

/** Quantile values of one line at index `i`. */
export function quantilesAt(fan: Quantiles, i: number): QuantileValues {
  return { p10: fan.p10[i], p25: fan.p25[i], p50: fan.p50[i], p75: fan.p75[i], p90: fan.p90[i] };
}

/**
 * One row per age for Recharts. Bands are [low, high] pairs (a range area); the whole set of
 * quantiles rides along on each row so the tooltip can list every series at that age.
 */
export function buildFanRows(lines: readonly FanLineSpec[]): FanRow[] {
  const ages = Array.from(new Set(lines.flatMap((line) => line.fan.ages))).sort((a, b) => a - b);
  const indexOfAge = lines.map((line) => new Map(line.fan.ages.map((age, i) => [age, i] as const)));
  return ages.map((age) => {
    const row: FanRow = { age };
    lines.forEach((line, li) => {
      const i = indexOfAge[li].get(age);
      if (i === undefined) return;
      const q = quantilesAt(line.fan, i);
      row[medianKey(line.id)] = q.p50;
      row[outerKey(line.id)] = [q.p10, q.p90];
      row[innerKey(line.id)] = [q.p25, q.p75];
      row[quantileKey(line.id)] = q;
    });
    return row;
  });
}
