import type { TooltipContentProps } from "recharts";
import { money } from "@/lib/format";
import { DASH_KEY } from "./chartTheme";
import { quantileKey, type FanLineSpec, type FanRow, type QuantileValues } from "./fanData";
import styles from "./FanTooltip.module.css";

/**
 * What the cursor is over: every series at that age. The value leads (strong), the series name
 * follows (secondary), and a short key in the series color says which line it is.
 */
export function FanTooltip({
  active,
  payload,
  lines,
}: Pick<TooltipContentProps, "active" | "payload"> & { lines: readonly FanLineSpec[] }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as FanRow | undefined;
  if (!row) return null;
  return (
    <div className={styles.tip}>
      <div className={styles.age}>Age {row.age}</div>
      <ul className={styles.rows}>
        {lines.map((line) => {
          const q = row[quantileKey(line.id)] as QuantileValues | undefined;
          if (!q) return null;
          return (
            <li key={line.id} className={styles.row}>
              {line.dashed ? (
                // A dashed series gets a dashed key, so the tooltip tells lines apart by more than colour too.
                <svg className={styles.key} width="16" height="2" viewBox="0 0 16 2" aria-hidden="true">
                  <line x1="0" y1="1" x2="16" y2="1" stroke={line.color} strokeWidth="2" strokeDasharray={DASH_KEY} />
                </svg>
              ) : (
                <span className={styles.key} style={{ background: line.color }} aria-hidden="true" />
              )}
              <div>
                <div>
                  <strong className={styles.value}>{money(q.p50)}</strong>
                  <span className={styles.name}>{line.name}</span>
                </div>
                {line.details?.(q).map((detail) => (
                  <div key={detail} className={styles.detail}>
                    {detail}
                  </div>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
