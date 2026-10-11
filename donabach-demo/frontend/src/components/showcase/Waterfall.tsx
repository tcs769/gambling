"use client";

import { useId, useMemo, useRef, useState, type FocusEvent, type PointerEvent } from "react";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { Button, DataTable, Icon, Spinner, type DataColumn } from "@/components/ui";
import { money, signedMoney } from "@/lib/format";
import type { ShowcaseAnalysis } from "@/lib/types";
import { Segmented } from "./Segmented";
import { StrategySwitch } from "./StrategySwitch";
import {
  axisCaption,
  axisFor,
  biggestStep,
  dollarsText,
  place,
  ratePercent,
  rateText,
  tickText,
  waterfallRows,
  type Axis,
  type Unit,
  type WaterfallRow,
} from "./waterfall";
import { strategies } from "./text";
import styles from "./Waterfall.module.css";

interface Hover {
  key: string;
  /** Where the tooltip points, in pixels from the top left of the chart. */
  x: number;
  y: number;
  width: number;
}

interface WaterfallProps {
  /** The analysis on screen (it may be a step behind the switches while a new one is being worked out). */
  analysis: ShowcaseAnalysis;
  /** The analysis with every strategy on: the axis is never narrower than its bars, so a bar shrinks against a scale that stays put. */
  full: ShowcaseAnalysis;
  /** The strategies that are switched on: what the switches show. */
  enabled: readonly string[];
  /** A new analysis is on its way: the bars and numbers are dimmed until it arrives. */
  computing: boolean;
  onToggle: (key: string, on: boolean) => void;
}

/**
 * The waterfall from the advisor's result to Donabach's. One bar per strategy, drawn floating: it starts where the
 * running total stood before the strategy and ends where it stood after, so the bars join up from the advisor (zero) to
 * the total (Donabach). A switch on every row turns the strategy off and the API measures the rest again; a strategy
 * that is off is an empty dashed bar of zero. What a bar's length means is a choice (dollars at the horizon or a yearly
 * rate), and both numbers are written on every row whichever is chosen. The same numbers are one toggle away as a table.
 */
export function Waterfall({ analysis, full, enabled, computing, onToggle }: WaterfallProps) {
  const [unit, setUnit] = useState<Unit>("dollars");
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [hover, setHover] = useState<Hover | null>(null);
  const chart = useRef<HTMLDivElement>(null);
  const ids = useId();

  const horizon = analysis.horizon_age;
  const rows = useMemo(() => waterfallRows(analysis), [analysis]);
  const axis = useMemo(() => axisFor(unit, [analysis, full]), [unit, analysis, full]);
  const strategyRows = rows.filter((row) => row.kind === "strategy");
  const allOpen = strategyRows.length > 0 && strategyRows.every((row) => open.has(row.key));

  const toggleOpen = (key: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  // Where a pointer is, or where the keyboard is, in the chart's own coordinates: the tooltip goes beside it.
  const track = (event: PointerEvent<HTMLElement>, key: string) => {
    const box = chart.current?.getBoundingClientRect();
    if (box) setHover({ key, x: event.clientX - box.left, y: event.clientY - box.top, width: box.width });
  };
  const focus = (event: FocusEvent<HTMLElement>, row: WaterfallRow) => {
    // A mouse click that focuses a switch has no need of the tooltip; the keyboard does.
    if (!(event.target as Element).matches(":focus-visible")) return;
    const box = chart.current?.getBoundingClientRect();
    const trackBox = event.currentTarget.querySelector<HTMLElement>("[data-track]")?.getBoundingClientRect();
    const rowBox = event.currentTarget.getBoundingClientRect();
    if (!box || !trackBox) return;
    const x = trackBox.left - box.left + (place(axis, row.to[unit]) / 100) * trackBox.width;
    setHover({ key: row.key, x, y: rowBox.top - box.top + 28, width: box.width });
  };
  const leave = (event: FocusEvent<HTMLElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setHover(null);
  };

  const tipRow = hover ? rows.find((row) => row.key === hover.key) : undefined;
  const on = analysis.bars.filter((bar) => bar.enabled).length;
  const biggest = biggestStep(analysis);
  const total = analysis.advantage;

  const summary = (
    <>
      {on === analysis.bars.length ? `All ${strategies(on)} on` : `${on} of ${analysis.bars.length} strategies on`}:{" "}
      {on === 0 ? (
        <>Donabach&apos;s plan is the advisor&apos;s own, so the advantage is zero.</>
      ) : (
        <>
          Donabach ends {dollarsText(total.median_dollars, horizon)} ahead of the {analysis.advisor_label.toLowerCase()} ({rateText(total.median_rate)}
          ).
          {biggest && (
            <>
              {" "}
              The biggest step is {biggest.label}: {dollarsText(biggest.delta_dollars, horizon)} ({rateText(biggest.delta_rate)}).
            </>
          )}
        </>
      )}
    </>
  );

  const controls = (
    <div className={styles.controls}>
      <div className={styles.unit}>
        <span className={styles.controlLabel}>Bars show</span>
        <Segmented<Unit>
          label="What the length of a bar shows"
          value={unit}
          onChange={setUnit}
          options={[
            { value: "dollars", label: `Dollars at ${horizon}` },
            { value: "rate", label: "Percent a year" },
          ]}
        />
      </div>
      <Button
        variant="ghost"
        className={styles.explain}
        aria-pressed={allOpen}
        onClick={() => setOpen(allOpen ? new Set() : new Set(strategyRows.map((row) => row.key)))}
      >
        <Icon name="info" size={18} />
        {allOpen ? "Hide the explanations" : "Explain each strategy"}
      </Button>
      {computing && (
        <span className={styles.recomputing} aria-hidden="true">
          <Spinner size={14} />
          Recomputing…
        </span>
      )}
    </div>
  );

  return (
    <ChartFrame
      label={`Waterfall from the ${analysis.advisor_label.toLowerCase()}'s result to Donabach's: what each strategy adds to median after-tax wealth at ${horizon}`}
      height="auto"
      wrapToolbar
      legend={controls}
      summary={summary}
      chart={
        <div ref={chart} className={styles.chart} data-stale={computing} aria-busy={computing}>
          <ol className={styles.rows} aria-label={`What each strategy adds, from the ${analysis.advisor_label.toLowerCase()}'s result to Donabach's`}>
            {rows.map((row, i) => (
              <RowView
                key={row.key}
                row={row}
                index={i}
                last={i === rows.length - 1}
                unit={unit}
                axis={axis}
                horizon={horizon}
                analysis={analysis}
                checked={enabled.includes(row.key)}
                open={open.has(row.key)}
                detailId={`${ids}-${row.key}`}
                onToggle={onToggle}
                onOpen={toggleOpen}
                onTrack={track}
                onLeave={() => setHover(null)}
                onFocus={focus}
                onBlur={leave}
              />
            ))}
          </ol>
          <div className={styles.axis} aria-hidden="true">
            <div className={styles.axisTicks}>
              {axis.ticks.map((tick) => {
                const at = place(axis, tick);
                return (
                  <span key={tick} className={styles.tick} data-edge={at < 1 ? "start" : at > 99 ? "end" : undefined} style={{ left: `${at}%` }}>
                    {tickText(unit, tick)}
                  </span>
                );
              })}
            </div>
          </div>
          <p className={styles.caption}>{axisCaption(unit, horizon)}</p>
          {hover && tipRow && (
            <div className={styles.tooltip} role="tooltip" data-flip={hover.x > hover.width - 290} style={{ left: hover.x, top: hover.y }}>
              <Tip row={tipRow} unit={unit} horizon={horizon} analysis={analysis} />
            </div>
          )}
        </div>
      }
      table={<WaterfallTable rows={rows} horizon={horizon} analysis={analysis} />}
    />
  );
}

/** What the tooltip says about a row: the change in both units, and the running total after it. */
function Tip({ row, unit, horizon, analysis }: { row: WaterfallRow; unit: Unit; horizon: number; analysis: ShowcaseAnalysis }) {
  if (row.kind === "start") {
    return (
      <>
        <div className={styles.tipName}>{row.label}</div>
        <div className={styles.tipValue}>{money(analysis.advantage.advisor_median_at_horizon)}</div>
        <div className={styles.tipDetail}>Median after-tax wealth at {horizon}: where everything is measured from</div>
      </>
    );
  }
  const first = unit === "dollars" ? dollarsText(row.delta.dollars, horizon) : rateText(row.delta.rate);
  const second = unit === "dollars" ? rateText(row.delta.rate) : dollarsText(row.delta.dollars, horizon);
  return (
    <>
      <div className={styles.tipName}>{row.kind === "total" ? "Donabach, in all" : row.label}</div>
      <div className={styles.tipValue}>{first}</div>
      <div className={styles.tipDetail}>{second}</div>
      {row.kind === "strategy" && !row.enabled ? (
        <div className={styles.tipDetail}>Switched off: it adds nothing</div>
      ) : (
        row.kind === "strategy" && (
          <div className={styles.tipDetail}>
            Running total: {rateText(row.to.rate)}, {dollarsText(row.to.dollars, horizon)}
          </div>
        )
      )}
    </>
  );
}

interface RowProps {
  row: WaterfallRow;
  index: number;
  last: boolean;
  unit: Unit;
  axis: Axis;
  horizon: number;
  analysis: ShowcaseAnalysis;
  checked: boolean;
  open: boolean;
  detailId: string;
  onToggle: (key: string, on: boolean) => void;
  onOpen: (key: string) => void;
  onTrack: (event: PointerEvent<HTMLElement>, key: string) => void;
  onLeave: () => void;
  onFocus: (event: FocusEvent<HTMLElement>, row: WaterfallRow) => void;
  onBlur: (event: FocusEvent<HTMLElement>) => void;
}

function RowView({ row, index, last, unit, axis, horizon, analysis, checked, open, detailId, onToggle, onOpen, onTrack, onLeave, onFocus, onBlur }: RowProps) {
  const off = row.kind === "strategy" && !row.enabled;
  const a = row.from[unit];
  const b = row.to[unit];
  const lo = place(axis, Math.min(a, b));
  const hi = place(axis, Math.max(a, b));
  const negative = b < a;
  // A strategy that is off adds nothing: an empty dashed bar centred on where the running total stands.
  const bar = off ? { left: `calc(${place(axis, b)}% - 14px)`, width: "28px" } : { left: `${lo}%`, width: `${hi - lo}%` };
  // The line that joins this bar to the one above it starts where the running total stood before the row (for the total, where the last strategy ended).
  const joinAbove = index === 0 ? null : place(axis, (row.kind === "total" ? row.to : row.from)[unit]);
  const joinBelow = last ? null : place(axis, b);

  const primary =
    row.kind === "start" ? "Starting point" : unit === "dollars" ? dollarsText(row.delta.dollars, horizon) : rateText(row.delta.rate);
  const secondary =
    row.kind === "start" ? "0 = the advisor's result" : unit === "dollars" ? rateText(row.delta.rate) : dollarsText(row.delta.dollars, horizon);
  const median =
    row.kind === "start"
      ? analysis.advantage.advisor_median_at_horizon
      : row.kind === "total"
        ? analysis.advantage.plan_median_at_horizon
        : undefined;

  return (
    <li
      className={styles.row}
      data-key={row.key}
      data-kind={row.kind}
      data-off={off || undefined}
      onFocus={(event) => onFocus(event, row)}
      onBlur={onBlur}
    >
      <div className={styles.name}>
        {row.kind === "strategy" ? (
          <>
            <div className={styles.nameLine}>
              <StrategySwitch label={row.label} checked={checked} onChange={(on) => onToggle(row.key, on)} describedBy={detailId} />
              <button
                type="button"
                className={styles.info}
                aria-expanded={open}
                aria-controls={detailId}
                aria-label={`What “${row.label}” does`}
                onClick={() => onOpen(row.key)}
              >
                <Icon name="info" size={18} />
              </button>
            </div>
            <p id={detailId} className={styles.detail} hidden={!open}>
              {row.detail}
            </p>
          </>
        ) : (
          <div className={styles.nameLine}>
            <span className={styles.plainName}>
              <strong>{row.label}</strong>
              {median !== undefined && (
                <span className={styles.sub}>
                  Median {money(median)} at {horizon}
                </span>
              )}
            </span>
          </div>
        )}
      </div>

      <div className={styles.track} data-track="" onPointerMove={(event) => onTrack(event, row.key)} onPointerLeave={onLeave}>
        {axis.ticks.map((tick) => (
          <span key={tick} className={styles.grid} data-zero={tick === 0} style={{ left: `${place(axis, tick)}%` }} />
        ))}
        {joinAbove !== null && <span className={styles.joint} data-part="above" style={{ left: `${joinAbove}%` }} />}
        {joinBelow !== null && <span className={styles.joint} data-part="below" style={{ left: `${joinBelow}%` }} />}
        {row.kind === "start" ? (
          <span className={styles.origin} style={{ left: `${place(axis, 0)}%` }} />
        ) : (
          <span
            className={styles.bar}
            data-kind={row.kind}
            data-off={off || undefined}
            data-negative={(!off && negative) || undefined}
            style={bar}
          />
        )}
      </div>

      <div className={styles.values}>
        <strong className={styles.primary}>{primary}</strong>
        <span className={styles.secondary}>{secondary}</span>
      </div>
    </li>
  );
}

/** The table twin: every number the chart draws or writes, row by row. */
function WaterfallTable({ rows, horizon, analysis }: { rows: readonly WaterfallRow[]; horizon: number; analysis: ShowcaseAnalysis }) {
  const columns: DataColumn<WaterfallRow>[] = [
    {
      key: "name",
      header: "Strategy",
      rowHeader: true,
      width: "34%",
      cell: (row) => (
        <>
          {row.label}
          {row.kind === "start" && <span className={styles.tableNote}>Starting point: median {money(analysis.advantage.advisor_median_at_horizon)} at {horizon}</span>}
          {row.kind === "total" && <span className={styles.tableNote}>Median {money(analysis.advantage.plan_median_at_horizon)} at {horizon}</span>}
          {row.kind === "strategy" && !row.enabled && <span className={styles.tableNote}>Switched off</span>}
        </>
      ),
    },
    { key: "rate", header: "Change a year", align: "end", width: "16%", cell: (row) => (row.kind === "start" ? "–" : ratePercent(row.delta.rate)) },
    { key: "dollars", header: `Change at ${horizon}`, align: "end", width: "16%", cell: (row) => (row.kind === "start" ? "–" : signedMoney(row.delta.dollars)) },
    { key: "rate-total", header: "Running total a year", align: "end", width: "18%", cell: (row) => (row.kind === "start" ? "0.00%" : ratePercent(row.to.rate)) },
    { key: "dollars-total", header: `Running total at ${horizon}`, align: "end", width: "16%", cell: (row) => (row.kind === "start" ? "$0" : signedMoney(row.to.dollars)) },
  ];
  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(row) => row.key}
      caption={`What each strategy adds to median after-tax wealth at ${horizon}, a year and in dollars, with the running total after it`}
      rowTone={(row) => (row.kind === "total" ? "highlight" : undefined)}
      minWidth={640}
    />
  );
}
