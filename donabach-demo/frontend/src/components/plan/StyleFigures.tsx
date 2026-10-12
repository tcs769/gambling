import { MEASURES } from "@/components/compare/AdvantagePanel";
import { rangeVerdict } from "@/lib/adaptive";
import { money, percentTrim, signedMoney, signedPercent } from "@/lib/format";
import { baselineOf, type AdvantageView, type PlanResponse } from "@/lib/types";
import { Metric } from "./Metric";
import { StyleLimits } from "./StyleLimits";
import styles from "./StyleFigures.module.css";

/** The plan's advantage over the good RIA under each valuation of wealth at the horizon, with the API's labels. */
function valuations(plan: PlanResponse): { id: string; label: string; advantage: AdvantageView }[] {
  return [
    { id: "liquidated", label: plan.settings.liquidated_label, advantage: plan.stats.advantage },
    { id: "heirs", label: plan.settings.heirs_label, advantage: plan.stats.advantage_heirs },
  ];
}

/** Does any advantage a plan shows have a 90% range that includes zero (judged on the figures as printed, like the dagger)? */
export function hasZeroRange(plan: PlanResponse): boolean {
  return valuations(plan).some(({ advantage }) =>
    MEASURES.some((measure) => {
      const { low, high } = measure.pick(advantage);
      return rangeVerdict(low, high) === "spans";
    }),
  );
}

/**
 * What a plan comes to, in the sections the side-by-side view and a single style's view both show: wealth at the horizon
 * (liquidated), the advantage over the good RIA in both measures and under both valuations, and the taxes and risks beside the
 * good RIA's, then, for the liability-matched plan, the two limits it was chosen under. Every figure is the API's, written as
 * the Comparison screen writes it. The parent lays the sections out (stacked in a column, or in a grid).
 */
export function StyleFigures({ plan, id }: { plan: PlanResponse; id: string }) {
  const { horizon_age: horizon, liquidated_label: liquidated } = plan.settings;
  const { stats } = plan;
  const ria = baselineOf(plan, "good_ria");
  return (
    <>
      <section className={styles.section} aria-labelledby={`${id}-wealth`}>
        <h4 id={`${id}-wealth`} className={styles.title}>
          {liquidated}
        </h4>
        <dl className={styles.metrics}>
          <Metric label={`Typical outcome at ${horizon}`} figure={money(stats.typical_outcome.median)} />
          <Metric label="Bad case (10th percentile)" figure={money(stats.typical_outcome.p10)} />
        </dl>
      </section>

      <section className={styles.section} aria-labelledby={`${id}-advantage`}>
        <h4 id={`${id}-advantage`} className={styles.title}>
          Advantage over a good RIA
        </h4>
        {valuations(plan).map(({ id: key, label, advantage }) => (
          <div key={key} className={styles.valuation} role="group" aria-label={`Advantage over a good RIA, ${label}`}>
            <p className={styles.sub}>{label}</p>
            <dl className={styles.metrics}>
              {MEASURES.map((measure) => {
                const now = measure.pick(advantage);
                const spans = rangeVerdict(now.low, now.high) === "spans";
                return (
                  <Metric
                    key={measure.id}
                    label={measure.label}
                    figure={
                      <>
                        {signedPercent(now.value)}
                        <span className={styles.unit}> a year</span>
                        {spans && (
                          <>
                            <span aria-hidden="true"> †</span>
                            <span className="sr-only"> (the 90% range includes zero)</span>
                          </>
                        )}
                      </>
                    }
                    detail={`${signedMoney(now.dollars)} at ${horizon} · 90% range ${signedPercent(now.low)} to ${signedPercent(now.high)}`}
                  />
                );
              })}
            </dl>
          </div>
        ))}
      </section>

      <section className={styles.section} aria-labelledby={`${id}-risks`}>
        <h4 id={`${id}-risks`} className={styles.title}>
          Taxes and risks
        </h4>
        <dl className={styles.metrics}>
          <Metric
            label="Lifetime taxes"
            figure={money(stats.lifetime_taxes)}
            detail={`A good RIA: ${money(stats.ria_lifetime_taxes)}`}
          />
          <Metric
            label="Chance of running out of money"
            figure={percentTrim(stats.shortfall_chance)}
            detail={ria && `A good RIA: ${percentTrim(ria.shortfall_chance)}`}
          />
          <Metric
            label="Chance of selling stocks in a falling year to pay for goals or spending"
            figure={percentTrim(stats.forced_sale_chance)}
            detail={`A good RIA: ${percentTrim(stats.ria_forced_sale_chance)}`}
          />
        </dl>
      </section>

      {plan.liability && <StyleLimits plan={plan} id={`${id}-limits`} />}
    </>
  );
}
