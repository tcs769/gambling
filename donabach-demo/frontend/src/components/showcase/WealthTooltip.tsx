import type { TooltipContentProps } from "recharts";
import { lineStroke } from "@/components/charts/chartTheme";
import { money } from "@/lib/format";
import type { WealthRow, WealthSeries } from "./wealthData";
import styles from "./WealthTooltip.module.css";

/**
 * What the cursor (or the keyboard) is on: every line at that age. The value leads, the line's name follows, and a short
 * key in the line's colour and style says which line it is (a dashed key for a dashed line, so colour is not the only sign).
 * Donabach's lines come first, the advisor's after.
 */
export function WealthTooltip({
  active,
  payload,
  series,
}: Pick<TooltipContentProps, "active" | "payload"> & { series: readonly WealthSeries[] }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as WealthRow | undefined;
  if (!row) return null;
  return (
    <div className={styles.tip}>
      <div className={styles.age}>Age {row.age}</div>
      <ul className={styles.rows}>
        {[...series].reverse().map((line) => (
          <li key={line.key} className={styles.row}>
            <svg className={styles.key} width="22" height="4" viewBox="0 0 22 4" aria-hidden="true">
              <line x1="0" y1="2" x2="22" y2="2" stroke={line.color} {...lineStroke(line.lineStyle, "key")} />
            </svg>
            <div>
              <strong className={styles.value}>{money(row[line.key])}</strong>
              <span className={styles.name}>{line.name}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
