import { Disclosure, Panel, PanelTitle } from "@/components/ui";
import { rangeSentence } from "@/lib/adaptive";
import { count, rateDigits, signedMoney, signedPercent } from "@/lib/format";
import type { AdaptiveSection, PlanResponse } from "@/lib/types";
import { MEASURES } from "./AdvantagePanel";
import { RangeBar, scaleFor } from "./RangeBar";
import advantage from "./Advantage.module.css";
import styles from "./Judgment.module.css";

/** Two significant figures: 0.0624 seconds, 14 seconds. */
const seconds = (value: number): string => `${Number(value.toPrecision(2))} seconds`;

/**
 * What judgment over time adds: the adaptive planner against the best fixed strategy, on the same futures, as the
 * median and the risk-adjusted advantage a year, each with the 90% range it falls in and its dollars at the horizon.
 * Each figure is followed by what its range says about "no effect", no more strongly than the range allows.
 * Below it, folded away, how the planner works: the settings it ran with and the API's own account of its search.
 */
export function JudgmentPanel({ plan, section }: { plan: PlanResponse; section: AdaptiveSection }) {
  const { horizon_age: horizon, risk_aversion: riskAversion } = plan.settings;
  const value = section.value_of_judgment;
  const scale = scaleFor(MEASURES.map((measure) => measure.pick(value)));

  return (
    <Panel aria-labelledby="judgment-title">
      <PanelTitle id="judgment-title" aside={`Measured on ${count(section.n_eval_paths)} fresh futures`}>
        What judgment over time adds
      </PanelTitle>
      <p className={advantage.intro}>
        The adaptive planner against the best fixed strategy, on the same futures: what it adds to re-choose each
        year&apos;s decisions after that year&apos;s returns are known, instead of following the best fixed strategy all the way.
        Positive means the adaptive planner ends ahead. Each figure comes with the 90% range it would fall in if the
        simulated futures were resampled.
      </p>
      <div className={styles.cells}>
        {MEASURES.map((measure) => {
          const now = measure.pick(value);
          // A figure this small needs a third decimal to show more than "+0.02%" for two different dollar amounts.
          const digits = rateDigits(now.value, now.low, now.high);
          return (
            <div
              key={measure.id}
              className={advantage.cell}
              role="group"
              aria-label={`${measure.label} of the adaptive planner over the best fixed strategy`}
            >
              <div className={advantage.against}>{measure.label}</div>
              <p className={styles.definition}>{measure.definition(horizon, riskAversion)}</p>
              <div className={advantage.value}>
                <span className={advantage.figure}>{signedPercent(now.value, digits)}</span>
                <span className={advantage.unit}> a year</span>
              </div>
              <RangeBar value={now.value} low={now.low} high={now.high} scale={scale} />
              <p className={advantage.range}>
                90% range: {signedPercent(now.low, digits)} to {signedPercent(now.high, digits)} when the futures are resampled
              </p>
              <p className={advantage.dollars}>
                <strong>{signedMoney(now.dollars)}</strong> {measure.dollarsOf(horizon)}
              </p>
              <p className={styles.verdict}>{rangeSentence(now.low, now.high, digits)}</p>
            </div>
          );
        })}
      </div>

      <Disclosure title="How the year-by-year planner works" className={styles.how}>
        <div className={styles.howBody}>
          <p className={styles.search}>{section.search}</p>
          <dl className={styles.settings} aria-label="The planner's settings">
            <div>
              <dt>Futures scored for each candidate action</dt>
              <dd>{count(section.k)}</dd>
            </div>
            <div>
              <dt>Fresh futures a proposed change is re-tested on</dt>
              <dd>
                {count(section.confirm_k)}
                <span>, and it must win by {section.confirm_z} standard errors</span>
              </dd>
            </div>
            <div>
              <dt>Futures the verdict is measured on</dt>
              <dd>{count(section.n_eval_paths)}</dd>
            </div>
            <div>
              <dt>Computing time</dt>
              <dd>
                {seconds(section.seconds_per_path)}
                <span> per simulated future; the whole year-by-year plan took {seconds(section.elapsed_seconds)}</span>
              </dd>
            </div>
          </dl>
        </div>
      </Disclosure>
    </Panel>
  );
}
