"use client";

import { useRef, useState, type FocusEvent, type PointerEvent } from "react";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { niceScale } from "@/components/charts/chartTheme";
import { DataTable, type DataColumn } from "@/components/ui";
import { money, signedMoney } from "@/lib/format";
import type { AdvantageStep } from "@/lib/types";
import styles from "./AdvantageBars.module.css";

const ROW_HEIGHT = 58;
const AXIS_HEIGHT = 44;
/** Headroom past the longest bar, so the value at its tip always has room. */
const HEADROOM = 1.16;

/** Axis from the most negative to the most positive step, in clean steps, with zero as the baseline. */
function axisFor(values: number[]) {
  const max = Math.max(0, ...values);
  const min = Math.min(0, ...values);
  const { ticks } = niceScale(Math.max(max, -min, 1) * HEADROOM, 6);
  const step = ticks[1] - ticks[0];
  const up = max > 0 ? Math.ceil((max * HEADROOM) / step - 1e-9) : 0;
  const down = min < 0 ? Math.ceil((-min * HEADROOM) / step - 1e-9) : 0;
  const all: number[] = [];
  for (let i = -down; i <= Math.max(up, 1); i++) all.push(i * step);
  return { ticks: all, domainMin: -down * step, domainMax: Math.max(up, 1) * step };
}

interface Hover {
  index: number;
  x: number;
  y: number;
  width: number;
}

const COLUMNS: DataColumn<AdvantageStep>[] = [
  {
    key: "step",
    header: "Decision",
    rowHeader: true,
    cell: (s) => (
      <>
        {s.label}
        {!s.active && <span className={styles.tableNote}>Not used in this plan</span>}
      </>
    ),
  },
  { key: "median", header: "Change in typical outcome", align: "end", width: "22%", cell: (s) => (s.active ? signedMoney(s.delta_median) : "–") },
  { key: "p10", header: "Change in bad case", align: "end", width: "20%", cell: (s) => (s.active ? signedMoney(s.delta_p10) : "–") },
  { key: "total", header: "Running total", align: "end", width: "18%", cell: (s) => (s.active ? signedMoney(s.cumulative_median) : "–") },
];

/**
 * "Where the advantage comes from": one bar per decision, starting from the typical advisor and
 * switching decisions on one at a time. Each bar is the change in typical wealth at 70; together
 * they add up to the whole advantage. Decisions this plan does not use have no bar.
 */
export function AdvantageBars({ steps }: { steps: AdvantageStep[] }) {
  const chart = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const active = steps.filter((s) => s.active);
  const { ticks, domainMin, domainMax } = axisFor(active.map((s) => s.delta_median));
  const span = domainMax - domainMin;
  const at = (value: number) => ((value - domainMin) / span) * 100;
  const zero = at(0);
  const height = ROW_HEIGHT * steps.length + AXIS_HEIGHT;

  const track = (event: PointerEvent<HTMLLIElement>, index: number) => {
    const box = chart.current?.getBoundingClientRect();
    if (box) setHover({ index, x: event.clientX - box.left, y: event.clientY - box.top, width: box.width });
  };
  const focus = (event: FocusEvent<HTMLLIElement>, index: number) => {
    const box = chart.current?.getBoundingClientRect();
    const row = event.currentTarget.getBoundingClientRect();
    if (box) setHover({ index, x: row.left - box.left + row.width * 0.55, y: row.top - box.top + row.height / 2, width: box.width });
  };

  const tip = hover ? steps[hover.index] : null;

  return (
    <ChartFrame
      label="Where the advantage comes from: the change in typical wealth at 70 from each decision"
      height={height}
      chart={
        <div ref={chart} className={styles.chart} style={{ height }}>
          <div className={styles.plot} style={{ bottom: AXIS_HEIGHT }} aria-hidden="true">
            {ticks.map((t) => (
              <span key={t} className={styles.grid} data-zero={t === 0} style={{ left: `${at(t)}%` }} />
            ))}
          </div>
          <ol className={styles.rows} aria-label="Change in typical wealth at 70, by decision">
            {steps.map((step, i) => {
              const value = step.delta_median;
              const end = at(value);
              const negative = value < 0;
              const summary = step.active
                ? `${step.label}: ${signedMoney(value)} in typical wealth at 70, ${signedMoney(step.delta_p10)} in the bad case`
                : `${step.label}: not used in this plan`;
              return (
                <li
                  key={step.label}
                  className={styles.row}
                  style={{ height: ROW_HEIGHT }}
                  data-active={step.active}
                  tabIndex={0}
                  aria-label={summary}
                  onPointerMove={(e) => track(e, i)}
                  onPointerLeave={() => setHover(null)}
                  onFocus={(e) => focus(e, i)}
                  onBlur={() => setHover(null)}
                >
                  <div className={styles.label}>
                    <span className={styles.name}>{step.label}</span>
                    {!step.active && <span className={styles.unused}>Not used in this plan</span>}
                  </div>
                  <div className={styles.track}>
                    {step.active && (
                      <>
                        <span
                          className={styles.bar}
                          data-negative={negative}
                          style={{ left: `${negative ? end : zero}%`, width: `${Math.abs(end - zero)}%` }}
                        />
                        <span
                          className={styles.value}
                          data-negative={negative}
                          style={negative ? { right: `${100 - end}%` } : { left: `${end}%` }}
                        >
                          {signedMoney(value)}
                        </span>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
          <div className={styles.axis} style={{ height: AXIS_HEIGHT }} aria-hidden="true">
            {ticks.map((t) => (
              <span key={t} className={styles.tick} style={{ left: `${at(t)}%` }}>
                {money(t)}
              </span>
            ))}
          </div>
          {hover && tip && (
            <div
              className={styles.tooltip}
              role="tooltip"
              data-flip={hover.x > hover.width - 270}
              style={{ left: hover.x, top: hover.y }}
            >
              <div className={styles.tipName}>{tip.label}</div>
              {tip.active ? (
                <>
                  <div className={styles.tipValue}>{signedMoney(tip.delta_median)}</div>
                  <div className={styles.tipDetail}>Change in typical outcome at 70</div>
                  <div className={styles.tipDetail}>Bad case: {signedMoney(tip.delta_p10)}</div>
                  <div className={styles.tipDetail}>Running total: {signedMoney(tip.cumulative_median)}</div>
                </>
              ) : (
                <div className={styles.tipDetail}>Not used in this plan</div>
              )}
            </div>
          )}
        </div>
      }
      table={
        <DataTable
          columns={COLUMNS}
          rows={steps}
          rowKey={(s) => s.label}
          caption="Where the advantage comes from: the change in typical outcome and bad case at 70 from each decision, and the running total"
          height={height}
        />
      }
    />
  );
}
