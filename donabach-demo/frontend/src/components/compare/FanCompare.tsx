"use client";

import { useMemo } from "react";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { ChartLegend, type LegendItem } from "@/components/charts/ChartLegend";
import { CHART_HEIGHT, SERIES_DONABACH, SERIES_RIA } from "@/components/charts/chartTheme";
import { buildFanRows, quantilesAt, type FanLineSpec, type QuantileValues } from "@/components/charts/fanData";
import { FanChart } from "@/components/charts/FanChart";
import { DataTable, type DataColumn } from "@/components/ui";
import { money } from "@/lib/format";
import type { PlanResponse } from "@/lib/types";
import styles from "./Compare.module.css";

const details = (q: QuantileValues) => [`Bad case ${money(q.p10)}, good case ${money(q.p90)}`];

const LEGEND: LegendItem[] = [
  { id: "donabach", kind: "bandLine", color: SERIES_DONABACH, label: "Donabach plan" },
  { id: "ria", kind: "bandLine", color: SERIES_RIA, label: "Typical advisor (a good traditional RIA)" },
];

interface Row {
  age: number;
  donabach: QuantileValues;
  ria: QuantileValues;
}

const stack = (top: string, bottom: string) => (
  <>
    {top}
    <br />
    {bottom}
  </>
);

const COLUMNS: DataColumn<Row>[] = [
  { key: "age", header: "Age", rowHeader: true, width: "9%", cell: (r) => r.age },
  { key: "d50", header: stack("Donabach", "typical"), align: "end", cell: (r) => money(r.donabach.p50) },
  { key: "d10", header: stack("Donabach", "bad case"), align: "end", cell: (r) => money(r.donabach.p10) },
  { key: "d90", header: stack("Donabach", "good case"), align: "end", cell: (r) => money(r.donabach.p90) },
  { key: "r50", header: stack("Advisor", "typical"), align: "end", cell: (r) => money(r.ria.p50) },
  { key: "r10", header: stack("Advisor", "bad case"), align: "end", cell: (r) => money(r.ria.p10) },
  { key: "r90", header: stack("Advisor", "good case"), align: "end", cell: (r) => money(r.ria.p90) },
];

/**
 * After-tax wealth by age for the plan and for a good traditional advisor, on the same simulated
 * futures: a median line for each with a 10th-to-90th percentile band around it.
 */
export function FanCompare({ plan }: { plan: PlanResponse }) {
  const lines = useMemo<FanLineSpec[]>(
    () => [
      { id: "donabach", name: "Donabach plan", endName: "Donabach", color: SERIES_DONABACH, fan: plan.fan, details },
      { id: "ria", name: "Typical advisor", endName: "Advisor", color: SERIES_RIA, fan: plan.ria_fan, details },
    ],
    [plan.fan, plan.ria_fan],
  );
  const rows = useMemo(() => buildFanRows(lines), [lines]);
  const tableRows = useMemo<Row[]>(
    () =>
      plan.fan.ages.map((age, i) => ({
        age,
        donabach: quantilesAt(plan.fan, i),
        ria: quantilesAt(plan.ria_fan, plan.ria_fan.ages.indexOf(age)),
      })),
    [plan.fan, plan.ria_fan],
  );

  return (
    <ChartFrame
      label="After-tax wealth by age: Donabach plan and typical advisor, median with a 10th to 90th percentile band each"
      legend={
        <div className={styles.legendStack}>
          <ChartLegend items={LEGEND} />
          <p className={styles.legendNote}>
            Each line is the median future. The shaded band around it runs from the 10th to the 90th percentile, so 8 in 10
            futures end inside it.
          </p>
        </div>
      }
      chart={<FanChart lines={lines} rows={rows} height={CHART_HEIGHT} />}
      table={
        <DataTable
          columns={COLUMNS}
          rows={tableRows}
          rowKey={(r) => r.age}
          caption="After-tax wealth by age for the Donabach plan and a typical advisor: typical, bad case (10th percentile) and good case (90th percentile)"
          height={CHART_HEIGHT}
          dense
        />
      }
    />
  );
}
