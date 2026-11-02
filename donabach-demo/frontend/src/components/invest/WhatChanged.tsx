import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { beforeAfter, wealth } from "@/lib/invest-format";
import styles from "./WhatChanged.module.css";

type Changed = NonNullable<Plan["what_changed"]>;

/** What the customer's last change did to the portfolio: labels and numbers, straight from the API. */
export function WhatChanged({ change, horizon }: { change: Changed; horizon: number }) {
  const moved = change.mix.filter((row) => row.moved);
  const conversionChanged = Math.round(change.conversion_before) !== Math.round(change.conversion_after);
  return (
    <section className={styles.block} aria-labelledby="what-changed-title" data-testid="what-changed">
      <h2 id="what-changed-title" className={styles.title}>
        What changed
      </h2>
      <ul className={styles.list}>
        <li className={styles.first}>
          <span className={styles.value}>{change.changed}</span>
        </li>
        {moved.map((row) => {
          const [before, after] = beforeAfter(row.before, row.after);
          return (
            <li key={row.key} data-testid="change-mix">
              <span className={styles.label}>{row.label}</span>
              <span className={`${styles.value} num`}>
                {before} → {after}
              </span>
            </li>
          );
        })}
        <li data-testid="change-wealth">
          <span className={styles.label}>Projected wealth at {horizon}:</span>
          <span className={`${styles.value} num`}>
            {wealth(change.wealth_before)} → {wealth(change.wealth_after)}
          </span>
        </li>
        {change.moves.map((move) => (
          <li key={`${move.kind}-${move.title}`} data-testid="change-move">
            <span className={styles.label}>
              {move.kind === "added" ? "New: " : move.kind === "removed" ? "Removed: " : ""}
              {move.title}:
            </span>
            <span className={`${styles.value} num`}>
              {move.kind === "added"
                ? move.after
                : move.kind === "removed"
                  ? move.before
                  : `${move.before ?? "—"} → ${move.after ?? "—"}`}
            </span>
          </li>
        ))}
        {conversionChanged && (
          <li data-testid="change-conversion">
            <span className={styles.label}>Roth conversion at {change.conversion_age}:</span>
            <span className={`${styles.value} num`}>
              {dollarsWhole(change.conversion_before)} → {dollarsWhole(change.conversion_after)}
            </span>
          </li>
        )}
      </ul>
    </section>
  );
}
