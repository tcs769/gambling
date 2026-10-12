import { MEASURES } from "@/components/compare/AdvantagePanel";
import { count, money, signedMoney } from "@/lib/format";
import type { ShowcaseWealth } from "@/lib/types";
import { ratePercent } from "./waterfall";
import styles from "./WealthHeadline.module.css";

/** "$2.8M more at 80", "$12k less at 80", or that there is no difference. */
function moreOrLess(dollars: number, horizon: number): string {
  if (Math.abs(dollars) < 0.5) return `no difference at ${horizon}`;
  return `${money(Math.abs(dollars))} ${dollars > 0 ? "more" : "less"} at ${horizon}`;
}

/**
 * The whole plan's advantage in two measures, side by side above the chart: the one place the risk-adjusted advantage is
 * shown. The median advantage is the difference between the typical futures; the risk-adjusted one counts bad futures for
 * more, so a plan that takes more risk is credited less for what it earns. Each is a yearly rate, what it comes to in
 * dollars at the horizon, and one line that says what it is (the risk-adjusted label and line are the API's own words).
 */
export function WealthHeadline({ wealth }: { wealth: ShowcaseWealth }) {
  const { advantage, horizon_age: horizon } = wealth;
  const range = advantage.median_low !== 0 || advantage.median_high !== 0;
  return (
    <div className={styles.frame}>
      <section
        className={styles.headline}
        aria-label={`Donabach's advantage over a ${wealth.advisor_label.toLowerCase()}`}
      >
        <div className={styles.cell}>
          <h2 className={styles.label}>Median advantage</h2>
          <p className={styles.figures}>
            <span className={styles.big}>{ratePercent(advantage.median_rate)}</span>
            <span className={styles.unit}> a year</span>
          </p>
          <p className={styles.dollars}>
            <strong>{moreOrLess(advantage.median_dollars, horizon)}</strong>
          </p>
          <p className={styles.line}>{MEASURES[0].definition(horizon, wealth.risk_aversion)}</p>
          {range && (
            <p className={styles.range}>
              90% range when the {count(wealth.n_paths)} futures are resampled: {ratePercent(advantage.median_low)} to{" "}
              {ratePercent(advantage.median_high)} a year
            </p>
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
        </div>
      </section>
    </div>
  );
}
