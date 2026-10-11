import { Panel, PanelTitle } from "@/components/ui";
import { count, dollars } from "@/lib/format";
import type { PlanResponse } from "@/lib/types";
import { SCREEN_FUTURES, menuSummary } from "./measure";
import styles from "./Compare.module.css";

/**
 * A short account of how the numbers on this screen were produced: which futures each one was
 * measured on, why the plan's own results use ones the search never saw, and what a range is.
 */
export function HowWeMeasure({ plan }: { plan: PlanResponse }) {
  const s = plan.settings;
  const { menu, screened } = menuSummary(plan);
  return (
    <Panel id="how-we-measure" className={styles.anchor} aria-labelledby="how-we-measure-title">
      <PanelTitle id="how-we-measure-title" aside={`After tax, in 2026 dollars, at age ${s.horizon_age}`}>
        How we measure
      </PanelTitle>
      <ul className={styles.measureList}>
        <li>
          <strong>Fresh futures for the verdict.</strong> The plan and both advisors are measured on the same{" "}
          {count(s.n_eval_paths)} simulated futures, ones the strategy search never saw. Picking the best of{" "}
          {count(menu)} strategies and then scoring it on the futures it was picked on would flatter it.
        </li>
        <li>
          <strong>Search futures for the ranking.</strong> The table of strategies is scored on {count(s.n_paths)} search
          futures
          {screened ? ` (each strategy was screened on ${count(SCREEN_FUTURES)} of them first)` : ""}, so its figures are
          not the plan&apos;s results above.
        </li>
        <li>
          <strong>Ranges.</strong> A 90% range is the 5th to the 95th percentile of an advantage when the{" "}
          {count(s.n_eval_paths)} futures are resampled. The risk-adjusted measure scores wealth with risk aversion{" "}
          {s.risk_aversion} and counts anything below {dollars(s.wealth_floor)} as {dollars(s.wealth_floor)}.
        </li>
      </ul>
    </Panel>
  );
}
