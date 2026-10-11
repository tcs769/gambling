"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Drawer, Icon, Pill, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { dollars, money, percent } from "@/lib/format";
import type { Decision, Household, PlanResponse, TaxLine, YearDetail } from "@/lib/types";
import styles from "./YearDrawer.module.css";

/** What a decision is worth: the change in after-tax wealth at 70 if it is removed for this year. */
function Worth({ decision }: { decision: Decision }) {
  const value = decision.value;
  if (!decision.valued || value === null || value === undefined) {
    return <span className={styles.context}>Context, not valued separately</span>;
  }
  if (Math.abs(value) < 0.5) return <Pill>No difference by 70</Pill>;
  return value > 0 ? (
    <Pill tone="good" icon={<Icon name="check" size={14} strokeWidth={2.8} />}>
      Worth +{money(value)} by 70
    </Pill>
  ) : (
    <Pill tone="bad" icon={<Icon name="alert" size={14} />}>
      Costs {money(-value)} by 70
    </Pill>
  );
}

function TaxRow({ line }: { line: TaxLine }) {
  const zero = line.kind === "amount" && Math.abs(line.amount) < 0.5;
  return (
    <tr data-kind={line.kind} data-zero={zero}>
      <th scope="row">
        {line.label}
        {line.note && <span className={styles.lineNote}>{line.note}</span>}
      </th>
      <td>{line.kind === "rate" ? percent(line.amount) : dollars(line.amount)}</td>
    </tr>
  );
}

interface YearDrawerProps {
  plan: PlanResponse;
  /** The household the plan on screen was made for (a what-if's, if one is active). */
  household: Household;
  /** The selected row's year_index, or null for closed. */
  selected: number | null;
  onSelect: (yearIndex: number | null) => void;
}

/**
 * One year of the plan, opened from a table row: the decisions taken and what each is worth, then
 * the full tax return line by line. Details are fetched on demand and kept per plan, so going back
 * to a year is instant; a new plan (a what-if) starts a fresh set.
 */
export function YearDrawer({ plan, household, selected, onSelect }: YearDrawerProps) {
  const row = selected === null ? undefined : plan.rows.find((r) => r.year_index === selected);
  const [cache, setCache] = useState<{ plan: PlanResponse; byYear: Record<number, YearDetail> }>({ plan, byYear: {} });
  const [failure, setFailure] = useState<{ plan: PlanResponse; year: number; message: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const body = useRef<HTMLDivElement>(null);

  const detail = selected !== null && cache.plan === plan ? cache.byYear[selected] : undefined;
  const failed = failure && failure.plan === plan && failure.year === selected ? failure.message : undefined;

  useEffect(() => {
    if (selected === null || detail || failed) return;
    api
      .yearDetail(household, plan.strategy.choices, selected, plan.settings.market_shock ?? null)
      .then((result) =>
        setCache((prev) => ({ plan, byYear: { ...(prev.plan === plan ? prev.byYear : {}), [selected]: result } })),
      )
      .catch((e: Error) => setFailure({ plan, year: selected, message: e.message }));
  }, [selected, detail, failed, household, plan, attempt]);

  // A different year starts at the top of the panel.
  useEffect(() => {
    body.current?.parentElement?.scrollTo({ top: 0 });
  }, [selected]);

  if (!row) return null;
  const index = plan.rows.findIndex((r) => r.year_index === row.year_index);
  const previous = plan.rows[index - 1];
  const next = plan.rows[index + 1];

  return (
    <Drawer
      open
      onClose={() => onSelect(null)}
      eyebrow={`Year ${index + 1} of ${plan.rows.length}`}
      title={`Age ${row.age}`}
      restoreFocus={() => document.querySelector<HTMLElement>(`tr[data-row-key="${row.year_index}"]`)}
      actions={
        <>
          <button
            type="button"
            className={styles.step}
            disabled={!previous}
            onClick={() => previous && onSelect(previous.year_index)}
            aria-label={previous ? `Previous year, age ${previous.age}` : "Previous year"}
          >
            <Icon name="chevron" size={20} className={styles.back} />
          </button>
          <button
            type="button"
            className={styles.step}
            disabled={!next}
            onClick={() => next && onSelect(next.year_index)}
            aria-label={next ? `Next year, age ${next.age}` : "Next year"}
          >
            <Icon name="chevron" size={20} />
          </button>
        </>
      }
    >
      <div ref={body}>
        <dl className={styles.summary}>
          <div>
            <dt>Income</dt>
            <dd>{money(row.income)}</dd>
          </div>
          <div>
            <dt>Total tax</dt>
            <dd>{dollars(row.total_tax)}</dd>
          </div>
          <div>
            <dt>Year-end wealth</dt>
            <dd>{money(row.wealth)}</dd>
          </div>
        </dl>

        {failed ? (
          <div className={styles.failure} role="alert">
            <Icon name="alert" size={20} />
            <div>
              <p>{failed}</p>
              <Button
                variant="secondary"
                onClick={() => {
                  setFailure(null);
                  setAttempt((n) => n + 1);
                }}
              >
                Try again
              </Button>
            </div>
          </div>
        ) : !detail ? (
          <div className={styles.loading} aria-busy="true">
            <Spinner label="Loading this year's decisions and tax return..." />
          </div>
        ) : (
          <>
            <section className={styles.section} aria-labelledby="year-decisions">
              <h3 id="year-decisions">Decisions this year</h3>
              <p className={styles.caption}>
                Each value is how much after-tax wealth at 70 changes if that one decision is removed for this year.
              </p>
              <ul className={styles.decisions}>
                {detail.decisions.map((decision) => (
                  <li key={decision.key} className={styles.decision}>
                    <div className={styles.decisionHead}>
                      <strong>{decision.label}</strong>
                      <Worth decision={decision} />
                    </div>
                    <p>{decision.description}</p>
                  </li>
                ))}
              </ul>
            </section>

            <section className={styles.section} aria-labelledby="year-tax">
              <h3 id="year-tax">Tax return, line by line</h3>
              <p className={styles.caption}>Exact dollars for age {detail.age}, federal and Illinois, married filing jointly.</p>
              <table className={styles.tax}>
                <caption className="sr-only">Tax return for age {detail.age}</caption>
                <tbody>
                  {detail.tax_lines.map((line, i) => (
                    <TaxRow key={`${line.label}-${i}`} line={line} />
                  ))}
                </tbody>
              </table>
            </section>
          </>
        )}
      </div>
    </Drawer>
  );
}
