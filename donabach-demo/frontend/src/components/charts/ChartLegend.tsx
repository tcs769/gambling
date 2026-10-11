import type { ReactNode } from "react";
import { INNER_BAND_OPACITY, OUTER_BAND_OPACITY } from "./chartTheme";
import styles from "./ChartLegend.module.css";

export interface LegendItem {
  id: string;
  /** What the mark means, in words. The text stays in the text color; the swatch carries identity. */
  label: ReactNode;
  color: string;
  /** line: a median; band: a shaded range; bandLine: both (a series with its range). */
  kind: "line" | "band" | "innerBand" | "bandLine";
}

function Swatch({ color, kind }: { color: string; kind: LegendItem["kind"] }) {
  const bandOpacity = kind === "innerBand" ? INNER_BAND_OPACITY : OUTER_BAND_OPACITY;
  return (
    <svg className={styles.swatch} width="30" height="16" viewBox="0 0 30 16" aria-hidden="true">
      {kind !== "line" && <rect x="1" y="1" width="28" height="14" rx="3" fill={color} fillOpacity={bandOpacity} />}
      {(kind === "line" || kind === "bandLine") && (
        <line x1="2" y1="8" x2="28" y2="8" stroke={color} strokeWidth="2" strokeLinecap="round" />
      )}
    </svg>
  );
}

/** A legend for charts with more than one mark: a short swatch beside plain text. */
export function ChartLegend({ items }: { items: LegendItem[] }) {
  return (
    <ul className={styles.legend}>
      {items.map((item) => (
        <li key={item.id} className={styles.item}>
          <Swatch color={item.color} kind={item.kind} />
          <span>{item.label}</span>
        </li>
      ))}
    </ul>
  );
}
