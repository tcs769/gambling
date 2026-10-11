import { scoreDefinition } from "@/components/compare/measure";
import { Icon, Pill } from "@/components/ui";
import {
  changedTag,
  describeGap,
  differsIn,
  isBeforeShock,
  marketNote,
  retestLine,
} from "@/lib/adaptive";
import { count, money } from "@/lib/format";
import type { AdaptiveSection, PlanResponse, YearDecisionView } from "@/lib/types";
import styles from "./YearDrawer.module.css";

/**
 * "Why this year", for the year-by-year plan: what the planner does and what the fixed strategy would, its own
 * computed explanation, the next two best actions it scored with how far behind each was, and how the change held up
 * when re-tested on fresh futures. All of it is the API's: the numbers are dollars of the planner's rollout score.
 */
export function WhyThisYear({
  decision,
  section,
  plan,
}: {
  decision: YearDecisionView;
  section: AdaptiveSection;
  plan: PlanResponse;
}) {
  const shock = plan.settings.market_shock;
  const market = marketNote(decision, shock);
  const beforeDrop = isBeforeShock(decision.year_index, shock);
  const alternatives = decision.alternatives;

  return (
    <section className={styles.section} aria-labelledby="year-why">
      <h3 id="year-why">Why this year</h3>
      <p className={styles.caption}>
        The planner&apos;s own reasoning for age {decision.age}. It scores each action as certainty-equivalent after-tax
        wealth at {plan.settings.horizon_age} from simulated futures ({scoreDefinition(plan.settings)}).
      </p>

      {market && (
        <p className={styles.marketNote} role="note">
          <Icon name="alert" size={18} />
          <span>{market}</span>
        </p>
      )}
      {beforeDrop && (
        <p className={styles.quietNote}>
          This year is before the market drop in the what-if. The planner decides each year after that year&apos;s returns
          are known, so it cannot see the drop coming.
        </p>
      )}

      <div className={styles.actions}>
        <div className={styles.action} data-kind="chosen">
          <div className={styles.actionHead}>
            <span>The plan does</span>
            {decision.departs ? (
              <Pill tone="gold">{changedTag(decision.departures)}</Pill>
            ) : (
              <Pill icon={<Icon name="check" size={14} strokeWidth={2.6} />}>Keeps the fixed strategy&apos;s action</Pill>
            )}
          </div>
          <p className={styles.actionLabel}>{decision.chosen.label}</p>
        </div>
        <div className={styles.action}>
          <div className={styles.actionHead}>
            <span>The fixed strategy would</span>
          </div>
          <p className={styles.actionLabel}>{decision.fixed.label}</p>
        </div>
      </div>

      <p className={styles.why}>{decision.why}</p>

      {!decision.departs && (
        <p className={styles.small}>
          The planner scored {count(decision.candidates_scored)} candidate actions this year and kept the fixed strategy&apos;s
          action.
        </p>
      )}

      {alternatives.length > 0 ? (
        <>
          <h4 id="year-alternatives" className={styles.subheading}>
            {alternatives.length === 1 ? "The next best alternative" : `The next ${alternatives.length === 2 ? "two" : alternatives.length} best alternatives`}
          </h4>
          <ol className={styles.alternatives} aria-labelledby="year-alternatives">
            {alternatives.map((alternative, i) => {
              const gap = describeGap(alternative.ce_gap);
              return (
                <li key={`${alternative.action.label}-${i}`} className={styles.alternative}>
                  <strong>{alternative.action.label}</strong>
                  <span className={styles.gap} data-kind={gap.kind}>
                    {gap.text}
                  </span>
                  <span className={styles.differs}>
                    {alternative.differs_in.length > 0
                      ? `Differs from the chosen action in: ${differsIn(alternative)}`
                      : "Same decisions as the chosen action"}
                  </span>
                </li>
              );
            })}
          </ol>
          <p className={styles.small}>
            Each gap is the chosen action&apos;s rollout score minus the alternative&apos;s, in dollars of certainty-equivalent
            wealth at {plan.settings.horizon_age}, against a score of about {money(decision.ce_chosen)} for the chosen action.
            An alternative that scored higher still does not change the plan unless the gain is convincing: the planner
            changes an action only if it beats the one it holds by at least {section.z_min} standard error across its
            futures and then wins by {section.confirm_z} standard errors on {count(section.plan_path_confirm_k)} fresh futures.
          </p>
        </>
      ) : (
        <p className={styles.small}>No other action was scored this year.</p>
      )}

      <p className={styles.retest}>
        <strong>Re-test.</strong> {retestLine(decision, section)}
      </p>
    </section>
  );
}
