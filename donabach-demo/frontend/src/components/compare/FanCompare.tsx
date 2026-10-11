"use client";

import { useMemo } from "react";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { ChartLegend, type LegendItem } from "@/components/charts/ChartLegend";
import {
  CHART_HEIGHT,
  LIGHT_BAND_OPACITY,
  SERIES_ADAPTIVE,
  SERIES_DONABACH,
  SERIES_RIA,
  SERIES_TYPICAL,
} from "@/components/charts/chartTheme";
import { buildFanRows, quantilesAt, type FanLineSpec, type QuantileValues } from "@/components/charts/fanData";
import { FanChart } from "@/components/charts/FanChart";
import { DataTable, type DataColumn } from "@/components/ui";
import { money } from "@/lib/format";
import type { AdaptiveState } from "@/lib/state";
import { baselineOf, type FanSeries, type PlanResponse, type StrategyKey } from "@/lib/types";
import styles from "./Compare.module.css";

/** Room at the right for "$1.83M Typical advisor" and "$1.98M Adaptive planner": the longest end labels on this chart. */
const END_LABEL_ROOM = 214;

/** What the legend says for the adaptive line before the year-by-year plan is known (the room is kept, nothing is drawn). */
const ADAPTIVE_NAME = "Adaptive planner";

/** A stand-in for the adaptive planner's clause in the text alternative while it is not known: never shown or read. */
const RESERVED_ENDING = "$0.00M with the adaptive planner";

const details = (q: QuantileValues) => [`Bad case ${money(q.p10)}, good case ${money(q.p90)}`];

/** The median's value at the last age of a fan: where the line ends. */
const endMedian = (fan: FanSeries) => fan.p50[fan.p50.length - 1];

interface Row {
  age: number;
  /** Quantiles of each line at this age, by line id. */
  at: Record<string, QuantileValues | undefined>;
}

const stack = (top: string, bottom: string) => (
  <>
    {top}
    <br />
    {bottom}
  </>
);

/** The table twin: exactly what the chart draws (a median for every line, a band for the lines that have one). */
function columnsFor(lines: readonly FanLineSpec[]): DataColumn<Row>[] {
  const columns: DataColumn<Row>[] = [{ key: "age", header: "Age", rowHeader: true, width: "8%", cell: (r) => r.age }];
  for (const line of lines) {
    columns.push({ key: `${line.id}-p50`, header: stack(line.endName, "typical"), align: "end", cell: (r) => money(r.at[line.id]?.p50) });
    if ((line.bandOpacity ?? 1) > 0) {
      columns.push({ key: `${line.id}-p10`, header: stack(line.endName, "bad case"), align: "end", cell: (r) => money(r.at[line.id]?.p10) });
      columns.push({ key: `${line.id}-p90`, header: stack(line.endName, "good case"), align: "end", cell: (r) => money(r.at[line.id]?.p90) });
    }
  }
  return columns;
}

/**
 * After-tax wealth by age on the same fresh simulated futures: a median line for the Donabach plan (the best fixed
 * strategy) and for both advisors, and, once the year-by-year plan is known, for the adaptive planner too (dotted).
 * A 10th-to-90th percentile band surrounds the plan, and a lighter one the good RIA and the adaptive planner; the
 * typical advisor is the dashed line with no band, so overlapping bands never hide each other. While the
 * year-by-year plan is being refined the chart shows the three lines it already has and keeps the legend's room for
 * the fourth.
 */
export function FanCompare({ plan, adaptive }: { plan: PlanResponse; adaptive?: AdaptiveState }) {
  const section = adaptive?.status === "ready" ? adaptive.section : undefined;
  const refining = adaptive?.status === "refining";
  // With the year-by-year plan known, every line comes from its four strategies (one source for the chart and the
  // comparison panels); until then the plan's own fan and the two advisors' are what there is.
  const strategy = (key: StrategyKey) => section?.strategies.find((s) => s.key === key);
  const fixed = strategy("best_fixed");
  const adapt = strategy("adaptive");
  const good = baselineOf(plan, "good_ria");
  const typical = baselineOf(plan, "typical_advisor");
  const goodFan = strategy("good_ria")?.fan ?? good?.fan;
  const typicalFan = strategy("typical_advisor")?.fan ?? typical?.fan;
  const fixedFan = fixed?.fan ?? plan.fan;

  const lines = useMemo<FanLineSpec[]>(() => {
    const out: FanLineSpec[] = [
      { id: "donabach", name: "Donabach plan", endName: "Donabach", color: SERIES_DONABACH, fan: fixedFan, details },
    ];
    if (adapt) {
      // Drawn on top of the plan's line: the two run close together, and the dots show over the solid line.
      out.push({
        id: adapt.key,
        name: adapt.label,
        endName: adapt.label,
        color: SERIES_ADAPTIVE,
        lineStyle: "dotted",
        bandOpacity: LIGHT_BAND_OPACITY,
        layer: 1,
        fan: adapt.fan,
        details,
      });
    }
    if (good && goodFan) {
      out.push({
        id: good.key,
        name: good.label,
        endName: good.label,
        color: SERIES_RIA,
        bandOpacity: LIGHT_BAND_OPACITY,
        fan: goodFan,
        details,
      });
    }
    if (typical && typicalFan) {
      // Drawn above the good RIA (the two run close together), under the plan: where they overlap the dashes still show.
      out.push({
        id: typical.key,
        name: typical.label,
        endName: typical.label,
        color: SERIES_TYPICAL,
        lineStyle: "dashed",
        bandOpacity: 0,
        layer: -0.5,
        fan: typicalFan,
      });
    }
    return out;
  }, [fixedFan, adapt, good, goodFan, typical, typicalFan]);

  const rows = useMemo(() => buildFanRows(lines), [lines]);
  const columns = useMemo(() => columnsFor(lines), [lines]);
  // Every heading word ("Donabach" is the longest) has to fit its column, so a narrow window scrolls the table sideways
  // inside its panel instead of cutting words off: about 88px a column, the age column taking 8% of the width.
  const tableMinWidth = Math.ceil(((columns.length - 1) * 88) / 0.92);
  const tableRows = useMemo<Row[]>(
    () =>
      fixedFan.ages.map((age) => ({
        age,
        at: Object.fromEntries(
          lines.map((line) => {
            const i = line.fan.ages.indexOf(age);
            return [line.id, i < 0 ? undefined : quantilesAt(line.fan, i)] as const;
          }),
        ),
      })),
    [fixedFan.ages, lines],
  );

  const legend = useMemo<LegendItem[]>(() => {
    const items: LegendItem[] = lines.map((line) => ({
      id: line.id,
      kind: (line.bandOpacity ?? 1) === 0 ? "line" : "bandLine",
      color: line.color,
      lineStyle: line.lineStyle,
      bandOpacity: line.bandOpacity,
      label: line.name,
    }));
    if (refining) {
      // The adaptive line is on its way: its place in the legend is kept (not drawn), so nothing moves when it arrives.
      items.splice(1, 0, {
        id: "adaptive-pending",
        kind: "bandLine",
        color: SERIES_ADAPTIVE,
        lineStyle: "dotted",
        bandOpacity: LIGHT_BAND_OPACITY,
        label: ADAPTIVE_NAME,
        reserved: true,
      });
    }
    return items;
  }, [lines, refining]);

  // The figure's text alternative: where each line ends. With the adaptive planner and without it are two wordings
  // stacked in one cell (see `stacked`), so the line of text it gains does not move the page when the line arrives.
  const endAge = fixedFan.ages[fixedFan.ages.length - 1];
  const sentence = (endings: (string | false | undefined)[]) => {
    const parts = endings.filter((ending): ending is string => !!ending);
    return `At age ${endAge} the median after-tax wealth is ${
      parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}` : parts[0]
    }.`;
  };
  const planEnding = `${money(endMedian(fixedFan))} with the Donabach plan`;
  const goodEnding = good && goodFan && `${money(endMedian(goodFan))} with a good RIA`;
  const typicalEnding = typical && typicalFan && `${money(endMedian(typicalFan))} with a typical advisor`;
  const withoutAdaptive = sentence([planEnding, goodEnding, typicalEnding]);
  const withAdaptive = adapt
    ? sentence([planEnding, `${money(endMedian(adapt.fan))} with the adaptive planner`, goodEnding, typicalEnding])
    : // what it will say when the line arrives, with a stand-in figure of the same length: it only holds the room
      sentence([planEnding, RESERVED_ENDING, goodEnding, typicalEnding]);
  const summary = (
    <span className={styles.stacked}>
      <span data-active={!adapt} aria-hidden={adapt ? true : undefined}>
        {withoutAdaptive}
      </span>
      <span data-active={!!adapt} aria-hidden={adapt ? undefined : true}>
        {withAdaptive}
      </span>
    </span>
  );

  return (
    <ChartFrame
      label={`After-tax wealth by age: the Donabach plan with a 10th to 90th percentile band, ${
        adapt ? "the adaptive planner as a dotted line with a lighter band, " : ""
      }a good RIA with a lighter band, and a typical advisor as a dashed median line`}
      summary={summary}
      legend={
        <div className={styles.legendStack}>
          <ChartLegend items={legend} label="Chart legend" />
          {/* All three wordings share one cell, so the legend note is as tall as the tallest and the chart never moves. */}
          <div className={styles.stacked}>
            <p className={styles.legendNote} data-active={!adapt && !refining}>
              Each line is the median future. The shaded band around the Donabach plan runs from the 10th to the 90th
              percentile, so 8 in 10 futures end inside it; the good RIA has the same band, lighter. The typical advisor is
              the dashed line, with no band.
            </p>
            <p className={styles.legendNote} data-active={!!adapt}>
              Each line is the median future. The shaded band around the Donabach plan runs from the 10th to the 90th
              percentile, so 8 in 10 futures end inside it; the good RIA and the adaptive planner have the same band,
              lighter. The typical advisor is the dashed line, with no band; the adaptive planner is the dotted line.
            </p>
            <p className={styles.legendNote} data-active={refining}>
              Each line is the median future. The shaded band around the Donabach plan runs from the 10th to the 90th
              percentile, so 8 in 10 futures end inside it; the good RIA and the adaptive planner have the same band,
              lighter. The typical advisor is the dashed line, with no band; the adaptive planner&apos;s dotted line joins
              when the year-by-year plan is ready.
            </p>
          </div>
        </div>
      }
      chart={<FanChart lines={lines} rows={rows} height={CHART_HEIGHT} endLabelRoom={END_LABEL_ROOM} />}
      table={
        <DataTable
          columns={columns}
          rows={tableRows}
          rowKey={(r) => r.age}
          caption={`After-tax wealth by age: the median for the Donabach plan${adapt ? ", the adaptive planner" : ""}, a good RIA and a typical advisor, with the bad case (10th percentile) and good case (90th percentile) for every line but the typical advisor's`}
          height={CHART_HEIGHT}
          minWidth={tableMinWidth}
          dense
        />
      }
    />
  );
}
