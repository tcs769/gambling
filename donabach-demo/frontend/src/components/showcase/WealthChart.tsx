"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  useXAxisScale,
  useYAxisScale,
} from "recharts";
import { spreadLabels } from "@/components/charts/FanChart";
import {
  ANIMATION_MS,
  GRID_STROKE,
  SURFACE,
  TICK_STYLE,
  ageTicks,
  lineStroke,
  niceScale,
} from "@/components/charts/chartTheme";
import { money } from "@/lib/format";
import { WealthTooltip } from "./WealthTooltip";
import type { WealthRow, WealthSeries } from "./wealthData";

/** Fewer age labels for a narrow chart: the first age, then every tenth year, never two labels closer than five years. */
function compactAgeTicks(ages: readonly number[]): number[] {
  if (ages.length === 0) return [];
  const ticks = [ages[0]];
  for (const age of ages) {
    if (age % 10 === 0 && age - ticks[ticks.length - 1] >= 5) ticks.push(age);
  }
  const last = ages[ages.length - 1];
  if (last - ticks[ticks.length - 1] >= 5) ticks.push(last);
  return ticks;
}

/** Two end labels closer than this (in pixels) are moved apart, and joined to their lines by a short leader. */
const END_LABEL_GAP = 22;

/**
 * The value and name at the right end of each line, with a short stroke in the line's colour and style beside it. Where
 * two lines end close together their labels are moved apart (as little as possible) and a thin leader joins each label to
 * the end of its line, so a moved label never loses its line. Text stays in text colours.
 */
function EndLabels({ series, last }: { series: readonly WealthSeries[]; last: WealthRow | undefined }) {
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  if (!xScale || !yScale || !last) return null;
  const x = xScale(last.age);
  if (x === undefined) return null;
  const placed = series.flatMap((line) => {
    const y = yScale(last[line.key]);
    return y === undefined ? [] : [{ line, y, value: last[line.key] }];
  });
  const ys = spreadLabels(
    placed.map((p) => p.y),
    END_LABEL_GAP,
  );
  return (
    <g>
      {placed.map(({ line, y, value }, i) => (
        <g
          key={line.key}
          style={{ transform: `translate(${x}px, ${ys[i]}px)`, transition: `transform ${ANIMATION_MS}ms ease-in-out` }}
        >
          {Math.abs(ys[i] - y) > 1 && (
            <polyline points={`0,${y - ys[i]} 9,0`} fill="none" stroke="var(--muted)" strokeWidth={1} />
          )}
          <line x1="9" y1="0" x2="23" y2="0" stroke={line.color} {...lineStroke(line.lineStyle, "key")} />
          <text x="30" y="0" dy="0.35em" fontSize="14" fill="var(--muted-text)">
            <tspan fontWeight="700" fill="var(--espresso)">
              {money(value)}
            </tspan>
            <tspan dx="6">{line.endName}</tspan>
          </text>
        </g>
      ))}
    </g>
  );
}

interface WealthChartProps {
  rows: WealthRow[];
  /** Listed bottom to top: the last is drawn on top. */
  series: readonly WealthSeries[];
  height: number;
  /** Pixels reserved at the right for the end labels (0: a narrow chart has none, and the legend and tooltip carry the names). */
  endLabelRoom: number;
}

/**
 * After-tax wealth by age, from today to the horizon: four lines, two for each of the two entities. A crosshair follows the
 * cursor and the tooltip lists all four at that age (the arrow keys do the same when the chart has focus). Use inside a
 * ChartFrame, which supplies the legend and the table twin.
 */
export function WealthChart({ rows, series, height, endLabelRoom }: WealthChartProps) {
  const last = rows[rows.length - 1];
  const { ticks, domainMax } = useMemo(
    () => niceScale(Math.max(0, ...rows.flatMap((row) => series.map((line) => row[line.key])))),
    [rows, series],
  );
  const ages = useMemo(() => rows.map((row) => row.age), [rows]);
  return (
    <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 900, height }}>
      <LineChart data={rows} margin={{ top: 14, right: endLabelRoom > 0 ? endLabelRoom : 16, bottom: 4, left: 4 }}>
        <CartesianGrid vertical={false} stroke={GRID_STROKE} strokeWidth={1} />
        <XAxis
          dataKey="age"
          ticks={endLabelRoom > 0 ? ageTicks(ages) : compactAgeTicks(ages)}
          interval={0}
          tick={TICK_STYLE}
          tickLine={false}
          axisLine={{ stroke: GRID_STROKE, strokeWidth: 1 }}
          tickMargin={8}
          height={54}
          label={{ value: "Age", position: "insideBottom", offset: 2, fill: "var(--muted-text)", fontSize: 14 }}
        />
        <YAxis
          width={66}
          domain={[0, domainMax]}
          ticks={ticks}
          interval={0}
          tickFormatter={(value: number) => money(value)}
          tick={TICK_STYLE}
          tickLine={false}
          axisLine={false}
        />
        {series.map((line) => (
          <Line
            key={line.key}
            type="monotone"
            dataKey={line.key}
            stroke={line.color}
            strokeLinejoin="round"
            {...lineStroke(line.lineStyle, "line")}
            dot={false}
            activeDot={{ r: 5, fill: line.color, stroke: SURFACE, strokeWidth: 2 }}
            isAnimationActive="auto"
            animationDuration={ANIMATION_MS}
            animationEasing="ease-in-out"
          />
        ))}
        <Tooltip
          cursor={{ stroke: "var(--muted)", strokeWidth: 1 }}
          isAnimationActive={false}
          wrapperStyle={{ outline: "none", zIndex: 10 }}
          content={(props) => <WealthTooltip active={props.active} payload={props.payload} series={series} />}
        />
        {endLabelRoom > 0 && <EndLabels series={series} last={last} />}
      </LineChart>
    </ResponsiveContainer>
  );
}
