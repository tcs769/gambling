import { Panel, PanelTitle } from "@/components/ui";
import { count } from "@/lib/format";
import type { PlanResponse } from "@/lib/types";
import { StyleFigures, hasZeroRange } from "./StyleFigures";
import styles from "./StyleResults.module.css";

/**
 * What one planning style's plan comes to, in a panel of its own (the plan in the style the switch is on, when it is not the
 * default one, whose results are on the Comparison screen). The same sections as a column of the side-by-side view.
 */
export function StyleResults({ plan, name }: { plan: PlanResponse; name: string }) {
  return (
    <Panel aria-labelledby="style-results-title">
      <PanelTitle
        id="style-results-title"
        aside={`After tax, in 2026 dollars · measured on ${count(plan.settings.n_eval_paths)} fresh futures`}
      >
        How the {name.toLowerCase()} plan does
      </PanelTitle>
      <div className={styles.grid}>
        <StyleFigures plan={plan} id="style-results" />
      </div>
      <p className={styles.note}>
        {hasZeroRange(plan) ? (
          <>
            <strong>†</strong> The 90% range includes zero, so that advantage is not distinguishable from no effect.
          </>
        ) : (
          <>
            No advantage here has a 90% range that includes zero; a <strong>†</strong> would mark one that did.
          </>
        )}
      </p>
    </Panel>
  );
}
