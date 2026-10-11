import {
  DataTable,
  FactorList,
  Icon,
  ModelNotConnected,
  Panel,
  PanelTitle,
  Pill,
  type DataColumn,
} from "@/components/ui";
import { count, money, percent } from "@/lib/format";
import {
  CHOICE_LABELS,
  optionLabel,
  type PlanResponse,
  type RankedRow,
  type RecommenderPanel as RecommenderData,
  type StrategyView,
} from "@/lib/types";
import { RankedStrategyCell } from "./RankedStrategy";
import styles from "./Recommender.module.css";

function StrategyBox({ heading, strategy, horizon }: { heading: string; strategy: StrategyView; horizon: number }) {
  return (
    <div className={styles.strategyBox}>
      <div className={styles.boxHeading}>{heading}</div>
      <div className={styles.boxLabel}>{strategy.label}</div>
      <dl className={styles.boxStats}>
        <div>
          <dt>Score</dt>
          <dd>{money(strategy.outcome.score)}</dd>
        </div>
        <div>
          <dt>Typical outcome at {horizon}</dt>
          <dd>{money(strategy.outcome.median)}</dd>
        </div>
        <div>
          <dt>Bad case</dt>
          <dd>{money(strategy.outcome.p10)}</dd>
        </div>
      </dl>
    </div>
  );
}

const CANDIDATE_COLUMNS: DataColumn<RankedRow>[] = [
  { key: "rank", header: "Rank", rowHeader: true, width: "9%", cell: (row) => row.rank },
  { key: "strategy", header: "Strategy", cell: (row) => <RankedStrategyCell row={row} /> },
  { key: "median", header: "Typical outcome", align: "end", width: "17%", cell: (row) => money(row.median) },
  { key: "score", header: "Score", align: "end", width: "14%", cell: (row) => money(row.score) },
];

/** What the connected model said, next to what the engine verified. Every number comes from the model or the engine. */
function Connected({ panel, plan }: { panel: RecommenderData; plan: PlanResponse }) {
  const { horizon_age: horizon, n_paths: searchPaths, n_eval_paths: evalPaths } = plan.settings;
  const recommendation = panel.recommendation;
  if (!recommendation) return null;
  return (
    <div className={styles.recommender}>
      <div className={styles.columns}>
        <section aria-labelledby="rec-confidence">
          <h3 id="rec-confidence">How sure the model is, choice by choice</h3>
          <ul className={styles.confidence}>
            {recommendation.choices.map((choice) => {
              const others = (choice.distribution ?? [])
                .filter((entry) => entry.option !== choice.option)
                .sort((a, b) => b.probability - a.probability)
                .map((entry) => `${optionLabel(choice.choice, entry.option)} (${percent(entry.probability)})`);
              return (
                <li key={choice.choice}>
                  <span className={styles.choiceName}>{CHOICE_LABELS[choice.choice] ?? choice.choice}</span>
                  <span className={styles.choiceOption}>{optionLabel(choice.choice, choice.option)}</span>
                  <span className={styles.bar} role="img" aria-label={`${percent(choice.probability)} confident`}>
                    <span className={styles.fill} style={{ width: `${choice.probability * 100}%` }} />
                  </span>
                  <span className={styles.pct}>{percent(choice.probability)}</span>
                  {others.length > 0 && <span className={styles.others}>Other options: {others.join(", ")}</span>}
                </li>
              );
            })}
          </ul>
        </section>
        <section aria-labelledby="rec-factors">
          <h3 id="rec-factors">What the model looked at</h3>
          {recommendation.top_factors && recommendation.top_factors.length > 0 ? (
            <FactorList
              factors={recommendation.top_factors}
              upText="Makes this pick likelier"
              downText="Makes this pick less likely"
              label="Top factors behind the model's recommendation"
            />
          ) : (
            <p className={styles.quiet}>The model did not report any factors.</p>
          )}
        </section>
      </div>

      {panel.model_strategy && panel.verified_strategy && (
        <section aria-labelledby="rec-verify" className={styles.verify}>
          <div className={styles.verifyHead}>
            <h3 id="rec-verify">Model recommended, verified by the engine</h3>
            {panel.agrees ? (
              <Pill tone="good" icon={<Icon name="check" size={14} strokeWidth={2.8} />}>
                The engine agrees with the model
              </Pill>
            ) : (
              <Pill tone="warn" icon={<Icon name="alert" size={14} />}>
                The engine chose a different strategy
              </Pill>
            )}
          </div>
          <div className={styles.versus}>
            <StrategyBox heading="Model recommended" strategy={panel.model_strategy} horizon={horizon} />
            <StrategyBox heading="Verified by the engine" strategy={panel.verified_strategy} horizon={horizon} />
          </div>
          <p className={styles.quiet}>
            Score is wealth at {horizon} adjusted for risk (certainty-equivalent wealth). The engine scored the model&apos;s
            recommendation and its nearest alternatives on the same {count(searchPaths)} search futures; the plan&apos;s own
            results on the Comparison screen are measured on {count(evalPaths)} fresh ones.
          </p>
        </section>
      )}

      {panel.candidates && panel.candidates.length > 0 && (
        <section aria-labelledby="rec-candidates">
          <h3 id="rec-candidates">Strategies the engine scored</h3>
          <DataTable
            columns={CANDIDATE_COLUMNS}
            rows={panel.candidates}
            rowKey={(row) => row.rank}
            caption="Strategies the engine scored: the model's recommendation and its nearest alternatives"
            rowTone={(row) => (row.is_chosen ? "highlight" : undefined)}
            maxHeight={340}
            dense
          />
        </section>
      )}
    </div>
  );
}

/**
 * The model recommendation panel. With a connected recommender: confidence bars per choice, its
 * top factors, and its strategy beside the one the engine verified. Without one, only the
 * "Model not connected" state: no bars and no numbers stand in for a prediction.
 */
export function RecommenderPanel({ plan }: { plan: PlanResponse }) {
  const panel = plan.recommender;
  const connected = panel.status.connected && !!panel.recommendation;
  return (
    <Panel>
      <PanelTitle
        aside={
          connected && (
            <Pill tone="good" icon={<Icon name="check" size={14} strokeWidth={2.8} />}>
              Model connected
            </Pill>
          )
        }
      >
        Model recommendation
      </PanelTitle>
      {connected ? (
        <Connected panel={panel} plan={plan} />
      ) : (
        <ModelNotConnected model="recommender" reason={panel.status.reason}>
          No confidence bars or factors are shown because no recommendation model is plugged in. The plan above comes from
          searching all {count(plan.settings.strategies_searched)} strategies on simulated futures instead.
        </ModelNotConnected>
      )}
    </Panel>
  );
}
