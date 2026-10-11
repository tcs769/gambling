"use client";

import { ChoiceChips } from "@/components/plan/StrategyCard";
import { AdaptiveFailure, ProgressBar, progressWords } from "@/components/plan/Refining";
import { Disclosure, Panel, PanelTitle, Spinner } from "@/components/ui";
import {
  agesList,
  beforeDropNote,
  beforeDropReason,
  changedChoices,
  departureComparison,
  differingYears,
  sentence,
} from "@/lib/adaptive";
import { count, percentTrim } from "@/lib/format";
import { adaptiveSection, useApp, type AdaptiveState } from "@/lib/state";
import { CHOICE_LABELS, optionLabel } from "@/lib/types";
import styles from "./WhatChanged.module.css";

/** Why a year-by-year plan is not there to compare, in words; null when it is. */
function missing(state: AdaptiveState | undefined, which: "before" | "after"): { busy?: number; failure?: string; text?: string } | null {
  const whose = which === "before" ? "your unmodified plan" : "the what-if";
  switch (state?.status) {
    case "ready":
      return null;
    case "refining":
      return { busy: state.progress, text: `The year-by-year plan for ${whose} is still being refined.` };
    case "failed":
      return { failure: state.message, text: `The year-by-year plan for ${whose} could not be completed, so its choices cannot be compared.` };
    default:
      return { text: `There is no year-by-year plan for ${whose}, so its choices cannot be compared.` };
  }
}

/**
 * What a what-if changed in the plan, from what was on screen before it (the unmodified household's fixed and
 * year-by-year plans, kept) and what is on screen now: the recommended strategy's choices that changed; the years
 * where the planner's chosen action differs; and how often the planner changes anything, in the year of a market drop
 * and after it against before. It states the differences it finds and no cause, and where nothing differs it says so.
 */
export function WhatChangedPanel() {
  const { state, plan, basePlan, adaptive, baseAdaptive, whatIfActive } = useApp();
  if (!whatIfActive || !plan || !basePlan) return null;
  const shock = state.whatIf?.response.shock ?? plan.settings.market_shock ?? null;
  // A what-if that changes more than the market: the note for a year before the drop must not say "only".
  const otherChanges = (state.whatIf?.response.changes ?? []).some((change) => change.field !== "market_shock");
  const dropNote = sentence(beforeDropNote(otherChanges));

  const changed = changedChoices(basePlan.strategy.choices, plan.strategy.choices);
  const changedChoiceList = Object.entries(changed);
  const total = Object.keys(plan.strategy.choices).length;

  const before = adaptiveSection(baseAdaptive);
  const after = adaptiveSection(adaptive);
  const wait = missing(baseAdaptive, "before") ?? missing(adaptive, "after");
  const same = before && after ? differingYears(before, after, shock) : null;
  const rates = before && after ? departureComparison(before, after, shock) : null;
  const afterDrop = same?.differing.filter((d) => !d.beforeShock) ?? [];
  const beforeDropYears = same?.differing.filter((d) => d.beforeShock) ?? [];
  const evalPaths = after?.n_eval_paths;

  return (
    <Panel aria-labelledby="whatchanged-title" className={styles.panel}>
      <PanelTitle id="whatchanged-title" aside="Your plan before the what-if, against the plan now">
        What changed in the plan
      </PanelTitle>

      <section className={styles.part} aria-labelledby="whatchanged-strategy">
        <h3 id="whatchanged-strategy">The recommended strategy</h3>
        <p className={styles.lead}>
          {changedChoiceList.length === 0
            ? "The recommended strategy is the same as before the what-if."
            : `The what-if changed ${changedChoiceList.length} of the recommended strategy's ${total} choices: ${changedChoiceList
                .map(([choice, was]) => `${CHOICE_LABELS[choice] ?? choice} (was ${was === undefined ? "not set" : optionLabel(choice, was)})`)
                .join(", ")}.`}
        </p>
        <ChoiceChips
          choices={plan.strategy.choices}
          changed={changed}
          label="The recommended strategy after the what-if, with the choices that changed marked"
        />
      </section>

      {wait ? (
        <section className={styles.part} data-waiting="true" aria-labelledby="whatchanged-years" aria-busy={wait.busy !== undefined}>
          <h3 id="whatchanged-years">The planner&apos;s year-by-year choices</h3>
          <div className={styles.waiting}>
            {wait.failure !== undefined ? (
              <AdaptiveFailure message={wait.failure}>{wait.text}</AdaptiveFailure>
            ) : (
              <>
                <p>{wait.text}</p>
                {wait.busy !== undefined && (
                  <p className={styles.progress}>
                    <Spinner size={16} />
                    <ProgressBar progress={wait.busy} />
                    <span aria-hidden="true">{progressWords(wait.busy)}</span>
                  </p>
                )}
                <p className={styles.quiet}>
                  The comparison of its choices, and of how often it changes something, appears here when both plans are ready.
                </p>
              </>
            )}
          </div>
        </section>
      ) : (
        same &&
        rates &&
        evalPaths !== undefined && (
          <>
            <section className={styles.part} aria-labelledby="whatchanged-years">
              <h3 id="whatchanged-years">Years where the planner&apos;s chosen action differs</h3>
              {same.differing.length === 0 ? (
                <p className={styles.lead}>
                  None. The planner&apos;s chosen action is the same as before the what-if in all {same.compared} years: its
                  year-by-year decisions did not change.
                </p>
              ) : (
                <>
                  <p className={styles.lead}>
                    First at age {same.differing[0].age}. It differs in <strong>{same.differing.length}</strong> of{" "}
                    {same.compared} years: {agesList(same.differing.map((d) => d.age))}.
                    {beforeDropYears.length > 0 && (
                      <>
                        {" "}
                        Before the drop ({agesList(beforeDropYears.map((d) => d.age))}): {beforeDropReason(otherChanges)}.
                      </>
                    )}
                    {shock && afterDrop.length === 0 && (
                      <> From the year of the drop on, its chosen action is the same as before the what-if in every year.</>
                    )}
                  </p>
                  {/* The action in each of those years sits behind a fold, so the panel is the same height whatever the count. */}
                  <Disclosure
                    title="The action in each of those years"
                    aside={`${same.differing.length} ${same.differing.length === 1 ? "year" : "years"}`}
                    className={styles.fold}
                  >
                    <ul
                      className={styles.years}
                      tabIndex={0}
                      aria-label="Years where the planner's chosen action differs, with the action before and now"
                    >
                      {same.differing.map((d) => (
                        <li key={d.yearIndex}>
                          <span className={styles.yearAge}>Age {d.age}</span>
                          <span className={styles.yearLabels}>
                            <span>Before: {d.before}</span>
                            <span>Now: {d.after}</span>
                            {d.beforeShock && <span className={styles.yearNote}>{dropNote}</span>}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </Disclosure>
                </>
              )}
            </section>

            <section className={styles.part} aria-labelledby="whatchanged-rates">
              <h3 id="whatchanged-rates">How often the planner changes something</h3>
              <p className={styles.quiet}>
                The share of the {count(evalPaths)} simulated futures in which the planner changes anything from the fixed
                strategy in that year. Each future follows its own path, so this is not the table&apos;s one path.
              </p>
              <table className={styles.rates}>
                <caption className="sr-only">
                  Share of simulated futures in which the planner changes something, before the what-if and with it
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Years</th>
                    <th scope="col">Before the what-if</th>
                    <th scope="col">With the what-if</th>
                  </tr>
                </thead>
                <tbody>
                  {rates.map((row) => (
                    <tr key={row.id}>
                      <th scope="row">
                        {row.label}
                        {row.id === "before" && <span className={styles.rowNote}>{dropNote}</span>}
                      </th>
                      <td>{percentTrim(row.before)}</td>
                      <td>{percentTrim(row.after)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        )
      )}
    </Panel>
  );
}
