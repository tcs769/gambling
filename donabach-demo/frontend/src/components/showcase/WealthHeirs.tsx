import { Disclosure } from "@/components/ui";
import { money, percent, splitFirstSentence } from "@/lib/format";
import type { ShowcaseWealth } from "@/lib/types";
import { moreOrLess } from "./WealthHeadline";
import { ratePercent } from "./waterfallData";
import styles from "./WealthHeirs.module.css";

/**
 * The same plan and advisor with the estate passed to heirs at the horizon (the API's second valuation), under the headline:
 * the two medians at the horizon and the median advantage a year and in dollars. It is the median only: the risk-adjusted
 * advantage is shown once, in the headline, and there is none here. The API's note says what the valuation assumes and why its
 * rate is what it is: its first sentence is on the screen, the rest behind a disclosure (and all of it if there is only one).
 */
export function WealthHeirs({ wealth }: { wealth: ShowcaseWealth }) {
  const { heirs, advisor_label: advisor, horizon_age: horizon } = wealth;
  const { first, rest } = splitFirstSentence(heirs.note);
  return (
    <section className={styles.frame} aria-labelledby="heirs-title">
      <div className={styles.block}>
        <h2 id="heirs-title" className={styles.title}>
          {heirs.label}
        </h2>
        <dl className={styles.figures}>
          <div className={styles.figure} data-entity="plan">
            <dt>
              <span className={styles.key} aria-hidden="true" />
              Donabach, typical (median)
            </dt>
            <dd>{money(heirs.plan_median_at_horizon)}</dd>
          </div>
          <div className={styles.figure} data-entity="advisor">
            <dt>
              <span className={styles.key} aria-hidden="true" />
              {advisor}, typical (median)
            </dt>
            <dd>{money(heirs.advisor_median_at_horizon)}</dd>
          </div>
          <div className={styles.figure}>
            <dt>Median advantage</dt>
            <dd>
              {ratePercent(heirs.median_rate)}
              <span className={styles.unit}> a year</span>
            </dd>
            <dd className={styles.dollars}>{moreOrLess(heirs.median_dollars, horizon)}</dd>
          </div>
        </dl>
        {first && <p className={styles.note}>{first}</p>}
        {rest && (
          <Disclosure title={`Why ${percent(heirs.rate)}, and what is left out`} className={styles.fold}>
            <p className={styles.rest}>{rest}</p>
          </Disclosure>
        )}
      </div>
    </section>
  );
}
