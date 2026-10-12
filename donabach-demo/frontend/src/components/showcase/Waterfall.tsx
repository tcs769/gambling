"use client";

import { useCallback, useId, useMemo, useRef, useState, type FocusEvent, type PointerEvent } from "react";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { Button, DataTable, Icon, Spinner, type DataColumn } from "@/components/ui";
import { money, signedMoney } from "@/lib/format";
import type { ShowcaseWaterfall } from "@/lib/types";
import { Segmented } from "./Segmented";
import { StrategySwitch } from "./StrategySwitch";
import { useElementWidth } from "./useElementWidth";
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
import { strategiesOn } from "./text";
import styles from "./Waterfall.module.css";

interface Hover {
  key: string;
  /** Where the tooltip points, in pixels from the top left of the chart. */
  x: number;
  y: number;
  width: number;
}

interface WaterfallProps {
  /** The waterfall on screen (it may be a step behind the switches while a new one is being worked out). */
  waterfall: ShowcaseWaterfall;
  /** The waterfall with every strategy on: the axis is never narrower than its bars, so a bar shrinks against a scale that stays put. */
  full: ShowcaseWaterfall;
  /** The strategies that are switched on: what the switches show. */
  enabled: readonly string[];
  /** A new waterfall is on its way: the bars and numbers are dimmed until it arrives. */
  computing: boolean;
  onToggle: (key: string, on: boolean) => void;
  /** Put every strategy back on. */
  onAllOn: () => void;
}

/**
 * The waterfall from the advisor's result to Donabach's. One bar per strategy, drawn floating: it starts where the
 * running total stood before the strategy and ends where it stood after, so the bars join up from the advisor (zero) to
 * the total (Donabach). A switch on every row turns the strategy off and the API measures the rest again; a strategy
 * that is off is an empty dashed bar of zero. What a bar's length means is a choice (dollars at the horizon or a yearly
 * rate), and both numbers are written on every row whichever is chosen. The same numbers are one toggle away as a table.
 */
export function Waterfall({ waterfall, full, enabled, computing, onToggle, onAllOn }: WaterfallProps) {
  const [unit, setUnit] = useState<Unit>("dollars");
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [hover, setHover] = useState<Hover | null>(null);
  const chart = useRef<HTMLDivElement | null>(null);
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const setChart = useCallback(
    (node: HTMLDivElement | null) => {
      chart.current = node;
      measure(node);
    },
    [measure],
  );
  const ids = useId();

  const horizon = waterfall.horizon_age;
  const rows = useMemo(() => waterfallRows(waterfall), [waterfall]);
  // Seven tick labels do not fit a phone's width: a narrow chart gets half as many.
  const axis = useMemo(
    () => axisFor(unit, [waterfall, full], width > 0 && width < 560 ? 3 : 6),
    [unit, waterfall, full, width],
  );
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
    const trackEl = event.currentTarget.querySelector<HTMLElement>("[data-track]");
    if (!box || !trackEl) return;
    const trackBox = trackEl.getBoundingClientRect();
    // Beside the end of the row's bar: how far down the track its middle is is a style (--mid), as it differs by layout.
    const mid = parseFloat(getComputedStyle(trackEl).getPropertyValue("--mid")) || 28;
    const x = trackBox.left - box.left + (place(axis, row.to[unit]) / 100) * trackBox.width;
    setHover({ key: row.key, x, y: trackBox.top - box.top + mid, width: box.width });
  };
  const leave = (event: FocusEvent<HTMLElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setHover(null);
  };

  const tipRow = hover ? rows.find((row) => row.key === hover.key) : undefined;
  const on = waterfall.bars.filter((bar) => bar.enabled).length;
  const biggest = biggestStep(waterfall);
  const total = waterfall.advantage;

  // The figure's text alternative, in words: how many strategies are on, what they come to, and the biggest step.
  const advisorName = waterfall.advisor_label.toLowerCase();
  const ahead = total.median_dollars >= 0;
  const summary = (
    <>
      {strategiesOn(on, waterfall.bars.length)}:{" "}
      {on === 0 ? (
        <>Donabach&apos;s plan is the {advisorName}&apos;s own, so the advantage is zero.</>
      ) : (
        <>
          at {horizon} Donabach is {money(Math.abs(total.median_dollars))} {ahead ? "ahead of" : "behind"} the{" "}
          {advisorName} ({rateText(total.median_rate)}).
          {biggest && (
            <>
              {" "}
              The biggest step is {biggest.label}: {dollarsText(biggest.delta_dollars, horizon)} (
              {rateText(biggest.delta_rate)}).
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
        onClick={() => setOpen(allOpen ? new Set() : new Set(strategyRows.map((row) => row.key)))}
      >
        <Icon name="info" size={18} />
        {allOpen ? "Hide the explanations" : "Explain each strategy"}
      </Button>
      {enabled.length < waterfall.bars.length && (
        <Button variant="secondary" className={styles.allOn} onClick={onAllOn}>
          Switch every strategy on
        </Button>
      )}
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
      label={`Waterfall from the ${waterfall.advisor_label.toLowerCase()}'s result to Donabach's: what each strategy adds to median after-tax wealth at ${horizon}`}
      height="auto"
      wrapToolbar
      legend={controls}
      summary={summary}
      chart={
        <div ref={setChart} className={styles.chart} data-stale={computing} aria-busy={computing}>
          <ol
            className={styles.rows}
            aria-label={`What each strategy adds, from the ${waterfall.advisor_label.toLowerCase()}'s result to Donabach's`}
          >
            {rows.map((row, i) => (
              <RowView
                key={row.key}
                row={row}
                index={i}
                last={i === rows.length - 1}
                unit={unit}
                axis={axis}
                horizon={horizon}
                waterfall={waterfall}
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
                  <span
                    key={tick}
                    className={styles.tick}
                    data-edge={at < 1 ? "start" : at > 99 ? "end" : undefined}
                    style={{ left: `${at}%` }}
                  >
                    {tickText(unit, tick)}
                  </span>
                );
              })}
            </div>
          </div>
          <p className={styles.caption}>{axisCaption(unit, horizon)}</p>
          {hover && tipRow && (
            <div
              className={styles.tooltip}
              role="tooltip"
              data-flip={hover.x > hover.width - 290}
              style={{ left: hover.x, top: hover.y }}
            >
              <Tip row={tipRow} unit={unit} horizon={horizon} waterfall={waterfall} />
            </div>
          )}
        </div>
      }
      table={<WaterfallTable rows={rows} horizon={horizon} waterfall={waterfall} />}
    />
  );
}

/** What the tooltip says about a row: the change in both units, and the running total after it. */
function Tip({
  row,
  unit,
  horizon,
  waterfall,
}: {
  row: WaterfallRow;
  unit: Unit;
  horizon: number;
  waterfall: ShowcaseWaterfall;
}) {
  if (row.kind === "start") {
    return (
      <>
        <div className={styles.tipName}>{row.label}</div>
        <div className={styles.tipValue}>{money(waterfall.advantage.advisor_median_at_horizon)}</div>
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
      ) : isIdle(row) ? (
        <div className={styles.tipDetail}>On, but it adds nothing to the strategies before it</div>
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

/** A strategy that is on and, given the ones before it, changes nothing (it needs something that is switched off). */
const isIdle = (row: WaterfallRow): boolean =>
  row.kind === "strategy" && row.enabled && row.delta.dollars === 0 && row.delta.rate === 0;

interface RowProps {
  row: WaterfallRow;
  index: number;
  last: boolean;
  unit: Unit;
  axis: Axis;
  horizon: number;
  waterfall: ShowcaseWaterfall;
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

function RowView({
  row,
  index,
  last,
  unit,
  axis,
  horizon,
  waterfall,
  checked,
  open,
  detailId,
  onToggle,
  onOpen,
  onTrack,
  onLeave,
  onFocus,
  onBlur,
}: RowProps) {
  const off = row.kind === "strategy" && !row.enabled;
  // A strategy with no sentence about it has nothing to open.
  const hasDetail = row.detail.trim() !== "";
  // On, but with the strategies before it the API measures no change at all: a sliver of a bar and zeros, so it says why.
  const idle = isIdle(row);
  const a = row.from[unit];
  const b = row.to[unit];
  const lo = place(axis, Math.min(a, b));
  const hi = place(axis, Math.max(a, b));
  const negative = b < a;
  // A strategy that is off adds nothing: an empty dashed bar centred on where the running total stands.
  const bar = off
    ? { left: `calc(${place(axis, b)}% - 14px)`, width: "28px" }
    : { left: `${lo}%`, width: `${hi - lo}%` };
  // The line that joins this bar to the one above it starts where the running total stood before the row (for the total, where the last strategy ended).
  const joinAbove = index === 0 ? null : place(axis, (row.kind === "total" ? row.to : row.from)[unit]);
  const joinBelow = last ? null : place(axis, b);

  const primary =
    row.kind === "start"
      ? "Starting point"
      : unit === "dollars"
        ? dollarsText(row.delta.dollars, horizon)
        : rateText(row.delta.rate);
  const secondary =
    row.kind === "start"
      ? "0 = the advisor's result"
      : unit === "dollars"
        ? rateText(row.delta.rate)
        : dollarsText(row.delta.dollars, horizon);
  const median =
    row.kind === "start"
      ? waterfall.advantage.advisor_median_at_horizon
      : row.kind === "total"
        ? waterfall.advantage.plan_median_at_horizon
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
              <StrategySwitch
                label={row.label}
                checked={checked}
                onChange={(on) => onToggle(row.key, on)}
                describedBy={hasDetail ? detailId : undefined}
              />
              {hasDetail && (
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
              )}
            </div>
            {idle && <p className={styles.idle}>On, but it adds nothing here.</p>}
            {hasDetail && (
              <p id={detailId} className={styles.detail} hidden={!open}>
                {row.detail}
              </p>
            )}
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

      <div
        className={styles.track}
        data-track=""
        onPointerMove={(event) => onTrack(event, row.key)}
        onPointerLeave={onLeave}
      >
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
function WaterfallTable({
  rows,
  horizon,
  waterfall,
}: {
  rows: readonly WaterfallRow[];
  horizon: number;
  waterfall: ShowcaseWaterfall;
}) {
  const columns: DataColumn<WaterfallRow>[] = [
    {
      key: "name",
      header: "Strategy",
      rowHeader: true,
      width: "34%",
      cell: (row) => (
        <>
          {row.label}
          {row.kind === "start" && (
            <span className={styles.tableNote}>
              Starting point: median {money(waterfall.advantage.advisor_median_at_horizon)} at {horizon}
            </span>
          )}
          {row.kind === "total" && (
            <span className={styles.tableNote}>
              Median {money(waterfall.advantage.plan_median_at_horizon)} at {horizon}
            </span>
          )}
          {row.kind === "strategy" && !row.enabled && <span className={styles.tableNote}>Switched off</span>}
          {isIdle(row) && <span className={styles.tableNote}>On, but it adds nothing here</span>}
        </>
      ),
    },
    {
      key: "rate",
      header: "Change a year",
      align: "end",
      width: "16%",
      cell: (row) => (row.kind === "start" ? "–" : ratePercent(row.delta.rate)),
    },
    {
      key: "dollars",
      header: `Change at ${horizon}`,
      align: "end",
      width: "16%",
      cell: (row) => (row.kind === "start" ? "–" : signedMoney(row.delta.dollars)),
    },
    {
      key: "rate-total",
      header: "Running total a year",
      align: "end",
      width: "18%",
      cell: (row) => (row.kind === "start" ? "0.00%" : ratePercent(row.to.rate)),
    },
    {
      key: "dollars-total",
      header: `Running total at ${horizon}`,
      align: "end",
      width: "16%",
      cell: (row) => (row.kind === "start" ? "$0" : signedMoney(row.to.dollars)),
    },
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
