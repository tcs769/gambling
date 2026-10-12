// The four lines of the wealth chart, and the rows they are drawn from. Nothing here is computed: every value is the API's.

import { SERIES_DONABACH, SERIES_RIA, type LineStyle } from "@/components/charts/chartTheme";
import type { ShowcaseWealth } from "@/lib/types";

export type WealthKey = "planMedian" | "planP10" | "advisorMedian" | "advisorP10";

export interface WealthSeries {
  key: WealthKey;
  /** The whole name, for the legend, the tooltip and the table. */
  name: string;
  /** Beside the end of the line: the entity and, for the bad market, which line it is. */
  endName: string;
  /** Table heading, in two short lines. */
  heading: [string, string];
  color: string;
  /** The median is solid, the 10th percentile dashed: line style says which is which when colour cannot. */
  lineStyle: LineStyle;
}

/**
 * Donabach and the advisor are the two entities, each in its own colour (the app's series colours: amber for Donabach,
 * blue for the good advisor, as on the Comparison screen). For each, the typical future (the median) is a solid line and a
 * bad-market future (the 10th percentile) a dashed one in the same colour. Advisor lines are listed first so they are
 * drawn first, and Donabach's end up on top.
 */
export function wealthSeries(advisorLabel: string): WealthSeries[] {
  return [
    {
      key: "advisorP10",
      name: `${advisorLabel}, bad market (10th percentile)`,
      endName: `${advisorLabel}, bad market`,
      heading: [advisorLabel, "bad market"],
      color: SERIES_RIA,
      lineStyle: "dashed",
    },
    {
      key: "advisorMedian",
      name: `${advisorLabel}, typical (median)`,
      endName: `${advisorLabel}, typical`,
      heading: [advisorLabel, "typical"],
      color: SERIES_RIA,
      lineStyle: "solid",
    },
    {
      key: "planP10",
      name: "Donabach, bad market (10th percentile)",
      endName: "Donabach, bad market",
      heading: ["Donabach", "bad market"],
      color: SERIES_DONABACH,
      lineStyle: "dashed",
    },
    {
      key: "planMedian",
      name: "Donabach, typical (median)",
      endName: "Donabach, typical",
      heading: ["Donabach", "typical"],
      color: SERIES_DONABACH,
      lineStyle: "solid",
    },
  ];
}

export interface WealthRow {
  age: number;
  planMedian: number;
  planP10: number;
  advisorMedian: number;
  advisorP10: number;
}

/** One row per age, today's age first, from the API's parallel lists. */
export function wealthRows(wealth: ShowcaseWealth): WealthRow[] {
  const lines = wealth.wealth;
  return lines.ages.map((age, i) => ({
    age,
    planMedian: lines.plan_median[i],
    planP10: lines.plan_p10[i],
    advisorMedian: lines.advisor_median[i],
    advisorP10: lines.advisor_p10[i],
  }));
}
