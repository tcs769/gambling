"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  useXAxisScale,
  useYAxisScale,
} from "recharts";
import { money } from "@/lib/format";
import {
  ANIMATION_MS,
  GRID_STROKE,
  INNER_BAND_OPACITY,
  OUTER_BAND_OPACITY,
  SURFACE,
  TICK_STYLE,
  ageTicks,
  lineStroke,
  niceScale,
} from "./chartTheme";
import {
  innerKey,
  medianKey,
  outerKey,
  quantileKey,
  type FanLineSpec,
  type FanRow,
  type QuantileValues,
} from "./fanData";
import { FanTooltip } from "./FanTooltip";

/** Room on the right for the end labels, so they are never clipped (a value, a short name, a key). */
const DEFAULT_END_LABEL_ROOM = 178;
/** Two end labels closer than this (in pixels) are nudged apart, symmetrically, so they stay readable. */
const END_LABEL_GAP = 22;

/** Whether a line has a 10th-to-90th percentile band at all (a series can be a median line alone). */
const hasBand = (line: FanLineSpec) => (line.bandOpacity ?? OUTER_BAND_OPACITY) > 0;

/** Spread label positions so none sit closer than `gap`, moving each as little as possible. */
export function spreadLabels(ys: readonly number[], gap: number): number[] {
  const out = [...ys];
  const order = ys.map((_, i) => i).sort((a, b) => ys[a] - ys[b]);
  for (let pass = 0; pass < 8; pass++) {
    for (let k = 1; k < order.length; k++) {
      const upper = order[k - 1];
      const lower = order[k];
      const short = gap - (out[lower] - out[upper]);
      if (short > 0) {
        out[upper] -= short / 2;
        out[lower] += short / 2;
      }
    }
  }
  return out;
}

/**
 * The value and name at the right end of each median line. Only the end gets a number: the axis,
 * the tooltip and the table carry the rest. Text stays in text colors; a short stroke in the
 * series color ties each label to its line. Labels glide with their lines when data changes.
 */
function EndLabels({ lines, last }: { lines: readonly FanLineSpec[]; last: FanRow | undefined }) {
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  if (!xScale || !yScale || !last) return null;

  const placed = lines.flatMap((line) => {
    const q = last[quantileKey(line.id)] as QuantileValues | undefined;
    const x = xScale(last.age);
    const y = q ? yScale(q.p50) : undefined;
    return q && x !== undefined && y !== undefined ? [{ line, q, x, y }] : [];
  });
  const ys = spreadLabels(
    placed.map((p) => p.y),
    END_LABEL_GAP,
  );

  return (
    <g>
      {placed.map(({ line, q, x }, i) => (
        <g
          key={line.id}
          style={{ transform: `translate(${x}px, ${ys[i]}px)`, transition: `transform ${ANIMATION_MS}ms ease-in-out` }}
        >
          <line x1="9" y1="0" x2="23" y2="0" stroke={line.color} {...lineStroke(line.lineStyle, "key")} />
          <text x="30" y="0" dy="0.35em" fontSize="14" fill="var(--muted-text)">
            <tspan fontWeight="700" fill="var(--espresso)">
              {money(q.p50)}
            </tspan>
            <tspan dx="6">{line.endName}</tspan>
          </text>
        </g>
      ))}
    </g>
  );
}

interface FanChartProps {
  lines: readonly FanLineSpec[];
  /** Rows from `buildFanRows(lines)`. Keep the array stable between renders so the chart only animates on new data. */
  rows: FanRow[];
  /** Total height, x-axis band included. */
  height: number;
  /** Pixels reserved at the right for the end labels. */
  endLabelRoom?: number;
}

/**
 * Median lines with shaded bands (10th to 90th percentile, optionally 25th to 75th), by age. A
 * line can carry a lighter band, no band, or be dashed or dotted. A crosshair follows the cursor and the
 * tooltip lists every line at that age. Use inside a ChartFrame, which supplies the legend and
 * the table twin.
 */
export function FanChart({ lines, rows, height, endLabelRoom = DEFAULT_END_LABEL_ROOM }: FanChartProps) {
  const ages = rows.map((row) => row.age);
  const last = rows[rows.length - 1];
  // The axis has to reach the top of everything drawn: a band's upper edge, or just the median for a line without one.
  const top = Math.max(
    0,
    ...rows.flatMap((row) =>
      lines.map((line) =>
        hasBand(line)
          ? ((row[outerKey(line.id)] as [number, number] | undefined)?.[1] ?? 0)
          : ((row[quantileKey(line.id)] as QuantileValues | undefined)?.p50 ?? 0),
      ),
    ),
  );
  const { ticks: valueTicks, domainMax } = niceScale(top);
  // The first line in `lines` is the one the page is about: it is drawn last, on top (unless a line sets its layer).
  const drawOrder = lines
    .map((line, i) => ({ line, layer: line.layer ?? -i }))
    .sort((a, b) => a.layer - b.layer)
    .map(({ line }) => line);
  return (
    <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 900, height }}>
      <ComposedChart data={rows} margin={{ top: 14, right: endLabelRoom, bottom: 4, left: 4 }}>
        <CartesianGrid vertical={false} stroke={GRID_STROKE} strokeWidth={1} />
        <XAxis
          dataKey="age"
          ticks={ageTicks(ages)}
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
          ticks={valueTicks}
          interval={0}
          tickFormatter={(value: number) => money(value)}
          tick={TICK_STYLE}
          tickLine={false}
          axisLine={false}
        />
        {drawOrder.filter(hasBand).map((line) => (
          <Area
            key={`${line.id}-outer`}
            type="monotone"
            dataKey={outerKey(line.id)}
            stroke="none"
            fill={line.color}
            fillOpacity={line.bandOpacity ?? OUTER_BAND_OPACITY}
            activeDot={false}
            isAnimationActive="auto"
            animationDuration={ANIMATION_MS}
            animationEasing="ease-in-out"
          />
        ))}
        {drawOrder
          .filter((line) => line.innerBand)
          .map((line) => (
            <Area
              key={`${line.id}-inner`}
              type="monotone"
              dataKey={innerKey(line.id)}
              stroke="none"
              fill={line.color}
              fillOpacity={INNER_BAND_OPACITY}
              activeDot={false}
              isAnimationActive="auto"
              animationDuration={ANIMATION_MS}
              animationEasing="ease-in-out"
            />
          ))}
        {drawOrder.map((line) => (
          <Line
            key={`${line.id}-median`}
            type="monotone"
            dataKey={medianKey(line.id)}
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
          content={(props) => <FanTooltip active={props.active} payload={props.payload} lines={lines} />}
        />
        <EndLabels lines={lines} last={last} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
