import { Disclosure, Panel } from "@/components/ui";
import { percent } from "@/lib/format";
import type { PlanSettings } from "@/lib/types";
import styles from "./Compare.module.css";

/**
 * The two ways of valuing wealth at the horizon, once for the whole screen. Every figure here that is wealth at the horizon is
 * shown as "Liquidated at 80" and as "Passed to heirs at 80" (the API's own labels); this says what each assumes. What the heirs
 * valuation assumes, and why its rate is what it is, is the API's own note, word for word, with the rate beside it.
 */
export function ValuationNote({ settings }: { settings: PlanSettings }) {
  const {
    liquidated_label: liquidated,
    heirs_label: heirs,
    heirs_rate: rate,
    heirs_note: note,
    horizon_age: horizon,
  } = settings;
  return (
    <Panel tone="plain" className={styles.valuationNote} aria-label="How wealth at the horizon is valued">
      <p className={styles.valuationIntro}>
        Wealth at {horizon} is valued two ways on this screen: <strong>{liquidated}</strong> and{" "}
        <strong>{heirs}</strong>. Each is shown wherever wealth at {horizon} is a result.
      </p>
      <Disclosure title="How these are valued">
        <dl className={styles.valued}>
          <div>
            <dt>{liquidated}</dt>
            <dd>
              Everything is sold at {horizon} and the tax on the sale is paid, so the figure is what the household is
              left with. The planner searches and scores plans on this valuation.
            </dd>
          </div>
          <div>
            <dt>{heirs}</dt>
            <dd>
              Tax rate on the 401(k) and IRA: <strong>{percent(rate)}</strong>.{note ? ` ${note}` : ""}
            </dd>
          </div>
        </dl>
      </Disclosure>
    </Panel>
  );
}
