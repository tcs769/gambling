"use client";

import { useState } from "react";
import { RankedStrategyCell } from "@/components/plan/RankedStrategy";
import { Button, DataTable, Icon, Panel, PanelTitle, Pill, type DataColumn } from "@/components/ui";
import { money } from "@/lib/format";
import type { PlanResponse, RankedRow } from "@/lib/types";
import styles from "./Compare.module.css";

/** How many strategies show before "Show all". */
const TOP = 10;

const COLUMNS: DataColumn<RankedRow>[] = [
  { key: "rank", header: "Rank", rowHeader: true, width: "8%", cell: (row) => row.rank },
  { key: "strategy", header: "Strategy", cell: (row) => <RankedStrategyCell row={row} /> },
  { key: "median", header: "Typical outcome", align: "end", width: "15%", cell: (row) => money(row.median) },
  { key: "p10", header: "Bad case", align: "end", width: "13%", cell: (row) => money(row.p10) },
  { key: "score", header: "Score", align: "end", width: "13%", cell: (row) => money(row.score) },
];

/** The strategies the planner scored, best first. The chosen one is highlighted; ties say so. */
export function SearchedTable({ plan }: { plan: PlanResponse }) {
  const [expanded, setExpanded] = useState(false);
  const all = plan.searched;
  // The strategy that was chosen (and the model's pick) stay visible even if they rank below the top.
  const shown = expanded ? all : all.filter((row, i) => i < TOP || row.is_chosen || row.is_model_pick);
  const hidden = all.length - shown.length;

  return (
    <Panel>
      <PanelTitle aside={<Pill icon={<Icon name="info" size={14} />}>{plan.planner_label}</Pill>}>
        Strategies searched
      </PanelTitle>
      <p className={styles.sectionNote}>
        {all.length} strategies, all run on the same simulated futures and ranked by score: certainty-equivalent wealth at 70
        (the guaranteed amount that would feel as good as the uncertain outcome; risk aversion 3, with a $50,000 floor).
        Typical outcome is the median future and bad case is the 10th percentile.
      </p>
      <DataTable
        columns={COLUMNS}
        rows={shown}
        rowKey={(row) => row.rank}
        caption="Strategies searched, ranked by score"
        maxHeight={expanded ? 560 : undefined}
        rowTone={(row) => (row.is_chosen ? "highlight" : row.is_model_pick ? "marked" : undefined)}
      />
      {all.length > shown.length || expanded ? (
        <div className={styles.expander}>
          <Button variant="secondary" aria-expanded={expanded} onClick={() => setExpanded((open) => !open)}>
            {expanded ? `Show the top ${TOP} only` : `Show all ${all.length} strategies`}
          </Button>
          {!expanded && hidden > 0 && <span className={styles.sectionNote}>{hidden} more are hidden.</span>}
        </div>
      ) : null}
    </Panel>
  );
}
