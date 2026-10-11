import type { ReactNode } from "react";
import { Swatch } from "@/components/charts/ChartLegend";
import {
  SERIES_ADAPTIVE,
  SERIES_DONABACH,
  SERIES_RIA,
  SERIES_TYPICAL,
  type LineStyle,
} from "@/components/charts/chartTheme";
import { DataTable, Panel, PanelTitle, type DataColumn } from "@/components/ui";
import { rangeVerdict } from "@/lib/adaptive";
import { count, money, percentTrim, rateDigits, signedMoney, signedPercent } from "@/lib/format";
import type { AdaptiveSection, AdvantageView, PlanResponse, StrategyKey, StrategyOutcome } from "@/lib/types";
import { MEASURES } from "./AdvantagePanel";
import { scoreDefinition } from "./measure";
import { RangeBar, scaleFor } from "./RangeBar";
import styles from "./FourWay.module.css";

/** How each strategy is drawn everywhere on this screen: its colour and its line style (colour never stands alone). */
const LOOK: Record<StrategyKey, { color: string; lineStyle: LineStyle }> = {
  typical_advisor: { color: SERIES_TYPICAL, lineStyle: "dashed" },
  good_ria: { color: SERIES_RIA, lineStyle: "solid" },
  best_fixed: { color: SERIES_DONABACH, lineStyle: "solid" },
  adaptive: { color: SERIES_ADAPTIVE, lineStyle: "dotted" },
};

/** Who an advantage is over, in words that follow "over", and where the API puts it. */
const OVER = [
  { key: "typical_advisor", words: "a typical advisor", pick: (s: StrategyOutcome) => s.advantage_vs_typical },
  { key: "good_ria", words: "a good RIA", pick: (s: StrategyOutcome) => s.advantage_vs_ria },
] as const;

/** The advantage a strategy has over an advisor, or nothing when the strategy is that advisor. */
const advantageOf = (strategy: StrategyOutcome, over: (typeof OVER)[number]): AdvantageView | null =>
  strategy.key === over.key ? null : (over.pick(strategy) ?? null);

/** One row of the comparison: a figure for each strategy. */
interface MatrixRow {
  id: string;
  label: ReactNode;
  /** The row's name for screen readers and the table's caption. */
  name: string;
  cell: (strategy: StrategyOutcome) => ReactNode;
}

/**
 * The four strategies measured on the same fresh futures, side by side, as a table: a column for each strategy and
 * a row for each figure: what it leaves the household with (typical outcome, certainty equivalent, bad case,
 * lifetime taxes, chance of running out of money) and how far ahead of each advisor it ends, two ways, with the 90%
 * range each advantage falls in. Where a range includes zero the cell says the figure is not distinguishable from
 * no effect.
 */
export function FourWayPanel({ plan, section }: { plan: PlanResponse; section: AdaptiveSection }) {
  const { horizon_age: horizon } = plan.settings;
  const strategies = section.strategies;
  const adaptive = strategies.find((s) => s.key === "adaptive");

  const outcomes: MatrixRow[] = [
    // A no-break space keeps "at 80" together when a label wraps.
    { id: "median", name: `Typical outcome at ${horizon}`, label: `Typical outcome at ${horizon}`, cell: (s) => money(s.outcome.median) },
    { id: "score", name: `Certainty equivalent at ${horizon}`, label: `Certainty equivalent at ${horizon}`, cell: (s) => money(s.outcome.score) },
    { id: "p10", name: "Bad case (10th percentile)", label: "Bad case (10th percentile)", cell: (s) => money(s.outcome.p10) },
    { id: "taxes", name: "Lifetime taxes", label: "Lifetime taxes", cell: (s) => money(s.lifetime_taxes) },
    { id: "shortfall", name: "Chance of running out of money", label: "Chance of running out of money", cell: (s) => percentTrim(s.shortfall_chance) },
  ];

  const advantages: MatrixRow[] = MEASURES.flatMap((measure) =>
    OVER.map((over): MatrixRow => {
      const name = `${measure.label} over ${over.words}`;
      // One axis for the four strategies, so the bars in a row can be compared by eye.
      const scale = scaleFor(
        strategies.flatMap((s) => {
          const a = advantageOf(s, over);
          return a ? [measure.pick(a)] : [];
        }),
      );
      return {
        id: `${measure.id}-${over.key}`,
        name,
        label: name,
        cell: (strategy) => {
          const a = advantageOf(strategy, over);
          if (!a) {
            return (
              <span className={styles.notApplicable}>
                {strategy.key === over.key ? `Not applicable: this is ${over.words}` : "Not available"}
              </span>
            );
          }
          const now = measure.pick(a);
          const digits = rateDigits(now.value, now.low, now.high);
          return (
            <div className={styles.advantage} role="group" aria-label={`${strategy.label}: ${name}`}>
              <div>
                <span className={styles.advFigure}>{signedPercent(now.value, digits)}</span>
                <span className={styles.unit}> a{"\u00a0"}year</span>
                {rangeVerdict(now.low, now.high, digits) === "spans" && (
                  <span className={styles.flag}>
                    {" "}
                    <span aria-hidden="true">†</span>
                    <span className="sr-only">(the 90% range includes zero)</span>
                  </span>
                )}
              </div>
              <RangeBar value={now.value} low={now.low} high={now.high} scale={scale} compact />
              <div className={styles.advRange}>
                90% range: {signedPercent(now.low, digits)} to {signedPercent(now.high, digits)}
              </div>
              <div className={styles.advDollars}>
                <strong>{signedMoney(now.dollars)}</strong> at {horizon}
              </div>
            </div>
          );
        },
      };
    }),
  );

  // Is any advantage's 90% range one that includes zero? (Judged on the figures as printed, like the cell's own †.)
  const anySpansZero = strategies.some((strategy) =>
    OVER.some((over) => {
      const a = advantageOf(strategy, over);
      return (
        !!a &&
        MEASURES.some((measure) => {
          const now = measure.pick(a);
          return rangeVerdict(now.low, now.high, rateDigits(now.value, now.low, now.high)) === "spans";
        })
      );
    }),
  );

  const rows = [...outcomes, ...advantages];
  const columns: DataColumn<MatrixRow>[] = [
    { key: "measure", header: "Measure", rowHeader: true, width: "18%", cell: (row) => row.label },
    ...strategies.map(
      (strategy): DataColumn<MatrixRow> => ({
        key: strategy.key,
        header: (
          <span className={styles.colHead}>
            <Swatch color={LOOK[strategy.key].color} kind="line" lineStyle={LOOK[strategy.key].lineStyle} />
            <span>{strategy.label}</span>
          </span>
        ),
        align: "end",
        cell: (row) => <span className={styles.cell}>{row.cell(strategy)}</span>,
      }),
    ),
  ];

  return (
    <Panel aria-labelledby="fourway-title">
      <PanelTitle id="fourway-title" aside={`${count(section.n_eval_paths)} fresh futures, after tax, in 2026 dollars`}>
        The four strategies side by side
      </PanelTitle>
      <p className={styles.intro}>
        {adaptive && (
          <>
            <strong>{adaptive.label}.</strong> {adaptive.definition}{" "}
          </>
        )}
        The best fixed strategy is the Donabach plan above. All four are measured on the same simulated futures, and each
        advantage comes with the 90% range it would fall in if those futures were resampled.
      </p>
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        caption={`The four strategies side by side: ${[...outcomes, ...advantages].map((row) => row.name).join(", ")}`}
        minWidth={640}
        dense
      />
      {/* One sentence either way, in one cell (see `stacked`): the table's height does not depend on whether a range reaches zero. */}
      <div className={`${styles.zeroNote} ${styles.stacked}`}>
        <p data-active={anySpansZero} aria-hidden={anySpansZero ? undefined : true}>
          <strong>†</strong> The 90% range includes zero, so that advantage is not distinguishable from no effect.
        </p>
        <p data-active={!anySpansZero} aria-hidden={anySpansZero ? true : undefined}>
          No advantage here has a 90% range that includes zero; a <strong>†</strong> would mark one that did.
        </p>
      </div>
      <dl className={styles.glossary} aria-label="What the figures mean">
        <div>
          <dt>Certainty equivalent at {horizon}</dt>
          <dd>{`Certainty-equivalent wealth: ${scoreDefinition(plan.settings)}.`}</dd>
        </div>
        <div>
          <dt>Chance of running out of money</dt>
          <dd>The share of futures in which spending or a goal could not be funded.</dd>
        </div>
        <div>
          <dt>Median and risk-adjusted advantage</dt>
          <dd>
            The two measures defined in &ldquo;Donabach&apos;s advantage&rdquo; above, here for every strategy. The dollars are
            the difference in typical (median) wealth at {horizon} in the median rows, and in certainty-equivalent wealth
            at {horizon} in the risk-adjusted rows.
          </dd>
        </div>
      </dl>
    </Panel>
  );
}
