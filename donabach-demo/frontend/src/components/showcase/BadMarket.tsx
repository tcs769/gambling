import { money, percentTrim } from "@/lib/format";
import type { ShowcaseAnalysis } from "@/lib/types";
import styles from "./BadMarket.module.css";

/**
 * What a bad market does to each side: the 10th percentile is a future in which nine in ten do better, so its value at
 * the horizon is the floor most households stay above, and the share of futures in which the money runs out is the
 * risk the plan takes on. Both are written for Donabach and for the advisor, side by side, as the API measured them.
 */
export function BadMarket({ analysis, computing }: { analysis: ShowcaseAnalysis; computing: boolean }) {
  const { advantage, horizon_age: horizon, advisor_label: advisor } = analysis;
  const pairs = [
    {
      title: `The 10th percentile at ${horizon}`,
      note: "After-tax wealth in a bad-market future: nine in ten do better.",
      plan: money(advantage.plan_p10_at_horizon),
      advisor: money(advantage.advisor_p10_at_horizon),
    },
    {
      title: "Chance of running out of money",
      note: "The share of simulated futures in which savings cannot cover spending or a goal.",
      plan: percentTrim(advantage.plan_shortfall),
      advisor: percentTrim(advantage.advisor_shortfall),
    },
  ];
  return (
    <div className={styles.frame}>
      <div className={styles.grid} data-stale={computing}>
        {pairs.map((pair) => (
          <section key={pair.title} className={styles.card} aria-label={pair.title}>
            <h3 className={styles.title}>{pair.title}</h3>
            <p className={styles.note}>{pair.note}</p>
            <dl className={styles.values}>
              <div className={styles.value} data-entity="plan">
                <dt>
                  <span className={styles.key} aria-hidden="true" />
                  Donabach
                </dt>
                <dd>{pair.plan}</dd>
              </div>
              <div className={styles.value} data-entity="advisor">
                <dt>
                  <span className={styles.key} aria-hidden="true" />
                  {advisor}
                </dt>
                <dd>{pair.advisor}</dd>
              </div>
            </dl>
          </section>
        ))}
      </div>
    </div>
  );
}
