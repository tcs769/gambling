"use client";

import { useMemo } from "react";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { ChartLegend, type LegendItem } from "@/components/charts/ChartLegend";
import { CHART_HEIGHT } from "@/components/charts/chartTheme";
import { DataTable, type DataColumn } from "@/components/ui";
import { money } from "@/lib/format";
import type { ShowcaseWealth } from "@/lib/types";
import { useElementWidth } from "./useElementWidth";
import { WealthChart } from "./WealthChart";
import { wealthRows, wealthSeries, type WealthRow, type WealthSeries } from "./wealthData";
import styles from "./WealthFigure.module.css";

/** Room at the right for "$942k Good advisor, bad market", the longest end label. */
const END_LABEL_ROOM = 262;
/** Below this width the end labels would leave no room for the lines: the legend and the tooltip name them instead. */
const ROOM_FOR_END_LABELS = 640;

const stack = (top: string, bottom: string) => (
  <>
    {top}
    <br />
    {bottom}
  </>
);

/** The table twin: exactly the four lines the chart draws, a row for every age. */
function columnsFor(series: readonly WealthSeries[]): DataColumn<WealthRow>[] {
  return [
    { key: "age", header: "Age", rowHeader: true, width: "12%", cell: (row) => row.age },
    ...[...series].reverse().map(
      (line): DataColumn<WealthRow> => ({
        key: line.key,
        header: stack(...line.heading),
        align: "end",
        cell: (row) => money(row[line.key]),
      }),
    ),
  ];
}

/**
 * Wealth over time against the advisor: the chart (Donabach and the advisor, each as a typical and a bad-market line),
 * its legend with a line on what the dashed lines are, the same numbers as a table, and in words where each line ends.
 */
export function WealthFigure({ wealth }: { wealth: ShowcaseWealth }) {
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const series = useMemo(() => wealthSeries(wealth.advisor_label), [wealth.advisor_label]);
  const rows = useMemo(() => wealthRows(wealth), [wealth]);
  const columns = useMemo(() => columnsFor(series), [series]);
  const advisor = wealth.advisor_label.toLowerCase();
  const { advantage, horizon_age: horizon } = wealth;

  // Donabach's lines first in the legend (the chart draws them last, on top).
  const legend: LegendItem[] = [...series].reverse().map((line) => ({
    id: line.key,
    kind: "line",
    color: line.color,
    lineStyle: line.lineStyle,
    label: line.name,
  }));

  return (
    <ChartFrame
      label={`After-tax wealth by age: Donabach and a ${advisor}, each as a solid line for the typical (median) future and a dashed line for a bad-market (10th percentile) future`}
      summary={
        <>
          At age {horizon} the typical (median) after-tax wealth is {money(advantage.plan_median_at_horizon)} with
          Donabach and {money(advantage.advisor_median_at_horizon)} with a {advisor}. In a bad market (the 10th
          percentile) it is {money(advantage.plan_p10_at_horizon)} and {money(advantage.advisor_p10_at_horizon)}.
        </>
      }
      legend={
        <div className={styles.legendStack}>
          <ChartLegend items={legend} label="Chart legend" />
          <p className={styles.legendNote}>
            Solid lines are the typical (median) future. Dashed lines are a bad-market future, the 10th percentile: nine
            in ten futures do better.
          </p>
        </div>
      }
      wrapToolbar
      chart={
        <div ref={measure} className={styles.chartBox}>
          <WealthChart
            rows={rows}
            series={series}
            height={CHART_HEIGHT}
            endLabelRoom={width >= ROOM_FOR_END_LABELS ? END_LABEL_ROOM : 0}
          />
        </div>
      }
      table={
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.age}
          caption={`After-tax wealth by age: the typical (median) and the bad-market (10th percentile) future for Donabach and a ${advisor}`}
          height={CHART_HEIGHT}
          minWidth={560}
          dense
        />
      }
    />
  );
}
