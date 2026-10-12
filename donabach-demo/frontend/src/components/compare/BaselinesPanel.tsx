import { Swatch } from "@/components/charts/ChartLegend";
import { SERIES_DONABACH, SERIES_RIA, SERIES_TYPICAL, type LineStyle } from "@/components/charts/chartTheme";
import { Icon, Panel, PanelTitle, Pill } from "@/components/ui";
import { count, money, percentagePoints, percentTrim } from "@/lib/format";
import type { BaselineView, PlanResponse } from "@/lib/types";
import { Delta } from "./Delta";
import styles from "./Baselines.module.css";

/**
 * What one column of cards shows: the same figures for the plan and for each advisor. Wealth at the horizon is given for both
 * of the API's valuations (`median` and `p10` liquidated, `medianHeirs` and `p10Heirs` passed to heirs); taxes and the chance
 * of a shortfall have one figure each.
 */
interface Figures {
  median: number;
  p10: number;
  medianHeirs: number;
  p10Heirs: number;
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
  lineStyle: LineStyle;
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
  medianHeirs: plan.stats.typical_outcome_heirs.median,
  p10Heirs: plan.stats.typical_outcome_heirs.p10,
  taxes: plan.stats.lifetime_taxes,
  shortfall: plan.stats.shortfall_chance,
});

const advisorFigures = (b: BaselineView): Figures => ({
  median: b.outcome.median,
  p10: b.outcome.p10,
  medianHeirs: b.outcome_heirs.median,
  p10Heirs: b.outcome_heirs.p10,
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

const typical = (key: "median" | "medianHeirs"): Row => ({
  key,
  label: (h) => `Typical outcome at ${h}`,
  format: money,
  goodWhen: "up",
  epsilon: 0.5,
  move: money,
});
const badCase = (key: "p10" | "p10Heirs"): Row => ({
  key,
  label: () => "Bad case (10th percentile)",
  format: money,
  goodWhen: "up",
  epsilon: 0.5,
  move: money,
});

/** The figures that have one value whichever way wealth at the horizon is valued. */
const SHARED_ROWS: Row[] = [
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
  const {
    horizon_age: horizon,
    n_eval_paths: evalPaths,
    liquidated_label: liquidated,
    heirs_label: heirs,
  } = plan.settings;
  // Wealth at the horizon under each valuation, with the API's own label over it.
  const valuations: { id: string; label: string; rows: Row[] }[] = [
    { id: "liquidated", label: liquidated, rows: [typical("median"), badCase("p10")] },
    { id: "heirs", label: heirs, rows: [typical("medianHeirs"), badCase("p10Heirs")] },
  ];
  const figureRow = (card: Card, row: Row) => (
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
  );
  const cards: Card[] = [
    {
      key: "donabach",
      name: "Donabach plan",
      definition: `The recommended strategy: ${plan.strategy.label}.`,
      chosenBy: plan.planner_label,
      color: SERIES_DONABACH,
      lineStyle: "solid",
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
        lineStyle: b.key === "typical_advisor" ? "dashed" : "solid",
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
            <article
              key={card.key}
              className={styles.card}
              data-tone={card.tone}
              aria-labelledby={`baseline-${card.key}`}
            >
              <header className={styles.head}>
                <Swatch color={card.color} kind="line" lineStyle={card.lineStyle} />
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
              {valuations.map((valuation) => (
                <section
                  key={valuation.id}
                  className={styles.valuation}
                  data-valuation={valuation.id}
                  aria-labelledby={`baseline-${card.key}-${valuation.id}`}
                >
                  <h4 id={`baseline-${card.key}-${valuation.id}`} className={styles.valuationTitle}>
                    {valuation.label}
                  </h4>
                  <dl className={styles.metrics}>{valuation.rows.map((row) => figureRow(card, row))}</dl>
                </section>
              ))}
              <section
                className={styles.valuation}
                data-valuation="shared"
                aria-labelledby={`baseline-${card.key}-shared`}
              >
                <h4 id={`baseline-${card.key}-shared`} className={styles.valuationTitle}>
                  Taxes and risks
                </h4>
                <dl className={styles.metrics}>{SHARED_ROWS.map((row) => figureRow(card, row))}</dl>
              </section>
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
