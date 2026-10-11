import { count, money, signedMoney } from "@/lib/format";
import type { ShowcaseAnalysis } from "@/lib/types";
import { ratePercent } from "./waterfall";
import styles from "./TotalPanel.module.css";

/**
 * The total the waterfall adds up to, in large type: the yearly advantage and the dollars it is worth at the horizon,
 * measured as the median of the simulated futures, and the median after-tax wealth each side ends with.
 */
export function TotalPanel({ analysis, computing }: { analysis: ShowcaseAnalysis; computing: boolean }) {
  const { advantage, horizon_age: horizon } = analysis;
  const on = analysis.bars.filter((bar) => bar.enabled).length;
  return (
    <div className={styles.frame}>
    <section className={styles.total} aria-labelledby="total-title" data-stale={computing}>
      <div className={styles.main}>
        <h2 id="total-title" className={styles.kicker}>
          Donabach&apos;s advantage over a {analysis.advisor_label.toLowerCase()}
        </h2>
        <p className={styles.headline}>
          <span className={styles.figure}>
            <span className={styles.big}>{ratePercent(advantage.median_rate)}</span>
            <span className={styles.unit}> a year</span>
          </span>
          <span className={styles.figure}>
            <span className={styles.big}>{signedMoney(advantage.median_dollars)}</span>
            <span className={styles.unit}> at {horizon}</span>
          </span>
        </p>
        <p className={styles.basis}>
          Median of {count(analysis.n_paths)} simulated futures.{" "}
          {on === analysis.bars.length ? `All ${on} strategies on.` : `${on} of ${analysis.bars.length} strategies on.`}
        </p>
      </div>
      <dl className={styles.medians}>
        <div className={styles.median}>
          <dt>{analysis.advisor_label}</dt>
          <dd>{money(advantage.advisor_median_at_horizon)}</dd>
        </div>
        <div className={styles.median}>
          <dt>Donabach</dt>
          <dd>{money(advantage.plan_median_at_horizon)}</dd>
        </div>
        <p className={styles.mediansNote}>median after-tax wealth at {horizon}</p>
      </dl>
    </section>
    </div>
  );
}
