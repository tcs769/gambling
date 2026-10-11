"use client";

import { useMemo } from "react";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { ChartLegend, type LegendItem } from "@/components/charts/ChartLegend";
import { CHART_HEIGHT, SERIES_DONABACH } from "@/components/charts/chartTheme";
import { buildFanRows, quantilesAt, type FanLineSpec } from "@/components/charts/fanData";
import { FanChart } from "@/components/charts/FanChart";
import { DataTable, type DataColumn } from "@/components/ui";
import { money } from "@/lib/format";
import type { IncomeForecast } from "@/lib/types";

const LEGEND: LegendItem[] = [
  { id: "median", kind: "line", color: SERIES_DONABACH, label: "Median (half of futures above, half below)" },
  { id: "inner", kind: "innerBand", color: SERIES_DONABACH, label: "Middle half of futures (25th to 75th percentile)" },
  { id: "outer", kind: "band", color: SERIES_DONABACH, label: "Middle 8 in 10 futures (10th to 90th percentile)" },
];

interface Row {
  age: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

const COLUMNS: DataColumn<Row>[] = [
  { key: "age", header: "Age", rowHeader: true, width: "12%", cell: (r) => r.age },
  { key: "p10", header: "Low (10th percentile)", align: "end", cell: (r) => money(r.p10) },
  { key: "p25", header: "25th percentile", align: "end", cell: (r) => money(r.p25) },
  { key: "p50", header: "Median", align: "end", cell: (r) => money(r.p50) },
  { key: "p75", header: "75th percentile", align: "end", cell: (r) => money(r.p75) },
  { key: "p90", header: "High (90th percentile)", align: "end", cell: (r) => money(r.p90) },
];

/** Household income by age as a fan: median line, a darker middle-half band and a wider band. */
export function ForecastChart({ forecast }: { forecast: IncomeForecast }) {
  const lines = useMemo<FanLineSpec[]>(
    () => [
      {
        id: "income",
        name: "Median",
        endName: "median",
        color: SERIES_DONABACH,
        fan: forecast,
        innerBand: true,
        details: (q) => [
          `Middle half of futures: ${money(q.p25)} to ${money(q.p75)}`,
          `Middle 8 in 10: ${money(q.p10)} to ${money(q.p90)}`,
        ],
      },
    ],
    [forecast],
  );
  const rows = useMemo(() => buildFanRows(lines), [lines]);
  const tableRows = useMemo<Row[]>(
    () => forecast.ages.map((age, i) => ({ age, ...quantilesAt(forecast, i) })),
    [forecast],
  );

  return (
    <ChartFrame
      label="Household income by age: median with bands for the middle half and the middle 8 in 10 simulated futures"
      legend={<ChartLegend items={LEGEND} />}
      chart={<FanChart lines={lines} rows={rows} height={CHART_HEIGHT} endLabelRoom={130} />}
      table={
        <DataTable
          columns={COLUMNS}
          rows={tableRows}
          rowKey={(r) => r.age}
          caption="Household income by age: median and percentiles of simulated futures"
          height={CHART_HEIGHT}
          dense
        />
      }
    />
  );
}
