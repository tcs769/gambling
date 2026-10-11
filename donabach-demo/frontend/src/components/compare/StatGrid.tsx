import { StatCard } from "@/components/ui";
import { money, signedMoney } from "@/lib/format";
import type { PlanResponse } from "@/lib/types";
import { Delta } from "./Delta";
import styles from "./Compare.module.css";

/**
 * The four headline numbers, each with the typical advisor's beside it and a plain-words
 * explanation. With a what-if on screen each also shows its move against the base plan.
 */
export function StatGrid({ plan, base }: { plan: PlanResponse; base?: PlanResponse }) {
  const s = plan.stats;
  const taxGap = s.ria_lifetime_taxes - s.lifetime_taxes;

  return (
    <div className={styles.stats}>
      <StatCard
        label="Typical outcome at 70"
        value={money(s.typical_outcome.median)}
        note={
          <>
            <span className={styles.strong}>Typical advisor: {money(s.ria_typical_outcome.median)}</span>
            <br />
            Half of simulated futures end above this, after tax, in 2026 dollars.
            {base && (
              <>
                <br />
                <Delta
                  change={s.typical_outcome.median - base.stats.typical_outcome.median}
                  goodWhen="up"
                  format={money}
                />
              </>
            )}
          </>
        }
      />
      <StatCard
        label="Bad case (10th percentile)"
        value={money(s.typical_outcome.p10)}
        note={
          <>
            <span className={styles.strong}>Typical advisor: {money(s.ria_typical_outcome.p10)}</span>
            <br />
            1 in 10 futures end below this.
            {base && (
              <>
                <br />
                <Delta change={s.typical_outcome.p10 - base.stats.typical_outcome.p10} goodWhen="up" format={money} />
              </>
            )}
          </>
        }
      />
      <StatCard
        tone="accent"
        label="Typical advantage per year"
        value={signedMoney(s.advantage_per_year)}
        note={
          <>
            <span className={styles.strong}>
              {signedMoney(s.advantage_total)} in total over {s.years} years
            </span>
            <br />
            Typical outcome at 70 compared with a typical advisor.
            {base && (
              <>
                <br />
                <Delta change={s.advantage_per_year - base.stats.advantage_per_year} goodWhen="up" format={money} />
              </>
            )}
          </>
        }
      />
      <StatCard
        label="Lifetime taxes including tax still owed on pre-tax accounts"
        value={money(s.lifetime_taxes)}
        note={
          <>
            <span className={styles.strong}>Typical advisor: {money(s.ria_lifetime_taxes)}</span>
            <br />
            {Math.abs(taxGap) < 0.5
              ? "The same as a typical advisor's."
              : `${money(Math.abs(taxGap))} ${taxGap > 0 ? "lower" : "higher"} than a typical advisor's.`}
            {base && (
              <>
                <br />
                <Delta change={s.lifetime_taxes - base.stats.lifetime_taxes} goodWhen="down" format={money} />
              </>
            )}
          </>
        }
      />
    </div>
  );
}
