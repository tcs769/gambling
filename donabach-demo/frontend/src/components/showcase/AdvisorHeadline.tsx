import { count, money, percentTrim } from "@/lib/format";
import type { ShowcaseWealth } from "@/lib/types";
import styles from "./WealthHeadline.module.css";

/**
 * The advisor's own result at the horizon, alone: before Donabach is shown, this is all the screen says. The typical (median)
 * household's after-tax wealth, a bad market's (the 10th percentile: nine in ten futures do better), the chance of running out
 * of money, and one line on what a good advisor does. Every figure is the API's (`wealth.advantage`); the line on what the
 * advisor does carries no number.
 */
export function AdvisorHeadline({ wealth }: { wealth: ShowcaseWealth }) {
  const { advantage, horizon_age: horizon } = wealth;
  const advisor = wealth.advisor_label.toLowerCase();
  return (
    <div className={styles.frame}>
      <section className={styles.headline} aria-label={`What a ${advisor} gets this household`}>
        <p className={styles.valuation}>{wealth.liquidated_label}</p>
        <div className={styles.cell}>
          <h2 className={styles.label}>A {advisor}&apos;s typical household</h2>
          <p className={styles.figures}>
            <span className={styles.big}>{money(advantage.advisor_median_at_horizon)}</span>
            <span className={styles.unit}> at {horizon}</span>
          </p>
          <p className={styles.line}>
            The typical (median) after-tax wealth at {horizon}, in 2026 dollars, over {count(wealth.n_paths)} simulated
            futures.
          </p>
        </div>
        <div className={styles.cell}>
          <h2 className={styles.label}>In a bad market</h2>
          <p className={styles.figures}>
            <span className={styles.big}>{money(advantage.advisor_p10_at_horizon)}</span>
            <span className={styles.unit}> at {horizon}</span>
          </p>
          <p className={styles.line}>
            The 10th percentile: nine in ten futures do better. The chance of running out of money is{" "}
            <strong>{percentTrim(advantage.advisor_shortfall)}</strong>.
          </p>
        </div>
        <p className={styles.about}>
          What a {advisor} does: an age-based portfolio, standard advisory fees, and every account managed separately.
        </p>
      </section>
    </div>
  );
}
