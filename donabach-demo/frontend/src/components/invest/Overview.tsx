"use client";

import { useState } from "react";
import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { usePortal } from "@/lib/portal-state";
import { amountOrDash, percent0, percentTrim } from "@/lib/invest-format";
import { colorOf } from "./asset-colors";
import { MixBar } from "./MixBar";
import { ProjectionChart } from "./ProjectionChart";
import { StatusPill } from "./StatusPill";
import styles from "./Overview.module.css";
import t from "./invest.module.css";

type Move = Plan["portfolio"]["overview"]["moves"][number];

/** The mockup's three shades for "What goes where": by the size of the cell against the largest one. */
function shadeOf(value: number, largest: number): "c1" | "c2" | "c3" | null {
  if (value < 0.5 || largest <= 0) return null;
  const ratio = value / largest;
  return ratio >= 0.35 ? "c3" : ratio >= 0.12 ? "c2" : "c1";
}

const money = (value: number) => <b className="num">{dollarsWhole(value)}</b>;

/** What a move says, in the words of the mockup, built from the API's move (its key, title, amount and detail). */
function MoveText({ move }: { move: Move }) {
  const amount = move.amount ?? 0;
  const hasAmount = move.amount !== null && move.amount !== undefined && Math.abs(amount) >= 0.5;
  switch (move.key) {
    case "invest":
      return <>Invested your savings in the target mix{hasAmount && <>, {money(amount)}</>}</>;
    case "lots":
      return <>Selling the highest-cost shares first</>;
    case "harvest":
      return <>{move.title}{hasAmount && <>, {money(amount)} harvested so far</>}</>;
    case "conversion":
    case "conversion_next":
      return (
        <>
          Convert {money(amount)} from your 401(k) / IRA to your Roth
          {move.detail && (
            <span className={styles.detail}> ({move.detail.charAt(0).toLowerCase() + move.detail.slice(1)})</span>
          )}
        </>
      );
    case "k401":
      return <>Raise your 401(k) contribution to {money(amount)} through your employer</>;
    default:
      return (
        <>
          {move.title}
          {hasAmount && <>, {money(amount)}</>}
          {move.detail && <span className={styles.detail}> ({move.detail})</span>}
        </>
      );
  }
}

export function Overview({ plan }: { plan: Plan }) {
  const { state, actions } = usePortal();
  const [announce, setAnnounce] = useState("");
  const { overview, summary } = plan.portfolio;
  const changed = plan.what_changed;
  const movedClasses = new Set(changed?.mix.filter((row) => row.moved).map((row) => row.key));
  const changedMoves = (changed?.moves ?? []).filter((m) => m.kind !== "removed");
  const isChangedMove = (move: Move) =>
    changedMoves.some((c) => c.title === move.title || c.title === `${move.title} at ${move.age}`);
  const approved = state.approved[plan.plan_id] ?? {};

  const largest = Math.max(0, ...overview.location.rows.flatMap((row) => [row.brokerage, row.pretax, row.roth]));

  return (
    <div>
      <section className={t.panel} aria-labelledby="ov-wealth">
        <div className={t.panelHead}>
          <h2 id="ov-wealth" className={t.sectionT}>
            Projected wealth
          </h2>
          <span className={t.mutedS}>Typical outcome, after tax</span>
        </div>
        <ProjectionChart overview={overview} horizon={summary.horizon_age} />
      </section>

      <div className={t.twocol}>
        <section className={t.panel} aria-labelledby="ov-mix">
          <div className={t.panelHead}>
            <h2 id="ov-mix" className={t.sectionT}>
              Overall mix
            </h2>
          </div>
          <MixBar items={overview.mix.rows} changed={movedClasses} label="Overall mix" legend={false} />
          <div className={t.scroll}>
            <table className={t.hold} data-testid="mix-table">
              <caption>Overall mix</caption>
              <thead>
                <tr>
                  <th scope="col">Asset class</th>
                  <th scope="col" className={t.right}>
                    Amount
                  </th>
                  <th scope="col" className={t.right}>
                    Share
                  </th>
                  <th scope="col" className={t.right}>
                    Exp. return
                  </th>
                </tr>
              </thead>
              <tbody>
                {overview.mix.rows.map((row) => {
                  const none = row.amount < 0.5;
                  return (
                    <tr
                      key={row.key}
                      className={movedClasses.has(row.key) ? t.changedRow : undefined}
                      data-row={row.key}
                    >
                      <th scope="row">
                        <i className={styles.swatch} style={{ background: colorOf(row.key) }} aria-hidden="true" />
                        {row.label}
                        {movedClasses.has(row.key) && <span className={t.tag}>Changed</span>}
                      </th>
                      <td className={`${t.right} num ${none ? t.dash : ""}`}>{amountOrDash(row.amount)}</td>
                      <td className={`${t.right} num ${none ? t.dash : ""}`}>{none ? "–" : percent0(row.share)}</td>
                      <td className={`${t.right} num ${none ? t.dash : ""}`}>
                        {none ? "–" : percentTrim(row.expected_return)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className={t.panel} aria-labelledby="ov-where">
          <div className={t.panelHead}>
            <h2 id="ov-where" className={t.sectionT}>
              What goes where
            </h2>
          </div>
          <div className={t.scroll}>
            <table className={`${t.hold} ${styles.matrix}`} data-testid="location-table">
              <caption>What goes where</caption>
              <thead>
                <tr>
                  <th scope="col">
                    <span className="sr-only">Asset class</span>
                  </th>
                  <th scope="col" className={t.right}>
                    Brokerage
                  </th>
                  <th scope="col" className={t.right}>
                    401(k) / IRA
                  </th>
                  <th scope="col" className={t.right}>
                    Roth IRA
                  </th>
                </tr>
              </thead>
              <tbody>
                {overview.location.rows.map((row) => (
                  <tr
                    key={row.key}
                    className={movedClasses.has(row.key) ? styles.movedLocation : undefined}
                    data-row={row.key}
                  >
                    <th scope="row">
                      {row.label}
                      {movedClasses.has(row.key) && <span className={t.tag}>Changed</span>}
                    </th>
                    {([row.brokerage, row.pretax, row.roth] as const).map((value, i) => {
                      const shade = shadeOf(value, largest);
                      return (
                        <td
                          key={i}
                          className={`${t.right} num ${shade ? styles[shade] : t.dash}`}
                          data-shade={shade ?? undefined}
                        >
                          {amountOrDash(value)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className={styles.tot}>
                  <th scope="row">Total</th>
                  <td className={`${t.right} num`}>{amountOrDash(overview.location.total.brokerage)}</td>
                  <td className={`${t.right} num`}>{amountOrDash(overview.location.total.pretax)}</td>
                  <td className={`${t.right} num`}>{amountOrDash(overview.location.total.roth)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          <p className={`${t.mutedS} ${styles.caption}`}>Darker cells hold more of each asset class.</p>
        </section>
      </div>

      <section className={t.panel} aria-labelledby="ov-moves">
        <div className={t.panelHead}>
          <h2 id="ov-moves" className={t.sectionT}>
            This year&rsquo;s moves
          </h2>
          <span className={t.mutedS}>Waramoug handles these for you</span>
        </div>
        <ul className={styles.moves} data-testid="moves-list">
          {overview.moves.map((move) => {
            const ok = move.status === "needs_ok" && approved[move.key];
            const status = ok ? "scheduled" : move.status;
            const changedRow = isChangedMove(move);
            return (
              <li key={move.key} className={changedRow ? styles.changedMove : undefined} data-move={move.key}>
                <StatusPill status={status} />
                <span className={styles.what}>
                  <MoveText move={move} />
                  {changedRow && <span className={t.tag}>Changed</span>}
                </span>
                <span className={styles.when}>
                  {move.status === "needs_ok" && !ok ? (
                    <span className={styles.whenWrap}>
                      <span className={styles.whenText}>{move.timing}</span>
                      <button
                        type="button"
                        className={styles.mini}
                        aria-label={`Approve ${move.title}, ${move.timing}`}
                        onClick={() => {
                          actions.approve(plan.plan_id, move.key, true);
                          setAnnounce(`${move.title}, ${move.timing}: scheduled`);
                        }}
                      >
                        Approve
                      </button>
                    </span>
                  ) : (
                    move.timing
                  )}
                </span>
              </li>
            );
          })}
        </ul>
        <p className="sr-only" role="status" aria-live="polite">
          {announce}
        </p>
      </section>
    </div>
  );
}
