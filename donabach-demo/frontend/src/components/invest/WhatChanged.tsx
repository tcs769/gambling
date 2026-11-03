import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { beforeAfter, wealth } from "@/lib/invest-format";
import styles from "./WhatChanged.module.css";

type Changed = NonNullable<Plan["what_changed"]>;

function Cell({ label, testId, children }: { label: string; testId: string; children: React.ReactNode }) {
  return (
    <div data-testid={testId}>
      <span className={styles.label}>{label}</span>
      <b className={`${styles.value} num`}>{children}</b>
    </div>
  );
}

/** What the customer's last change did to the portfolio: labels and numbers, straight from the API. */
export function WhatChanged({ change, horizon }: { change: Changed; horizon: number }) {
  const moved = change.mix.filter((row) => row.moved);
  const conversionChanged = Math.round(change.conversion_before) !== Math.round(change.conversion_after);
  const conversionLabel = `Roth conversion at ${change.conversion_age}`;
  // The conversion cell already says it, with plain dollars: the move of the same name is not shown twice.
  const moves = change.moves.filter((move) => !(conversionChanged && move.title === conversionLabel));
  return (
    <section className={styles.changed} aria-labelledby="what-changed-title" data-testid="what-changed">
      <div className={styles.chead}>
        <h2 id="what-changed-title" className={styles.title}>
          What changed
        </h2>
        <span className={styles.what}>{change.changed}</span>
      </div>
      <div className={styles.cgrid}>
        {conversionChanged && (
          <Cell label={conversionLabel} testId="change-conversion">
            {dollarsWhole(change.conversion_before)} → {dollarsWhole(change.conversion_after)}
          </Cell>
        )}
        <Cell label={`Projected at ${horizon}`} testId="change-wealth">
          {wealth(change.wealth_before)} → {wealth(change.wealth_after)}
        </Cell>
        {moved.map((row) => {
          const [before, after] = beforeAfter(row.before, row.after);
          return (
            <Cell key={row.key} label={row.label} testId="change-mix">
              {before} → {after}
            </Cell>
          );
        })}
        {moves.map((move) => (
          <Cell key={`${move.kind}-${move.title}`} label={move.title} testId="change-move">
            {move.kind === "added"
              ? "Added"
              : move.kind === "removed"
                ? "Removed"
                : `${move.before ?? "—"} → ${move.after ?? "—"}`}
          </Cell>
        ))}
      </div>
    </section>
  );
}
