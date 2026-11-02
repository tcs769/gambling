import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { feeLine, wealth } from "@/lib/invest-format";
import styles from "./SummaryStrip.module.css";

/** The four figures that stay above every tab. */
export function SummaryStrip({ summary }: { summary: Plan["portfolio"]["summary"] }) {
  return (
    <section className={styles.strip} aria-label="Summary" data-testid="summary">
      <div className={`${styles.cell} ${styles.lead}`}>
        <p className={styles.label}>Projected wealth at {summary.horizon_age}</p>
        <p className={`${styles.big} num`} data-testid="projected-wealth">
          {wealth(summary.projected_wealth)}
        </p>
      </div>
      <div className={styles.cell}>
        <p className={styles.label}>Invested today</p>
        <p className={`${styles.value} num`} data-testid="invested-today">
          {dollarsWhole(summary.invested_today)}
        </p>
      </div>
      <div className={styles.cell}>
        <p className={styles.label}>Yearly fee</p>
        <p className={`${styles.value} num`} data-testid="yearly-fee">
          {feeLine(summary.fee_dollars, summary.fee_rate)}
        </p>
      </div>
      <div className={styles.cell}>
        <p className={styles.label}>Estimated tax saved this year</p>
        <p className={`${styles.value} num`} data-testid="tax-saved">
          {dollarsWhole(summary.tax_saved)}
        </p>
      </div>
    </section>
  );
}
