"use client";

import { useId, useState } from "react";
import type { Plan } from "@/lib/portal-types";
import { axisMoney, wealth } from "@/lib/invest-format";
import { Btn } from "@/components/portal/Btn";
import { useElementWidth } from "@/components/showcase/useElementWidth";
import styles from "./ProjectionChart.module.css";
import t from "./invest.module.css";

type Overview = Plan["portfolio"]["overview"];
type Marker = Overview["markers"][number];

const HEIGHT = 260;
const TOP = 30;
const BOTTOM = 210;
const LEFT = 60;
const RIGHT_PAD = 20;
const TAG_LANE = 18;
const CHAR_WIDTH = 6.6;

/** 1, 2, 5, 10... times a power of ten, the first at or above `raw` (so the y axis steps by round figures). */
function niceStep(raw: number): number {
  if (raw <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(raw));
  const unit = raw / power;
  return (unit <= 1 ? 1 : unit <= 2 ? 2 : unit <= 5 ? 5 : 10) * power;
}

/** What a marker is called on the chart: the retirement tag says the age. */
const tagText = (m: Marker) => (m.key === "retirement" ? `Retire at ${m.start_age}` : m.label);

/** Projected wealth by age: one line, with the goals marked (a band for college, a dashed line for the rest), in the mockup's drawing. */
export function ProjectionChart({ overview, horizon }: { overview: Overview; horizon: number }) {
  const [asTable, setAsTable] = useState(false);
  const [ref, measured] = useElementWidth<HTMLDivElement>();
  const tableId = useId();
  const width = Math.max(measured || 900, 300);
  const left = width < 520 ? 52 : LEFT;
  const points = overview.projection;
  const first = points[0]?.age ?? 0;
  const last = points[points.length - 1]?.age ?? horizon;
  const peak = Math.max(1, ...points.map((p) => p.wealth));
  const step = niceStep(peak / 3);
  const top = Math.max(1, Math.ceil(peak / step - 1e-9)) * step;
  const gridValues = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);

  const x = (age: number) => left + ((age - first) / Math.max(1, last - first)) * (width - left - RIGHT_PAD);
  const y = (value: number) => BOTTOM - (value / top) * (BOTTOM - TOP);

  const bands = overview.markers.filter((m) => m.end_age !== null);
  const lines = overview.markers.filter((m) => m.end_age === null);
  const ageTicks = points
    .map((p) => p.age)
    .filter((age) => age % 10 === 0 && x(age) - x(first) > 20 && x(last) - x(age) > 20)
    .concat([first, last])
    .sort((a, b) => a - b);

  // Tags sit at the top of the chart; one that would run into the one before it drops to a second lane.
  const tags = [...overview.markers]
    .map((m) => ({ m, at: m.end_age !== null ? x(m.start_age) + 6 : x(m.start_age) + 8, text: tagText(m) }))
    .sort((a, b) => a.at - b.at);
  const laneEnds: number[] = [];
  const placed = tags.map((tag) => {
    let lane = laneEnds.findIndex((end) => tag.at > end + 8);
    if (lane < 0) lane = laneEnds.length;
    laneEnds[lane] = tag.at + tag.text.length * CHAR_WIDTH;
    return { ...tag, lane };
  });

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.age).toFixed(1)},${y(p.wealth).toFixed(1)}`).join(" ");
  const end = points[points.length - 1];
  const label = `Projected wealth rising from ${wealth(points[0]?.wealth ?? 0)} at ${first} to ${wealth(end?.wealth ?? 0)} at ${last}`;

  return (
    <div>
      <div ref={ref} className={styles.frame} data-testid="projection-chart">
        {asTable ? (
          <div id={tableId} className={`${t.scroll} ${styles.tableScroll}`}>
            <table className={t.hold}>
              <caption>Projected wealth by age</caption>
              <thead>
                <tr>
                  <th scope="col">Age</th>
                  <th scope="col" className={t.right}>
                    Wealth
                  </th>
                </tr>
              </thead>
              <tbody>
                {points.map((p) => (
                  <tr key={p.age}>
                    <th scope="row">{p.age}</th>
                    <td className={`${t.right} num`}>{wealth(p.wealth)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <svg
            className={styles.proj}
            viewBox={`0 0 ${width} ${HEIGHT}`}
            width={width}
            height={HEIGHT}
            role="img"
            aria-label={label}
          >
            <g className={styles.grid}>
              {gridValues.map((v) => (
                <line key={v} x1={left} y1={y(v)} x2={width - RIGHT_PAD} y2={y(v)} />
              ))}
            </g>
            <g className={styles.ylab}>
              {gridValues.map((v) => (
                <text key={v} x={left - 10} y={y(v) + 4}>
                  {axisMoney(v)}
                </text>
              ))}
            </g>
            {bands.map((m) => (
              <rect
                key={m.key}
                className={styles.band}
                data-marker={m.key}
                x={x(m.start_age)}
                y={TOP}
                width={x(m.end_age ?? m.start_age) - x(m.start_age)}
                height={BOTTOM - TOP}
              />
            ))}
            {lines.map((m) => (
              <line
                key={m.key}
                className={styles.mile}
                data-marker={m.key}
                x1={x(m.start_age)}
                y1={TOP}
                x2={x(m.start_age)}
                y2={BOTTOM}
              />
            ))}
            <path className={styles.line} d={path} />
            {end && <circle className={styles.end} cx={x(end.age)} cy={y(end.wealth)} r={5} />}
            <g className={styles.xlab}>
              {ageTicks.map((age) => (
                <text key={age} x={x(age)} y={236}>
                  {age}
                </text>
              ))}
            </g>
            {placed.map((tag) => (
              <text key={tag.m.key} className={styles.tag} x={tag.at} y={48 + tag.lane * TAG_LANE}>
                {tag.text}
              </text>
            ))}
          </svg>
        )}
      </div>
      <div className={styles.toggle}>
        <Btn
          variant="link"
          onClick={() => setAsTable((v) => !v)}
          aria-expanded={asTable}
          aria-controls={asTable ? tableId : undefined}
        >
          {asTable ? "View as chart" : "View as table"}
        </Btn>
      </div>
    </div>
  );
}
