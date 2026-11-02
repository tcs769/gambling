"use client";

import { useState } from "react";
import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { usePortal } from "@/lib/portal-state";
import { amountOrDash, percent0, percentTrim } from "@/lib/invest-format";
import { Btn } from "@/components/portal/Btn";
import { colorOf } from "./asset-colors";
import { MixBar } from "./MixBar";
import { ProjectionChart } from "./ProjectionChart";
import { StatusPill } from "./StatusPill";
import styles from "./Overview.module.css";
import t from "./invest.module.css";

type Move = Plan["portfolio"]["overview"]["moves"][number];

/** Darkest the "What goes where" shading gets (navy at this alpha keeps the text above 4.5:1). */
const MAX_SHADE = 0.34;

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
  const shade = (value: number): React.CSSProperties =>
    value > 0.5 && largest > 0
      ? { backgroundColor: `rgba(31, 58, 95, ${(0.05 + (MAX_SHADE - 0.05) * (value / largest)).toFixed(3)})` }
      : {};

  return (
    <div>
      <section className={t.section} aria-labelledby="ov-wealth">
        <h2 id="ov-wealth" className={t.heading}>
          Projected wealth
        </h2>
        <ProjectionChart overview={overview} horizon={summary.horizon_age} />
      </section>

      <section className={t.section} aria-labelledby="ov-mix">
        <h2 id="ov-mix" className={t.heading}>
          Overall mix
        </h2>
        <MixBar items={overview.mix.rows} changed={movedClasses} label="Overall mix" />
        <div className={`${t.tableWrap} ${styles.mixTable}`}>
          <table className={t.table} data-testid="mix-table">
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
                  Expected return
                </th>
              </tr>
            </thead>
            <tbody>
              {overview.mix.rows.map((row) => {
                const none = row.amount < 0.5;
                return (
                  <tr key={row.key} className={movedClasses.has(row.key) ? t.changedRow : undefined} data-row={row.key}>
                    <th scope="row">
                      <span className={styles.swatch} style={{ background: colorOf(row.key) }} aria-hidden="true" />
                      {row.label}
                      {movedClasses.has(row.key) && <span className={t.tag}>Changed</span>}
                    </th>
                    <td className={`${t.right} ${none ? t.dash : ""}`}>{amountOrDash(row.amount)}</td>
                    <td className={`${t.right} ${none ? t.dash : ""}`}>{none ? "—" : percent0(row.share)}</td>
                    <td className={`${t.right} ${none ? t.dash : ""}`}>
                      {none ? "—" : percentTrim(row.expected_return)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className={t.section} aria-labelledby="ov-where">
        <h2 id="ov-where" className={t.heading}>
          What goes where
        </h2>
        <div className={t.tableWrap}>
          <table className={t.table} data-testid="location-table">
            <caption>What goes where</caption>
            <thead>
              <tr>
                <th scope="col">Asset class</th>
                <th scope="col" className={t.right}>
                  Brokerage
                </th>
                <th scope="col" className={t.right}>
                  401(k)/IRA
                </th>
                <th scope="col" className={t.right}>
                  Roth IRA
                </th>
                <th scope="col" className={t.right}>
                  Total
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
                  {([row.brokerage, row.pretax, row.roth] as const).map((value, i) => (
                    <td
                      key={i}
                      className={`${t.right} ${styles.cell} ${value < 0.5 ? t.dash : ""}`}
                      style={shade(value)}
                      data-shaded={value > 0.5 || undefined}
                    >
                      {amountOrDash(value)}
                    </td>
                  ))}
                  <td className={t.right}>{amountOrDash(row.total)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">Total</th>
                <td className={t.right}>{amountOrDash(overview.location.total.brokerage)}</td>
                <td className={t.right}>{amountOrDash(overview.location.total.pretax)}</td>
                <td className={t.right}>{amountOrDash(overview.location.total.roth)}</td>
                <td className={t.right}>{amountOrDash(overview.location.total.total)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>

      <section className={t.section} aria-labelledby="ov-moves">
        <h2 id="ov-moves" className={t.heading}>
          This year&rsquo;s moves
        </h2>
        <div className={t.tableWrap}>
          <table className={`${t.table} ${styles.moves}`} data-testid="moves-table">
            <caption>This year&rsquo;s moves</caption>
            <thead>
              <tr>
                <th scope="col">Move</th>
                <th scope="col" className={t.right}>
                  Amount
                </th>
                <th scope="col">When</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {overview.moves.map((move) => {
                const ok = move.status === "needs_ok" && approved[move.key];
                const status = ok ? "scheduled" : move.status;
                return (
                  <tr key={move.key} className={isChangedMove(move) ? t.changedRow : undefined} data-move={move.key}>
                    <th scope="row" className={styles.title}>
                      {move.title}
                      {isChangedMove(move) && <span className={t.tag}>Changed</span>}
                    </th>
                    <td className={`${t.right} ${styles.amount}`}>
                      {move.amount === null || move.amount === undefined ? (
                        <span className={t.dash}>—</span>
                      ) : (
                        <>
                          {dollarsWhole(move.amount)}
                          {move.detail && <span className={styles.detail}>{move.detail}</span>}
                        </>
                      )}
                      {(move.amount === null || move.amount === undefined) && move.detail && (
                        <span className={styles.detail}>{move.detail}</span>
                      )}
                    </td>
                    <td className={styles.when}>{move.timing}</td>
                    <td className={styles.statusCell}>
                      <StatusPill status={status} />
                      {move.status === "needs_ok" && !ok && (
                        <Btn
                          variant="secondary"
                          className={styles.approve}
                          aria-label={`Approve ${move.title}, ${move.timing}`}
                          onClick={() => {
                            actions.approve(plan.plan_id, move.key, true);
                            setAnnounce(`${move.title}, ${move.timing}: scheduled`);
                          }}
                        >
                          Approve
                        </Btn>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="sr-only" role="status" aria-live="polite">
          {announce}
        </p>
      </section>
    </div>
  );
}
