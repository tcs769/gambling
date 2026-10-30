import { count, money, signedMoney } from "@/lib/format";
import type { ShowcaseWaterfall } from "@/lib/types";
import { strategiesOn } from "./text";
import { ratePercent } from "./waterfallData";
import styles from "./TotalPanel.module.css";

/**
 * The total the waterfall adds up to, in large type: the yearly advantage and the dollars it is worth at the horizon,
 * measured as the median of the simulated futures, and the median after-tax wealth each side ends with.
 */
export function TotalPanel({ waterfall, computing }: { waterfall: ShowcaseWaterfall; computing: boolean }) {
  const { advantage, horizon_age: horizon } = waterfall;
  const on = waterfall.bars.filter((bar) => bar.enabled).length;
  return (
    <div className={styles.frame}>
      <section className={styles.total} aria-labelledby="total-title" data-stale={computing}>
        <div className={styles.main}>
          <h2 id="total-title" className={styles.kicker}>
            Donabach&apos;s advantage over a {waterfall.advisor_label.toLowerCase()}
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
            Median of {count(waterfall.n_paths)} simulated futures.
            {waterfall.bars.length > 0 && ` ${strategiesOn(on, waterfall.bars.length)}.`}
          </p>
        </div>
        <div className={styles.medians}>
          <dl className={styles.pair}>
            <div className={styles.median}>
              <dt>{waterfall.advisor_label}</dt>
              <dd>{money(advantage.advisor_median_at_horizon)}</dd>
            </div>
            <div className={styles.median}>
              <dt>Donabach</dt>
              <dd>{money(advantage.plan_median_at_horizon)}</dd>
            </div>
          </dl>
          <p className={styles.mediansNote}>median after-tax wealth at {horizon}</p>
        </div>
      </section>
    </div>
  );
}
