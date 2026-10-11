import { Swatch } from "@/components/charts/ChartLegend";
import { SERIES_DONABACH, SERIES_RIA, SERIES_TYPICAL } from "@/components/charts/chartTheme";
import { Icon, Panel, PanelTitle, Pill } from "@/components/ui";
import { count, money, percentagePoints, percentTrim } from "@/lib/format";
import type { BaselineView, PlanResponse } from "@/lib/types";
import { Delta } from "./Delta";
import styles from "./Baselines.module.css";

/** What one column of cards shows: the same four figures for the plan and for each advisor. */
interface Figures {
  median: number;
  p10: number;
  taxes: number;
  shortfall: number;
}

interface Card {
  key: string;
  name: string;
  /** One full sentence on what this is: the API's definition for an advisor, the strategy for the plan. */
  definition: string;
  /** Who chose it, for the plan (the API's planner label). */
  chosenBy?: string;
  color: string;
  dashed: boolean;
  tone: "accent" | "default";
  figures: Figures;
  /** The base plan's figures, when a what-if is on screen (only the plan's own column moves with a what-if). */
  before?: Figures;
}

const SERIES_BY_KEY: Record<BaselineView["key"], string> = {
  good_ria: SERIES_RIA,
  typical_advisor: SERIES_TYPICAL,
};

const planFigures = (plan: PlanResponse): Figures => ({
  median: plan.stats.typical_outcome.median,
  p10: plan.stats.typical_outcome.p10,
  taxes: plan.stats.lifetime_taxes,
  shortfall: plan.stats.shortfall_chance,
});

const advisorFigures = (b: BaselineView): Figures => ({
  median: b.outcome.median,
  p10: b.outcome.p10,
  taxes: b.lifetime_taxes,
  shortfall: b.shortfall_chance,
});

interface Row {
  key: keyof Figures;
  label: (horizon: number) => string;
  format: (value: number) => string;
  /** Which way is good news, for the what-if move. */
  goodWhen: "up" | "down";
  /** A move smaller than this is no move at all. */
  epsilon: number;
  /** How a move is written. */
  move: (absoluteChange: number) => string;
}

const ROWS: Row[] = [
  { key: "median", label: (h) => `Typical outcome at ${h}`, format: money, goodWhen: "up", epsilon: 0.5, move: money },
  { key: "p10", label: () => "Bad case (10th percentile)", format: money, goodWhen: "up", epsilon: 0.5, move: money },
  { key: "taxes", label: () => "Lifetime taxes", format: money, goodWhen: "down", epsilon: 0.5, move: money },
  {
    key: "shortfall",
    label: () => "Chance of a shortfall",
    format: (v) => percentTrim(v),
    goodWhen: "down",
    // Measured on a few hundred futures, so it moves in steps of a fraction of a point.
    epsilon: 0.0005,
    move: (change) => percentagePoints(change, 1),
  },
];

/**
 * Who the plan is compared with, and what each leaves the household with: a card for the plan and
 * one for each advisor, with the advisor's definition in full and the same four figures down each
 * card (rows line up across the cards). One line under them says how the figures were measured; the
 * words for each figure follow, once.
 */
export function BaselinesPanel({ plan, base }: { plan: PlanResponse; base?: PlanResponse }) {
  const { horizon_age: horizon, n_eval_paths: evalPaths } = plan.settings;
  const cards: Card[] = [
    {
      key: "donabach",
      name: "Donabach plan",
      definition: `The recommended strategy: ${plan.strategy.label}.`,
      chosenBy: plan.planner_label,
      color: SERIES_DONABACH,
      dashed: false,
      tone: "accent",
      figures: planFigures(plan),
      before: base && planFigures(base),
    },
    ...plan.baselines.map(
      (b): Card => ({
        key: b.key,
        name: b.label,
        definition: b.definition,
        color: SERIES_BY_KEY[b.key] ?? SERIES_RIA,
        dashed: b.key === "typical_advisor",
        tone: "default",
        figures: advisorFigures(b),
      }),
    ),
  ];

  return (
    <Panel aria-labelledby="baselines-title">
      <PanelTitle id="baselines-title" aside="After tax, in 2026 dollars">
        Donabach against two advisors
      </PanelTitle>
      <div className={styles.wrap}>
        <div className={styles.cards}>
          {cards.map((card) => (
            <article key={card.key} className={styles.card} data-tone={card.tone} aria-labelledby={`baseline-${card.key}`}>
              <header className={styles.head}>
                <Swatch color={card.color} kind="line" dashed={card.dashed} />
                <h3 id={`baseline-${card.key}`}>{card.name}</h3>
              </header>
              <div className={styles.definition}>
                <p>{card.definition}</p>
                {card.chosenBy && (
                  <Pill tone="gold" icon={<Icon name="info" size={14} />}>
                    {card.chosenBy}
                  </Pill>
                )}
              </div>
              <dl className={styles.metrics}>
                {ROWS.map((row) => (
                  <div key={row.key} className={styles.metric}>
                    <dt>{row.label(horizon)}</dt>
                    <dd className={styles.figure}>{row.format(card.figures[row.key])}</dd>
                    {card.before && (
                      <dd className={styles.move}>
                        <Delta
                          change={card.figures[row.key] - card.before[row.key]}
                          goodWhen={row.goodWhen}
                          epsilon={row.epsilon}
                          format={row.move}
                        />
                      </dd>
                    )}
                  </div>
                ))}
              </dl>
            </article>
          ))}
        </div>
      </div>
      <p className={styles.note}>
        All figures are measured on {count(evalPaths)} fresh futures the search never saw.{" "}
        <a href="#how-we-measure">How we measure</a>
      </p>
      <dl className={styles.glossary} aria-label="What the figures mean">
        <div>
          <dt>Typical outcome at {horizon}</dt>
          <dd>Half of the simulated futures end above this, after tax.</dd>
        </div>
        <div>
          <dt>Bad case</dt>
          <dd>1 in 10 futures end below this (the 10th percentile).</dd>
        </div>
        <div>
          <dt>Lifetime taxes</dt>
          <dd>The median of income tax paid plus tax still owed on pre-tax accounts.</dd>
        </div>
        <div>
          <dt>Chance of a shortfall</dt>
          <dd>The share of futures in which spending or a goal could not be funded.</dd>
        </div>
      </dl>
    </Panel>
  );
}
