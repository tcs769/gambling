"use client";

import { Chip, ChipGroup, DataTable, Panel, PanelTitle, type DataColumn } from "@/components/ui";
import { agesList, changedTag, type YearRow } from "@/lib/adaptive";
import { count, money, percent, percentTrim } from "@/lib/format";
import type { AdaptiveState } from "@/lib/state";
import type { MarketShock } from "@/lib/types";
import { AdaptiveFailure } from "./Refining";
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

const isMarked = (row: YearRow) => row.roth_conversion > 0.5 || row.goal_paid > 0.5;

/** Which plan the table shows. */
export type PlanView = "adaptive" | "fixed";

interface YearTableProps {
  /** The rows of the plan on show: the year-by-year plan's when `view` is "adaptive", else the fixed strategy's. */
  rows: readonly YearRow[];
  view: PlanView;
  onView: (view: PlanView) => void;
  /** Where the year-by-year plan stands: the "Year-by-year plan" choice is there once it is ready. */
  adaptive?: AdaptiveState;
  /** The age the plan runs to (the last row is the year before it). */
  horizon: number;
  /** Marks the first year of retirement. */
  retirementAge?: number;
  /** A what-if's market drop, marked on the year it happens. */
  shock?: MarketShock | null;
  selected: number | null;
  onSelect: (yearIndex: number) => void;
  /** Why there is no year-by-year plan to switch to (a plan in another planning style has none): said instead of the usual status. */
  unavailableNote?: string;
}

/**
 * The plan, year by year: the year-by-year (adaptive) plan once it is ready, or the fixed strategy, with a switch
 * between them. In the year-by-year view the years where the planner changed something from the fixed strategy
 * are tinted and say so in words. Each row opens that year's decisions and tax return.
 */
export function YearTable({
  rows,
  view,
  onView,
  adaptive,
  horizon,
  retirementAge,
  shock,
  selected,
  onSelect,
  unavailableNote,
}: YearTableProps) {
  const section = adaptive?.status === "ready" ? adaptive.section : undefined;
  const yearByYear = view === "adaptive" && !!section;

  const columns: DataColumn<YearRow>[] = [
    {
      key: "age",
      header: "Age",
      rowHeader: true,
      width: "18%",
      cell: (row) => {
        const notes = [
          row.age === retirementAge ? "Retirement starts" : null,
          row.goal_paid > 0.5 ? `${row.goal_label ?? "Goal payment"} ${money(row.goal_paid)}` : null,
          shock && row.year_index === shock.year
            ? `Market ${shock.equity_return < 0 ? "falls" : "rises"} ${percent(Math.abs(shock.equity_return))}`
            : null,
        ].filter(Boolean);
        const departures = yearByYear && row.departs ? (row.departures ?? []) : null;
        return (
          <span className={styles.age}>
            <span className={styles.ageLine}>
              {row.age}
              {notes.length > 0 && <span className={styles.ageNote}>{notes.join(" · ")}</span>}
            </span>
            {departures && <span className={styles.changedTag}>{changedTag(departures)}</span>}
          </span>
        );
      },
    },
    // Each column has the room its heading's longest word needs ("conversion", "harvested", "(balance)"), so a narrow
    // window does not clip a heading or push the last column out of sight.
    { key: "income", header: "Income", align: "end", width: "12%", cell: (row) => money(row.income) },
    { key: "roth", header: "Roth conversion", align: "end", width: "16%", cell: (row) => amount(row.roth_conversion) },
    {
      key: "harvest",
      header: "Losses harvested",
      align: "end",
      width: "15%",
      cell: (row) => amount(row.losses_harvested),
    },
    {
      key: "bonds",
      header: "Goal bonds (balance)",
      align: "end",
      width: "15%",
      cell: (row) => amount(row.goal_bonds_balance),
    },
    { key: "stock", header: "Stock share", align: "end", width: "12%", cell: (row) => percent(row.stock_share) },
    { key: "tax", header: "Total tax", align: "end", width: "12%", cell: (row) => money(row.total_tax) },
  ];

  const first = rows[0]?.age;
  const last = rows[rows.length - 1]?.age;
  // Counted from the year-by-year plan's own rows, whichever view is showing (the other wording is kept for its room).
  const changedAges = section ? section.rows.filter((row) => row.departs).map((row) => row.age) : [];
  const noteHead = `${rows.length} years, ages ${first} to ${last}, running to ${horizon}. Scroll for the rest. Each year is at expected returns rather than a simulated future, so these figures are not the outcomes on the Comparison screen.`;

  return (
    <Panel aria-labelledby="year-table-title">
      <PanelTitle id="year-table-title" aside="Click a year for its decisions and tax return">
        Year by year
      </PanelTitle>

      <div className={styles.viewBar}>
        <ChipGroup label="Which plan the table shows">
          <Chip
            selected={yearByYear}
            disabled={!section}
            onClick={() => onView("adaptive")}
            title={section ? undefined : (unavailableNote ?? "The year-by-year plan is not ready")}
          >
            Year-by-year plan
          </Chip>
          <Chip selected={!yearByYear} onClick={() => onView("fixed")}>
            Fixed strategy
          </Chip>
        </ChipGroup>
        {/* The wordings share one cell (see `stacked`): the tallest sets the height, so switching views or the plan arriving moves nothing. */}
        {unavailableNote ? (
          <div className={styles.viewStatus}>
            <p>{unavailableNote}</p>
          </div>
        ) : (
          <div className={`${styles.viewStatus} ${styles.stacked}`} aria-live="polite">
            <p data-active={yearByYear} aria-hidden={yearByYear ? undefined : true}>
              {section ? (
                <>
                  <strong>
                    {changedAges.length} of {section.rows.length} years
                  </strong>{" "}
                  changed from the fixed strategy on this path
                  {changedAges.length > 0 ? ` (${agesList(changedAges)})` : ""}. Across {count(section.n_eval_paths)}{" "}
                  simulated futures the planner changes something in {percentTrim(section.departure_share)} of its
                  year-by-year decisions.
                </>
              ) : (
                // Not known yet: the room for it (the size of a typical sentence), never shown or read.
                `0 of ${rows.length} years changed from the fixed strategy on this path (ages 00, 00, 00, 00 and 00). Across 000 simulated futures the planner changes something in 0.0% of its year-by-year decisions.`
              )}
            </p>
            <p
              data-active={!yearByYear && adaptive?.status === "refining"}
              aria-hidden={!yearByYear && adaptive?.status === "refining" ? undefined : true}
            >
              Showing the fixed strategy until the year-by-year plan is ready.
            </p>
          </div>
        )}
      </div>

      {adaptive?.status === "failed" && (
        <div className={styles.notice}>
          <AdaptiveFailure message={adaptive.message}>
            The fixed strategy below is unaffected and still usable.
          </AdaptiveFailure>
        </div>
      )}

      <div className={styles.stacked}>
        <p className={styles.tableNote} data-active={!yearByYear} aria-hidden={yearByYear ? true : undefined}>
          {noteHead} A gold edge marks a year with a Roth conversion or a goal payment.
        </p>
        <p className={styles.tableNote} data-active={yearByYear} aria-hidden={yearByYear ? undefined : true}>
          {noteHead} A year where the planner changed something from the fixed strategy has a dark edge, a tint and a
          &ldquo;Changed&rdquo; tag.
        </p>
      </div>
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(row) => row.year_index}
        caption={`${yearByYear ? "Year-by-year plan" : "Fixed-strategy plan"}: income, Roth conversion, losses harvested, goal bonds, stock share and total tax${yearByYear ? ", with the years the planner changed marked" : ""}`}
        maxHeight={474}
        minWidth={580}
        selectedKey={selected}
        onRowActivate={(row) => onSelect(row.year_index)}
        rowTone={(row) => (yearByYear ? (row.departs ? "changed" : undefined) : isMarked(row) ? "marked" : undefined)}
        rowHint="Press Enter to see this year's decisions and tax return."
      />
    </Panel>
  );
}
