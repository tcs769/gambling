"use client";

import { DataTable, Panel, PanelTitle, type DataColumn } from "@/components/ui";
import { money, percent } from "@/lib/format";
import type { PlanRow } from "@/lib/types";
import styles from "./Plan.module.css";

/** Zero is an en dash, so a column of mostly nothing reads as nothing. */
function amount(value: number) {
  if (Math.abs(value) < 0.5) {
    return (
      <span className={styles.zero}>
        <span aria-hidden="true">–</span>
        <span className="sr-only">none</span>
      </span>
    );
  }
  return money(value);
}

const isMarked = (row: PlanRow) => row.roth_conversion > 0.5 || row.goal_paid > 0.5;

interface YearTableProps {
  rows: readonly PlanRow[];
  /** The age the plan runs to (the last row is the year before it). */
  horizon: number;
  /** Marks the first year of retirement. */
  retirementAge?: number;
  selected: number | null;
  onSelect: (yearIndex: number) => void;
}

/** The deterministic plan, year by year. Each row opens that year's decisions and tax return. */
export function YearTable({ rows, horizon, retirementAge, selected, onSelect }: YearTableProps) {
  const columns: DataColumn<PlanRow>[] = [
    {
      key: "age",
      header: "Age",
      rowHeader: true,
      width: "23%",
      cell: (row) => {
        const notes = [
          row.age === retirementAge ? "Retirement starts" : null,
          row.goal_paid > 0.5 ? `${row.goal_label ?? "Goal payment"} ${money(row.goal_paid)}` : null,
        ].filter(Boolean);
        return (
          <span className={styles.age}>
            {row.age}
            {notes.length > 0 && <span className={styles.ageNote}>{notes.join(" · ")}</span>}
          </span>
        );
      },
    },
    { key: "income", header: "Income", align: "end", cell: (row) => money(row.income) },
    { key: "roth", header: "Roth conversion", align: "end", cell: (row) => amount(row.roth_conversion) },
    { key: "harvest", header: "Losses harvested", align: "end", cell: (row) => amount(row.losses_harvested) },
    { key: "bonds", header: "Goal bonds (balance)", align: "end", cell: (row) => amount(row.goal_bonds_balance) },
    { key: "stock", header: "Stock share", align: "end", cell: (row) => percent(row.stock_share) },
    { key: "tax", header: "Total tax", align: "end", cell: (row) => money(row.total_tax) },
  ];

  const first = rows[0]?.age;
  const last = rows[rows.length - 1]?.age;

  return (
    <Panel>
      <PanelTitle aside="Click a year for its decisions and tax return">Year by year</PanelTitle>
      <p className={styles.tableNote}>
        {rows.length} years, ages {first} to {last}, running to {horizon}. Scroll for the rest. Each year is at expected
        returns rather than a simulated future, so these figures are not the outcomes on the Comparison screen. A gold edge
        marks a year with a Roth conversion or a goal payment.
      </p>
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(row) => row.year_index}
        caption="Year-by-year plan: income, Roth conversion, losses harvested, goal bonds, stock share and total tax"
        maxHeight={474}
        selectedKey={selected}
        onRowActivate={(row) => onSelect(row.year_index)}
        rowTone={(row) => (isMarked(row) ? "marked" : undefined)}
        rowHint="Press Enter to see this year's decisions and tax return."
      />
    </Panel>
  );
}
