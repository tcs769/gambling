"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import styles from "./DataTable.module.css";

export interface DataColumn<T> {
  key: string;
  header: ReactNode;
  cell: (row: T, index: number) => ReactNode;
  /** Numbers align to the end. */
  align?: "start" | "end";
  /** CSS width of the column (e.g. "14%", "120px"); the rest share what is left. */
  width?: string;
  /** Render this column's cell as the row's header cell (for the first, identifying column). */
  rowHeader?: boolean;
}

export type RowKey = string | number;

interface DataTableProps<T> {
  columns: DataColumn<T>[];
  rows: readonly T[];
  rowKey: (row: T, index: number) => RowKey;
  /** Names the table for screen readers (not shown). */
  caption: string;
  /** Scroll the body (header stays put) once it grows past this height. */
  maxHeight?: number | string;
  /** Exact height: the table scrolls inside it. Used where a table stands in for a chart. */
  height?: number | string;
  /** Rows become focusable buttons (Enter or Space), with Up and Down moving between them. */
  onRowActivate?: (row: T, index: number) => void;
  selectedKey?: RowKey | null;
  /** A quiet mark for rows worth noticing, or a stronger highlight for the row the page is about. */
  rowTone?: (row: T) => "marked" | "highlight" | undefined;
  /** Read out for interactive rows, e.g. "Press Enter to see this year's decisions". */
  rowHint?: string;
  /** What sits under the fade when more rows are scrolled out of view. */
  surface?: "panel" | "cream";
  dense?: boolean;
}

/**
 * A table of numbers: tabular figures, a sticky header over a scrolling body, optional row
 * selection. A soft fade at the bottom edge shows there is more to scroll to.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  maxHeight,
  height,
  onRowActivate,
  selectedKey = null,
  rowTone,
  rowHint,
  surface = "panel",
  dense = false,
}: DataTableProps<T>) {
  const scroller = useRef<HTMLDivElement>(null);
  const [more, setMore] = useState(false);
  const hintId = useId();
  const interactive = !!onRowActivate;

  // The fade at the bottom shows only while rows remain below the visible part.
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const update = () => setMore(el.scrollTop + el.clientHeight < el.scrollHeight - 2);
    const observer = new ResizeObserver(update);
    observer.observe(el);
    if (el.firstElementChild) observer.observe(el.firstElementChild);
    el.addEventListener("scroll", update, { passive: true });
    return () => {
      observer.disconnect();
      el.removeEventListener("scroll", update);
    };
  }, [rows.length]);

  const onKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, row: T, index: number) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onRowActivate?.(row, index);
      return;
    }
    const siblings = Array.from(event.currentTarget.parentElement?.children ?? []) as HTMLElement[];
    const at = siblings.indexOf(event.currentTarget);
    const to =
      event.key === "ArrowDown" ? at + 1 : event.key === "ArrowUp" ? at - 1 : event.key === "Home" ? 0 : event.key === "End" ? siblings.length - 1 : null;
    if (to === null) return;
    event.preventDefault();
    siblings[Math.max(0, Math.min(siblings.length - 1, to))]?.focus();
  };

  return (
    <div className={styles.wrap} data-more={more} data-surface={surface}>
      <div
        ref={scroller}
        className={styles.scroller}
        style={{ maxHeight, height }}
        // A scrolling region has to be reachable by keyboard; interactive rows already are.
        tabIndex={interactive ? undefined : 0}
        role={interactive ? undefined : "region"}
        aria-label={interactive ? undefined : caption}
      >
        <table className={styles.table} data-dense={dense}>
          <caption className="sr-only">{caption}</caption>
          <colgroup>
            {columns.map((col) => (
              <col key={col.key} style={col.width ? { width: col.width } : undefined} />
            ))}
          </colgroup>
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key} scope="col" data-align={col.align ?? "start"}>
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const key = rowKey(row, index);
              return (
                <tr
                  key={key}
                  data-row-key={key}
                  data-selected={interactive ? key === selectedKey : undefined}
                  data-tone={rowTone?.(row)}
                  data-interactive={interactive}
                  tabIndex={interactive ? 0 : undefined}
                  aria-selected={interactive ? key === selectedKey : undefined}
                  aria-describedby={interactive && rowHint ? hintId : undefined}
                  onClick={interactive ? () => onRowActivate?.(row, index) : undefined}
                  onKeyDown={interactive ? (event) => onKeyDown(event, row, index) : undefined}
                >
                  {columns.map((col) => {
                    const content = col.cell(row, index);
                    return col.rowHeader ? (
                      <th key={col.key} scope="row" data-align={col.align ?? "start"}>
                        {content}
                      </th>
                    ) : (
                      <td key={col.key} data-align={col.align ?? "start"}>
                        {content}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {interactive && rowHint && (
        <span id={hintId} className="sr-only">
          {rowHint}
        </span>
      )}
    </div>
  );
}
