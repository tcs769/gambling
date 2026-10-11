import { AdaptiveFailure, ProgressBar, progressWords } from "@/components/plan/Refining";
import { Panel, PanelTitle, Spinner } from "@/components/ui";
import type { AdaptiveState } from "@/lib/state";
import styles from "./AdaptivePlaceholder.module.css";

/**
 * Where the year-by-year plan's panels will appear on the Comparison screen while it is being refined: a calm
 * "Refining plan..." with its progress, in panels about the size of the real ones. If the job failed, the plain
 * error (and that everything above is unaffected); if the API sent no year-by-year plan, one sentence saying so.
 */
export function AdaptivePlaceholder({ adaptive }: { adaptive?: AdaptiveState }) {
  if (adaptive?.status === "failed") {
    return (
      <Panel aria-labelledby="adaptive-placeholder-title">
        <PanelTitle id="adaptive-placeholder-title">Year-by-year plan</PanelTitle>
        <AdaptiveFailure message={adaptive.message}>
          The fixed-strategy results on this screen are final and unaffected; only the four-way comparison and what
          judgment over time adds are missing.
        </AdaptiveFailure>
      </Panel>
    );
  }
  if (adaptive?.status !== "refining") {
    return (
      <Panel aria-labelledby="adaptive-placeholder-title">
        <PanelTitle id="adaptive-placeholder-title">Year-by-year plan</PanelTitle>
        <p className={styles.quiet}>There is no year-by-year plan for this plan, so only the fixed-strategy results are shown.</p>
      </Panel>
    );
  }
  return (
    <div className={styles.stack}>
      {/* Two panels, the size of the four-way comparison and of "What judgment over time adds" (see the CSS). */}
      {(["fourway", "judgment"] as const).map((room, i) => (
        <Panel
          key={room}
          className={styles.block}
          data-room={room}
          aria-busy="true"
          aria-labelledby={i === 0 ? "adaptive-placeholder-title" : undefined}
          aria-hidden={i === 0 ? undefined : "true"}
        >
          {i === 0 && (
            <div className={styles.body}>
              <PanelTitle id="adaptive-placeholder-title">Year-by-year plan</PanelTitle>
              <Spinner label="Refining plan…" />
              <p className={styles.progress}>
                <ProgressBar progress={adaptive.progress} />
                <span aria-hidden="true">{progressWords(adaptive.progress)}</span>
              </p>
              <p className={styles.quiet}>
                The fixed-strategy results on this screen are final. The planner is now re-choosing each year&apos;s decisions
                on the simulated futures. The four-way comparison and what judgment over time adds appear here when it is done.
              </p>
            </div>
          )}
        </Panel>
      ))}
    </div>
  );
}
