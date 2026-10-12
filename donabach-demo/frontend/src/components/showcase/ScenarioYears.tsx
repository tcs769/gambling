"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { DataTable, Icon, type DataColumn } from "@/components/ui";
import { money, percent } from "@/lib/format";
import type { ScenarioYear } from "@/lib/types";
import styles from "./Scenario.module.css";

interface Decision {
  /** The API's name for it in `responded` and `replanned`. */
  key: "wages" | "roth_conversion" | "gains_harvested_tax_free" | "losses_harvested" | "stock_share";
  header: string;
  /** What the plan does after the event, and what it did before it (the plan with no event). */
  after: (year: ScenarioYear) => number;
  before: (year: ScenarioYear) => number;
  format: (value: number) => string;
}

const DECISIONS: Decision[] = [
  { key: "wages", header: "Wages", after: (y) => y.wages, before: (y) => y.base_wages, format: money },
  {
    key: "roth_conversion",
    header: "Roth conversion",
    after: (y) => y.roth_conversion,
    before: (y) => y.base_roth_conversion,
    format: money,
  },
  {
    key: "gains_harvested_tax_free",
    header: "Gains realized tax-free",
    after: (y) => y.gains_harvested_tax_free,
    before: (y) => y.base_gains_harvested_tax_free,
    format: money,
  },
  {
    key: "losses_harvested",
    header: "Losses harvested",
    after: (y) => y.losses_harvested,
    before: (y) => y.base_losses_harvested,
    format: money,
  },
  {
    key: "stock_share",
    header: "Stock share",
    after: (y) => y.stock_share,
    before: (y) => y.base_stock_share,
    format: (v) => percent(v),
  },
];

/** What changed in a year, from the API's flags (never worked out here): the event's response and what planning again added. */
const changedKeys = (year: ScenarioYear): ReadonlySet<string> => new Set([...year.responded, ...year.replanned]);
export const yearChanged = (year: ScenarioYear): boolean => year.responded.length > 0 || year.replanned.length > 0;

/**
 * Year by year, from today to the end of the plan: what the plan does after the event, for each decision. A decision the
 * event (or planning again) changed is bold with "before: X" (the plan with no event) in small type under it; a year where
 * anything changed is highlighted by a tint, an edge, a visible "Changed" tag with an icon and text for screen readers, so colour is
 * never the only sign. "Show only the years that changed" is on at first. The first highlighted row is scrolled to when the
 * table first appears (inside the table, never the page).
 */
export function ScenarioYears({ years, eventLabel }: { years: readonly ScenarioYear[]; eventLabel: string }) {
  const [onlyChanged, setOnlyChanged] = useState(true);
  const wrap = useRef<HTMLDivElement>(null);
  const changedCount = years.filter(yearChanged).length;
  const rows = useMemo(() => (onlyChanged ? years.filter(yearChanged) : years), [years, onlyChanged]);

  const columns = useMemo<DataColumn<ScenarioYear>[]>(
    () => [
      {
        key: "age",
        header: "Age",
        rowHeader: true,
        width: "112px",
        cell: (year) => {
          const keys = changedKeys(year);
          return (
            <span className={styles.ageCell}>
              <span className={styles.age}>{year.age}</span>
              {yearChanged(year) && (
                <span className={styles.tag} data-testid="changed-tag">
                  <Icon name="refresh" size={12} strokeWidth={2.6} />
                  Changed
                  <span className="sr-only">
                    {" "}
                    in this year:{" "}
                    {DECISIONS.filter((d) => keys.has(d.key))
                      .map((d) => d.header.toLowerCase())
                      .join(", ")}
                  </span>
                </span>
              )}
            </span>
          );
        },
      },
      ...DECISIONS.map(
        (decision): DataColumn<ScenarioYear> => ({
          key: decision.key,
          header: decision.header,
          align: "end",
          width: "132px",
          cell: (year) => {
            const differs = changedKeys(year).has(decision.key);
            return (
              <span className={styles.value} data-differs={differs || undefined}>
                <span className={styles.after}>{decision.format(decision.after(year))}</span>
                {differs && (
                  <span className={styles.before}>
                    <span className="sr-only">changed, </span>before: {decision.format(decision.before(year))}
                  </span>
                )}
              </span>
            );
          },
        }),
      ),
    ],
    [],
  );

  // The first highlighted row is brought into view inside the table when it first shows (and when the event or the filter changes).
  useEffect(() => {
    const scroller = wrap.current?.querySelector<HTMLElement>('[role="region"]');
    const first = scroller?.querySelector<HTMLElement>('tr[data-tone="highlight"]');
    if (!scroller || !first) return;
    const header = scroller.querySelector("thead")?.getBoundingClientRect().height ?? 0;
    scroller.scrollTop = Math.max(0, first.offsetTop - header);
  }, [years, onlyChanged]);

  const hidden = years.length - rows.length;
  return (
    <div ref={wrap}>
      <div className={styles.yearsBar}>
        <label className={styles.toggle}>
          <input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} />
          <span>Show only the years that changed</span>
        </label>
        <p className={styles.count} role="status" aria-live="polite">
          {changedCount} of {years.length} years changed
          {onlyChanged && hidden > 0 ? `; ${hidden} hidden` : ""}.
        </p>
      </div>
      <p className={styles.quiet}>
        Each figure is what the plan does after the event. Under a bold figure, &quot;before&quot; is the same year with
        no event.
      </p>
      {rows.length === 0 ? (
        <p className={styles.quiet}>No year changed.</p>
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(year) => year.age}
          caption={`Year by year after the event "${eventLabel}": what the plan does at each age, and the years that changed`}
          rowTone={(year) => (yearChanged(year) ? "highlight" : undefined)}
          maxHeight={460}
          minWidth={720}
          dense
        />
      )}
    </div>
  );
}
