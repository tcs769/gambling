import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { percentTrim, wealth } from "@/lib/invest-format";
import styles from "./SummaryStrip.module.css";

/** The four figures that stay above every tab. */
export function SummaryStrip({ summary }: { summary: Plan["portfolio"]["summary"] }) {
  return (
    <section className={styles.summary} aria-label="Summary" data-testid="summary">
      <div className={`${styles.sum} ${styles.main}`}>
        <span>Projected at {summary.horizon_age}</span>
        <b className="num" data-testid="projected-wealth">
          {wealth(summary.projected_wealth)}
        </b>
      </div>
      <div className={styles.sum}>
        <span>Total savings</span>
        <b className="num" data-testid="invested-today">
          {dollarsWhole(summary.invested_today)}
        </b>
      </div>
      <div className={styles.sum}>
        <span>Yearly fee</span>
        <b className="num" data-testid="yearly-fee">
          {dollarsWhole(summary.fee_dollars)}
        </b>
        <em data-testid="fee-rate">{percentTrim(summary.fee_rate)} of managed accounts</em>
      </div>
      <div className={styles.sum}>
        <span>Tax saved this year</span>
        <b className="num" data-testid="tax-saved">
          {dollarsWhole(summary.tax_saved)}
        </b>
        <em>estimated</em>
      </div>
    </section>
  );
}
