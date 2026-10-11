import { Panel, PanelTitle } from "@/components/ui";
import { count, percentagePoints, signedMoney, signedPercent } from "@/lib/format";
import type { AdvantageView, BaselineView, PlanResponse } from "@/lib/types";
import { Delta } from "./Delta";
import { RangeBar, scaleFor } from "./RangeBar";
import styles from "./Advantage.module.css";

/** Who the plan is compared with, in words that follow "against". */
const AGAINST: Record<BaselineView["key"], string> = {
  good_ria: "a good RIA",
  typical_advisor: "a typical advisor",
};
const against = (baseline: BaselineView): string => AGAINST[baseline.key] ?? baseline.label;

interface Measure {
  id: "median" | "risk_adjusted";
  label: string;
  definition: (horizon: number, riskAversion: number) => string;
  /** The plan's number, its 90% range and its dollar equivalent for this measure. */
  pick: (advantage: AdvantageView) => { value: number; low: number; high: number; dollars: number };
  /** What the dollar figure is a difference of. */
  dollarsOf: (horizon: number) => string;
}

/** The two ways the advantage is measured. Each is defined once, in words, beside its row. */
const MEASURES: Measure[] = [
  {
    id: "median",
    label: "Median advantage",
    definition: (horizon) =>
      `Difference in the typical (median) after-tax wealth at ${horizon}, as a yearly growth-rate difference.`,
    pick: (a) => ({ value: a.median, low: a.median_low, high: a.median_high, dollars: a.median_dollars }),
    dollarsOf: (horizon) => `of typical (median) wealth at ${horizon}`,
  },
  {
    id: "risk_adjusted",
    label: "Risk-adjusted advantage",
    definition: (_horizon, riskAversion) =>
      `The same, but using certainty-equivalent wealth: the guaranteed amount that would feel as good as the risky range of outcomes to a household with risk aversion ${riskAversion}. It is the planner's own objective, so it rewards a smaller bad case, not just a higher middle.`,
    pick: (a) => ({
      value: a.risk_adjusted,
      low: a.risk_adjusted_low,
      high: a.risk_adjusted_high,
      dollars: a.risk_adjusted_dollars,
    }),
    dollarsOf: (horizon) => `of certainty-equivalent wealth at ${horizon}`,
  },
];

/** Two decimals of a percent is the figure's precision; a smaller move than half a step is no move. */
const PERCENT_EPSILON = 0.00005;

/**
 * The plan's advantage, measured two ways against each advisor: a 2 x 2 grid with the measures down
 * the side (each defined once, in words) and the advisors across. Every cell has its figure as a
 * signed yearly rate, the 90% range it falls in when the futures are resampled, and the dollars.
 * With a what-if on screen each also shows its move against the base plan.
 */
export function AdvantagePanel({ plan, base }: { plan: PlanResponse; base?: PlanResponse }) {
  const { horizon_age: horizon, risk_aversion: riskAversion, n_eval_paths: evalPaths } = plan.settings;
  const advisors = plan.baselines;
  if (advisors.length === 0) return null;

  return (
    <Panel aria-labelledby="advantage-title">
      <PanelTitle id="advantage-title" aside={`Measured on ${count(evalPaths)} fresh futures`}>
        Donabach&apos;s advantage
      </PanelTitle>
      <p className={styles.intro}>
        How far ahead the plan ends against each advisor, measured two ways. Positive means the plan ends ahead; each
        figure comes with the 90% range it would fall in if the simulated futures were resampled.
      </p>
      <div className={styles.measures}>
        {MEASURES.map((measure) => {
          const scale = scaleFor(advisors.map((advisor) => measure.pick(advisor.advantage)));
          return (
            <section key={measure.id} className={styles.measure} aria-labelledby={`measure-${measure.id}`}>
              <div className={styles.what}>
                <h3 id={`measure-${measure.id}`}>{measure.label}</h3>
                <p>{measure.definition(horizon, riskAversion)}</p>
              </div>
              <div className={styles.cells}>
                {advisors.map((advisor) => {
                  const now = measure.pick(advisor.advantage);
                  const before = base?.baselines.find((b) => b.key === advisor.key);
                  return (
                    <div
                      key={advisor.key}
                      className={styles.cell}
                      role="group"
                      aria-label={`${measure.label} against ${against(advisor)}`}
                    >
                      <div className={styles.against}>Against {against(advisor)}</div>
                      <div className={styles.value}>
                        <span className={styles.figure}>{signedPercent(now.value)}</span>
                        <span className={styles.unit}> a year</span>
                      </div>
                      <RangeBar value={now.value} low={now.low} high={now.high} scale={scale} />
                      <p className={styles.range}>
                        90% range: {signedPercent(now.low)} to {signedPercent(now.high)} when the futures are resampled
                      </p>
                      <p className={styles.dollars}>
                        <strong>{signedMoney(now.dollars)}</strong> {measure.dollarsOf(horizon)}
                      </p>
                      {before && (
                        <Delta
                          change={now.value - measure.pick(before.advantage).value}
                          goodWhen="up"
                          epsilon={PERCENT_EPSILON}
                          format={percentagePoints}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </Panel>
  );
}
