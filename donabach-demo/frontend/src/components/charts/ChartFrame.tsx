"use client";

import { useState, type ReactNode } from "react";
import { Button, Icon } from "@/components/ui";
import { CHART_HEIGHT } from "./chartTheme";
import styles from "./ChartFrame.module.css";

interface ChartFrameProps {
  /** A legend (for two or more marks) and any plain-language key. */
  legend?: ReactNode;
  chart: ReactNode;
  /** The same numbers as a table, one toggle away: no value is reachable only by hovering. */
  table: ReactNode;
  /** Names the figure for screen readers. */
  label: string;
  /** Total height of the body, x-axis labels included. Chart and table share it, so toggling never moves the page. */
  height?: number;
}

/**
 * The container every chart lives in: legend and "View as table" toggle above, a body of fixed
 * height below. Chart and table share that height, so toggling between them never moves the page.
 */
export function ChartFrame({ legend, chart, table, label, height = CHART_HEIGHT }: ChartFrameProps) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <figure className={styles.frame} aria-label={label}>
      <div className={styles.toolbar}>
        <div className={styles.legend}>{legend}</div>
        <Button variant="ghost" className={styles.toggle} onClick={() => setView(view === "chart" ? "table" : "chart")}>
          <Icon name={view === "chart" ? "table" : "chart"} size={18} />
          {view === "chart" ? "View as table" : "View as chart"}
        </Button>
      </div>
      <div className={styles.body} style={{ height }}>
        {view === "chart" ? chart : table}
      </div>
    </figure>
  );
}
