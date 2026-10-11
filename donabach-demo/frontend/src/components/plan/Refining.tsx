import type { ReactNode } from "react";
import { Icon, Pill, Spinner } from "@/components/ui";
import { percent } from "@/lib/format";
import type { AdaptiveState } from "@/lib/state";
import styles from "./Refining.module.css";

/** The words for a job's progress, "34%": the API reports it as a fraction. */
export const progressWords = (progress: number): string => percent(Math.min(1, Math.max(0, progress)));

/**
 * The page's state beside its title while the year-by-year plan is being worked out ("Refining plan... 34%"), or
 * a plain note that it could not be. Nothing when the plan is ready (or arrived with the response): then the page
 * simply has it. The percentage is for the eye; a screen reader hears only that the plan is being refined.
 */
export function RefiningPill({ adaptive }: { adaptive?: AdaptiveState }) {
  if (adaptive?.status === "refining") {
    return (
      <span role="status" className={styles.status}>
        <Pill tone="gold" icon={<Spinner size={14} />}>
          Refining plan…
          <span aria-hidden="true" className={styles.percent}>
            {progressWords(adaptive.progress)}
          </span>
        </Pill>
      </span>
    );
  }
  if (adaptive?.status === "failed") {
    return (
      <span role="status" className={styles.status}>
        <Pill tone="warn" icon={<Icon name="alert" size={14} />}>
          Year-by-year plan unavailable
        </Pill>
      </span>
    );
  }
  return null;
}

/** A thin bar for how far a job has got. It repeats the percentage written beside it, so it is hidden from screen readers. */
export function ProgressBar({ progress }: { progress: number }) {
  return (
    <span className={styles.bar} aria-hidden="true">
      <span className={styles.fill} style={{ width: progressWords(progress) }} />
    </span>
  );
}

/** The year-by-year plan failed: what the API said, and what is still there to use. */
export function AdaptiveFailure({ message, children }: { message?: string; children?: ReactNode }) {
  return (
    <div className={styles.failure} role="alert">
      <Icon name="alert" size={20} className={styles.failureIcon} />
      <div>
        <div className={styles.failureTitle}>The year-by-year plan could not be completed</div>
        {message && <p>{message}</p>}
        {children && <p>{children}</p>}
      </div>
    </div>
  );
}
