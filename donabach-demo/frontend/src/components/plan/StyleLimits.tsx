import { Icon } from "@/components/ui";
import { percent, percentTrim, years } from "@/lib/format";
import type { PlanResponse } from "@/lib/types";
import { Metric } from "./Metric";
import styles from "./StyleFigures.module.css";

const EPSILON = 1e-9;

/**
 * The two limits the liability-matched plan was chosen under, from the API's `liability`: stocks sold in a falling year to
 * pay for goals or spending in at most a set share of futures, and running out of money no more likely than with the good RIA.
 * Each is shown as measured on the fresh futures (as every other figure is) and on the futures the plan was chosen on, which
 * is what `feasible` is judged on: a plan can be inside a limit on fresh futures and still not have met it where it was chosen.
 */
export function StyleLimits({ plan, id }: { plan: PlanResponse; id: string }) {
  const limits = plan.liability;
  if (!limits) return null;
  const forcedOk = limits.forced_sale_chance <= limits.forced_sale_limit + EPSILON;
  const forcedChosenOk = limits.chosen_on_forced_sale_chance <= limits.forced_sale_limit + EPSILON;
  const ruinOk = limits.ruin_chance <= limits.advisor_ruin_chance + EPSILON;
  const ruinChosenOk = limits.chosen_on_ruin_chance <= limits.chosen_on_advisor_ruin_chance + EPSILON;
  const share = limits.stock_share_by_age;
  const shares = share.map(([, value]) => value);
  const first = share[0];
  const last = share[share.length - 1];
  return (
    <section className={styles.section} aria-labelledby={id}>
      <h4 id={id} className={styles.title}>
        The two limits it was chosen under
      </h4>
      <p className={styles.verdict} data-tone={limits.feasible ? "good" : "warn"}>
        <Icon name={limits.feasible ? "check" : "alert"} size={18} strokeWidth={limits.feasible ? 2.8 : undefined} />
        <span>
          {limits.feasible
            ? "Both limits are met on the futures it was chosen on."
            : "No strategy met both limits on the futures it was chosen on, so this is the one that came closest."}
        </span>
      </p>
      <dl className={styles.metrics}>
        <Metric
          label="Stocks sold in a falling year to pay for goals or spending"
          figure={percentTrim(limits.forced_sale_chance)}
          detail={
            <>
              <span className={styles.line}>
                On fresh futures: {forcedOk ? "within" : "above"} the {percentTrim(limits.forced_sale_limit)} limit
              </span>
              <span className={styles.line}>
                On the futures it was chosen on: {percentTrim(limits.chosen_on_forced_sale_chance)},{" "}
                {forcedChosenOk ? "within" : "above"} the limit
              </span>
            </>
          }
        />
        <Metric
          label="Running out of money"
          figure={percentTrim(limits.ruin_chance)}
          detail={
            <>
              <span className={styles.line}>
                On fresh futures: {ruinOk ? "no higher" : "higher"} than a good RIA&apos;s{" "}
                {percentTrim(limits.advisor_ruin_chance)}
              </span>
              <span className={styles.line}>
                On the futures it was chosen on: {percentTrim(limits.chosen_on_ruin_chance)} against{" "}
                {percentTrim(limits.chosen_on_advisor_ruin_chance)}, {ruinChosenOk ? "no higher" : "higher"}
              </span>
            </>
          }
        />
        <Metric label="Spending reserve" figure={years(limits.reserve_years)} />
        {first && last && (
          <Metric
            label="Stocks as a share of the portfolio"
            figure={`${percent(Math.min(...shares))} to ${percent(Math.max(...shares))}`}
            detail={`${percent(first[1])} at age ${first[0]}, ${percent(last[1])} at age ${last[0]}`}
          />
        )}
      </dl>
    </section>
  );
}
