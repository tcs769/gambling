"use client";

import { useId, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import type { Plan } from "@/lib/portal-types";
import { axisMoney, wealth } from "@/lib/invest-format";
import { Btn } from "@/components/portal/Btn";
import styles from "./ProjectionChart.module.css";
import table from "./invest.module.css";

type Overview = Plan["portfolio"]["overview"];

const NAVY = "#1f3a5f";
const BROWN = "#b8946a";
const INK2 = "#5b6472";

/** Projected wealth by age: one line, with the goals marked (a band for college, a dashed line for the rest). */
export function ProjectionChart({ overview, horizon }: { overview: Overview; horizon: number }) {
  const [asTable, setAsTable] = useState(false);
  const tableId = useId();
  const points = overview.projection;
  const first = points[0]?.age ?? 0;
  const last = points[points.length - 1]?.age ?? horizon;
  const bands = overview.markers.filter((m) => m.end_age !== null);
  const lines = overview.markers.filter((m) => m.end_age === null);
  const ticks = points.map((p) => p.age).filter((age) => age % 5 === 0 || age === first || age === last);

  return (
    <div>
      <div className={styles.frame} data-testid="projection-chart">
        <div className={styles.chart} role="img" aria-label="Projected wealth by age" hidden={asTable}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 28, right: 28, bottom: 8, left: 4 }}>
              <CartesianGrid stroke="#e6ecf3" vertical={false} />
              <XAxis
                dataKey="age"
                type="number"
                domain={[first, last]}
                ticks={ticks}
                tick={{ fill: INK2, fontSize: 13 }}
                stroke="#d5dee9"
                tickLine={false}
                label={{ value: "Age", position: "insideBottomRight", offset: -2, fill: INK2, fontSize: 13 }}
                height={42}
              />
              <YAxis
                tickFormatter={axisMoney}
                tick={{ fill: INK2, fontSize: 13 }}
                stroke="#d5dee9"
                tickLine={false}
                width={58}
              />
              {bands.map((m) => (
                <ReferenceArea
                  key={m.key}
                  x1={m.start_age}
                  x2={m.end_age ?? m.start_age}
                  fill={BROWN}
                  fillOpacity={0.18}
                  stroke="none"
                  ifOverflow="visible"
                  label={{ value: m.label, position: "insideBottom", fill: "#6b4a2e", fontSize: 13 }}
                />
              ))}
              {lines.map((m) => (
                <ReferenceLine
                  key={m.key}
                  x={m.start_age}
                  stroke={m.key === "social_security" ? INK2 : "#6b4a2e"}
                  strokeDasharray="5 4"
                  ifOverflow="visible"
                  label={{
                    value: m.label,
                    position: m.key === "retirement" ? "insideTopRight" : "insideTopLeft",
                    fill: m.key === "social_security" ? INK2 : "#6b4a2e",
                    fontSize: 13,
                  }}
                />
              ))}
              <Line
                type="monotone"
                dataKey="wealth"
                stroke={NAVY}
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
        {asTable && (
          <div id={tableId} className={`${table.tableWrap} ${styles.tableScroll}`}>
            <table className={table.table}>
              <caption>Projected wealth by age</caption>
              <thead>
                <tr>
                  <th scope="col">Age</th>
                  <th scope="col" className={table.right}>
                    Wealth
                  </th>
                </tr>
              </thead>
              <tbody>
                {points.map((p) => (
                  <tr key={p.age}>
                    <th scope="row">{p.age}</th>
                    <td className={table.right}>{wealth(p.wealth)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
