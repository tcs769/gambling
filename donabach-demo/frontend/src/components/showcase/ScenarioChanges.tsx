import { money, signedMoney } from "@/lib/format";
import type { ShowcaseScenario } from "@/lib/types";
import { ratePercent } from "./waterfall";
import styles from "./Scenario.module.css";

/** What choosing the plan again is worth after the event, with its sign in a word: "worth", "costs", or no difference. */
export function replanSentence(scenario: ShowcaseScenario): string {
  const { replan, plan_changed: changed, plan_label: planLabel, original_plan_label: originalLabel } = scenario;
  const horizon = scenario.wealth.horizon_age;
  const strategy = changed
    ? `the strategy ${planLabel} instead of ${originalLabel}`
    : `the strategy stays ${planLabel}`;
  const worth =
    replan.median_dollars === 0 && replan.median_rate === 0
      ? "It makes no difference to median wealth"
      : `It ${replan.median_dollars < 0 || (replan.median_dollars === 0 && replan.median_rate < 0) ? "costs" : "is worth"} ${ratePercent(replan.median_rate)} a year (${signedMoney(replan.median_dollars)} at ${horizon}) of median wealth`;
  return `Planning again: ${strategy}. ${worth}, on the same futures after the event.`;
}

/**
 * What Donabach changes because of the event: the API's `summary` sentences, then, when there are any, `replan_summary` under
 * "Planning again also changes", then one line on what choosing the plan again is worth. It prints what the API says and
 * nothing else about the outcome.
 */
export function ScenarioChanges({ scenario }: { scenario: ShowcaseScenario }) {
  const horizon = scenario.wealth.horizon_age;
  const { replan } = scenario;
  return (
    <div className={styles.changes}>
      {scenario.summary.length > 0 && (
        <ul className={styles.sentences} data-testid="summary" aria-label="What the plan does because of the event">
          {scenario.summary.map((sentence) => (
            <li key={sentence}>{sentence}</li>
          ))}
        </ul>
      )}
      {scenario.replan_summary.length > 0 && (
        <>
          <h3 className={styles.subtitle}>Planning again also changes</h3>
          <ul className={styles.sentences} data-testid="replan-summary" aria-label="What planning again also changes">
            {scenario.replan_summary.map((sentence) => (
              <li key={sentence}>{sentence}</li>
            ))}
          </ul>
        </>
      )}
      <p className={styles.replan} data-testid="replan" data-sign={Math.sign(replan.median_dollars)}>
        {replanSentence(scenario)}
      </p>
      <p className={styles.quiet}>
        Median wealth at {horizon} on the same shocked futures: {money(replan.original_plan_median_at_horizon)} with the
        original plan, {money(replan.replanned_median_at_horizon)} with the plan chosen again.
      </p>
    </div>
  );
}
