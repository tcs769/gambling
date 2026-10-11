"use client";

import { Button, Icon, Spinner } from "@/components/ui";
import { useApp } from "@/lib/state";
import styles from "./WhatIf.module.css";

/**
 * Above the content whenever a what-if is on screen or being worked out: what changed, a way back
 * to the base plan, and a quiet "Re-planning..." while it runs. It appears as soon as the re-plan
 * starts, so the content does not shift again when the answer arrives. Reset sits right after the
 * text (not at the far edge) so a side drawer opened over the page never covers it.
 */
export function WhatIfBanner() {
  const { state, actions, whatIfActive } = useApp();
  const loading = state.loading.whatIf;
  if (!whatIfActive && !loading) return null;
  const changes = state.whatIf?.response.changes ?? [];

  return (
    <div className={styles.reveal}>
      <div className={styles.revealInner}>
        <div className={styles.banner} aria-live="polite">
          <Icon name="sliders" size={20} className={styles.bannerIcon} />
          <p className={styles.bannerText}>
            {whatIfActive ? (
              <>
                <strong>What-if applied:</strong>{" "}
                {changes.length > 0
                  ? changes.map((change, i) => (
                      <span key={`${change.field}-${i}`} className={styles.bannerChange}>
                        {change.label} {change.before} <span aria-hidden="true">→</span>
                        <span className="sr-only">to</span> {change.after}
                      </span>
                    ))
                  : "no difference from your plan."}
              </>
            ) : (
              <strong>What-if</strong>
            )}
          </p>
          <Button
            variant="secondary"
            className={styles.bannerReset}
            onClick={actions.resetWhatIf}
            disabled={loading || !whatIfActive}
          >
            Reset
          </Button>
          {loading && <Spinner label="Re-planning..." />}
        </div>
      </div>
    </div>
  );
}
