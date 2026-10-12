import { money, signedMoney } from "@/lib/format";
import type { ShowcaseWealth } from "@/lib/types";
import { ratePercent } from "./waterfall";
import { moreOrLess } from "./WealthHeadline";
import styles from "./WealthHeadline.module.css";

/**
 * The household after an event, in both measures of the advantage and in the same box as the wealth screen's headline but
 * compact: after the event, Donabach's and the advisor's median at the horizon, the median advantage a year and in dollars,
 * the risk-adjusted advantage once, and, beside each, what it was for the unchanged household (`before`) so the viewer sees
 * what the event did. The valuation (liquidated) is named on top; the heirs' valuation is one small line. All the API's numbers.
 */
export function ScenarioHeadline({ wealth, before }: { wealth: ShowcaseWealth; before: ShowcaseWealth | null }) {
  const { advantage, horizon_age: horizon, heirs } = wealth;
  const advisor = wealth.advisor_label;
  return (
    <div className={styles.frame}>
      <section className={styles.headline} aria-label={`Donabach's advantage over a ${advisor.toLowerCase()}`}>
        <p className={styles.valuation}>{wealth.liquidated_label}</p>
        <div className={styles.cell}>
          <h2 className={styles.label}>Median advantage</h2>
          <p className={styles.figures}>
            <span className={styles.big}>{ratePercent(advantage.median_rate)}</span>
            <span className={styles.unit}> a year</span>
          </p>
          <p className={styles.dollars}>
            <strong>{moreOrLess(advantage.median_dollars, horizon)}</strong>
          </p>
          <p className={styles.line}>
            Typical (median) wealth at {horizon}: Donabach <strong>{money(advantage.plan_median_at_horizon)}</strong>,{" "}
            {advisor} <strong>{money(advantage.advisor_median_at_horizon)}</strong>.
          </p>
          {before && (
            <p className={styles.before}>Before the event: {ratePercent(before.advantage.median_rate)} a year</p>
          )}
        </div>
        <div className={styles.cell}>
          <h2 className={styles.label}>{wealth.risk_adjusted_label}</h2>
          <p className={styles.figures}>
            <span className={styles.big}>{ratePercent(advantage.risk_adjusted_rate)}</span>
            <span className={styles.unit}> a year</span>
          </p>
          <p className={styles.dollars}>
            <strong>
              {signedMoney(advantage.risk_adjusted_dollars)} at {horizon}
            </strong>{" "}
            on the wealth you can count on
          </p>
          <p className={styles.line}>{wealth.risk_adjusted_explanation}</p>
          {before && (
            <p className={styles.before}>Before the event: {ratePercent(before.advantage.risk_adjusted_rate)} a year</p>
          )}
        </div>
        <p className={styles.about}>
          {heirs.label}: Donabach <strong>{money(heirs.plan_median_at_horizon)}</strong>, {advisor}{" "}
          <strong>{money(heirs.advisor_median_at_horizon)}</strong>, a median advantage of{" "}
          <strong>{ratePercent(heirs.median_rate)} a year</strong> ({moreOrLess(heirs.median_dollars, horizon)}).
        </p>
      </section>
    </div>
  );
}
