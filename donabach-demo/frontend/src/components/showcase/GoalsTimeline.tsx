import type { CSSProperties } from "react";
import type { CardGoal } from "@/lib/types";
import styles from "./GoalsTimeline.module.css";

type DatedGoal = CardGoal & { years_from_now: number };
const isDated = (goal: CardGoal): goal is DatedGoal => typeof goal.years_from_now === "number";

/**
 * What the household is saving for, on a line from today to the age the plan runs to: a mark for each goal where it
 * falls, joined to its text below (the goal, the age, and the API's detail sentence). Goals are in the order they
 * happen, so the text columns never cross; a narrow card drops the line and stacks the goals down a rail instead.
 * The line only shows when each goal falls; everything it says is written in the list, so it is hidden from screen readers.
 */
export function GoalsTimeline({
  goals,
  startAge,
  endAge,
}: {
  goals: readonly CardGoal[];
  startAge: number | undefined;
  endAge: number;
}) {
  const dated = goals.filter(isDated).sort((a, b) => a.years_from_now - b.years_from_now);
  const undated = goals.filter((goal) => !isDated(goal));
  const span = startAge === undefined ? 0 : Math.max(1, endAge - startAge);
  // Where a goal falls along the line, as a share of it (a goal past the end of the plan sits at the end).
  const at = (goal: DatedGoal) => Math.min(1, Math.max(0, goal.years_from_now / span)) * 100;
  const n = dated.length;

  return (
    <div className={styles.wrap}>
      {startAge !== undefined && n > 0 && (
        <div className={styles.map} aria-hidden="true">
          <span className={styles.end} data-side="start">
            Today, age {startAge}
          </span>
          <span className={styles.end} data-side="end">
            Age {endAge}
          </span>
          <span className={styles.line} />
          <svg className={styles.fan} viewBox="0 0 100 48" preserveAspectRatio="none" focusable="false">
            {dated.map((goal, i) => {
              const x = at(goal);
              const column = ((i + 0.5) / n) * 100;
              return <polyline key={goal.key} points={`${x},0 ${x},12 ${column},32 ${column},48`} />;
            })}
          </svg>
          {dated.map((goal) => (
            <span key={goal.key} className={styles.marker} data-goal={goal.key} style={{ left: `${at(goal)}%` }} />
          ))}
        </div>
      )}

      {n > 0 && (
        <ol className={styles.goals} style={{ "--n": n } as CSSProperties}>
          {dated.map((goal) => (
            <li key={goal.key} className={styles.goal} data-goal={goal.key}>
              {startAge !== undefined && <span className={styles.age}>Age {startAge + goal.years_from_now}</span>}
              <strong className={styles.title}>{goal.label}</strong>
              <span className={styles.detail}>{goal.detail}</span>
            </li>
          ))}
        </ol>
      )}

      {undated.length > 0 && (
        <ul className={styles.undated} aria-label="Goals without a date">
          {undated.map((goal) => (
            <li key={goal.key}>
              <strong className={styles.title}>{goal.label}</strong>{" "}
              <span className={styles.detail}>{goal.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
