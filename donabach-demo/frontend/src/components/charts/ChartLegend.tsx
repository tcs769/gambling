import type { ReactNode } from "react";
import { INNER_BAND_OPACITY, OUTER_BAND_OPACITY, lineStroke, type LineStyle } from "./chartTheme";
import styles from "./ChartLegend.module.css";

export interface LegendItem {
  id: string;
  /** What the mark means, in words. The text stays in the text color; the swatch carries identity. */
  label: ReactNode;
  color: string;
  /** line: a median; band: a shaded range; bandLine: both (a series with its range). */
  kind: "line" | "band" | "innerBand" | "bandLine";
  /** The median is dashed or dotted: the swatch shows it, so the legend never relies on color alone. */
  lineStyle?: LineStyle;
  /**
   * Keeps the item's room in the row without showing it (hidden from everyone): for a series that is on its
   * way, so the legend does not change height when its line arrives.
   */
  reserved?: boolean;
  /** Opacity of the band in the swatch, when it is not the standard wash (a lighter band for a secondary series). */
  bandOpacity?: number;
}

export function Swatch({ color, kind, lineStyle, bandOpacity }: Pick<LegendItem, "color" | "kind" | "lineStyle" | "bandOpacity">) {
  const opacity = bandOpacity ?? (kind === "innerBand" ? INNER_BAND_OPACITY : OUTER_BAND_OPACITY);
  return (
    <svg className={styles.swatch} width="30" height="16" viewBox="0 0 30 16" aria-hidden="true">
      {kind !== "line" && <rect x="1" y="1" width="28" height="14" rx="3" fill={color} fillOpacity={opacity} />}
      {(kind === "line" || kind === "bandLine") && (
        <line x1="2" y1="8" x2="28" y2="8" stroke={color} {...lineStroke(lineStyle, "swatch")} />
      )}
    </svg>
  );
}

/** A legend for charts with more than one mark: a short swatch beside plain text. */
export function ChartLegend({ items, label = "Legend" }: { items: LegendItem[]; label?: string }) {
  return (
    <ul className={styles.legend} aria-label={label}>
      {items.map((item) => (
        <li
          key={item.id}
          className={styles.item}
          data-line-style={item.lineStyle && item.lineStyle !== "solid" ? item.lineStyle : undefined}
          data-reserved={item.reserved ? "true" : undefined}
          aria-hidden={item.reserved ? "true" : undefined}
        >
          <Swatch color={item.color} kind={item.kind} lineStyle={item.lineStyle} bandOpacity={item.bandOpacity} />
          <span>{item.label}</span>
        </li>
      ))}
    </ul>
  );
}
