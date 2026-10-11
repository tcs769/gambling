"use client";

import { useMemo } from "react";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { ChartLegend, type LegendItem } from "@/components/charts/ChartLegend";
import {
  CHART_HEIGHT,
  LIGHT_BAND_OPACITY,
  SERIES_DONABACH,
  SERIES_RIA,
  SERIES_TYPICAL,
} from "@/components/charts/chartTheme";
import { buildFanRows, quantilesAt, type FanLineSpec, type QuantileValues } from "@/components/charts/fanData";
import { FanChart } from "@/components/charts/FanChart";
import { DataTable, type DataColumn } from "@/components/ui";
import { money } from "@/lib/format";
import { baselineOf, type FanSeries, type PlanResponse } from "@/lib/types";
import styles from "./Compare.module.css";

/** Room at the right for "$1.83M Typical advisor": the longest end label on this chart. */
const END_LABEL_ROOM = 210;

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
 * After-tax wealth by age for the plan and for both advisors, on the same fresh simulated futures:
 * a median line for each, a 10th-to-90th percentile band around the plan's and (lighter) around the
 * good RIA's, and the typical advisor as a dashed line with no band, so three overlapping bands never
 * hide each other.
 */
export function FanCompare({ plan }: { plan: PlanResponse }) {
  const good = baselineOf(plan, "good_ria");
  const typical = baselineOf(plan, "typical_advisor");

  const lines = useMemo<FanLineSpec[]>(() => {
    const out: FanLineSpec[] = [
      { id: "donabach", name: "Donabach plan", endName: "Donabach", color: SERIES_DONABACH, fan: plan.fan, details },
    ];
    if (good) {
      out.push({
        id: good.key,
        name: good.label,
        endName: good.label,
        color: SERIES_RIA,
        bandOpacity: LIGHT_BAND_OPACITY,
        fan: good.fan,
        details,
      });
    }
    if (typical) {
      // Drawn above the good RIA (the two run close together), under the plan: where they overlap the dashes still show.
      out.push({
        id: typical.key,
        name: typical.label,
        endName: typical.label,
        color: SERIES_TYPICAL,
        dashed: true,
        bandOpacity: 0,
        layer: -0.5,
        fan: typical.fan,
      });
    }
    return out;
  }, [plan.fan, good, typical]);

  const rows = useMemo(() => buildFanRows(lines), [lines]);
  const columns = useMemo(() => columnsFor(lines), [lines]);
  const tableRows = useMemo<Row[]>(
    () =>
      plan.fan.ages.map((age) => ({
        age,
        at: Object.fromEntries(
          lines.map((line) => {
            const i = line.fan.ages.indexOf(age);
            return [line.id, i < 0 ? undefined : quantilesAt(line.fan, i)] as const;
          }),
        ),
      })),
    [plan.fan.ages, lines],
  );

  const legend = useMemo<LegendItem[]>(
    () =>
      lines.map((line) => ({
        id: line.id,
        kind: line.dashed ? "line" : "bandLine",
        color: line.color,
        dashed: line.dashed,
        bandOpacity: line.bandOpacity,
        label: line.name,
      })),
    [lines],
  );

  // The figure's text alternative: where each line ends.
  const endAge = plan.fan.ages[plan.fan.ages.length - 1];
  const endings = [
    `${money(endMedian(plan.fan))} with the Donabach plan`,
    good && `${money(endMedian(good.fan))} with a good RIA`,
    typical && `${money(endMedian(typical.fan))} with a typical advisor`,
  ].filter((ending): ending is string => !!ending);
  const summary = `At age ${endAge} the median after-tax wealth is ${
    endings.length > 1 ? `${endings.slice(0, -1).join(", ")} and ${endings[endings.length - 1]}` : endings[0]
  }.`;

  return (
    <ChartFrame
      label="After-tax wealth by age: the Donabach plan with a 10th to 90th percentile band, a good RIA with a lighter band, and a typical advisor as a dashed median line"
      summary={summary}
      legend={
        <div className={styles.legendStack}>
          <ChartLegend items={legend} label="Chart legend" />
          <p className={styles.legendNote}>
            Each line is the median future. The shaded band around the plan runs from the 10th to the 90th percentile, so 8
            in 10 futures end inside it; the good RIA has the same band, lighter. The typical advisor is the dashed line,
            with no band.
          </p>
        </div>
      }
      chart={<FanChart lines={lines} rows={rows} height={CHART_HEIGHT} endLabelRoom={END_LABEL_ROOM} />}
      table={
        <DataTable
          columns={columns}
          rows={tableRows}
          rowKey={(r) => r.age}
          caption="After-tax wealth by age: the median for the Donabach plan, a good RIA and a typical advisor, with the bad case (10th percentile) and good case (90th percentile) for the plan and the good RIA"
          height={CHART_HEIGHT}
          dense
        />
      }
    />
  );
}
