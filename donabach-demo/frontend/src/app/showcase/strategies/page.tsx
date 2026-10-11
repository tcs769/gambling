"use client";

import { ChangeError } from "@/components/showcase/ChangeError";
import { FlowNav } from "@/components/showcase/FlowNav";
import { ShowcasePending } from "@/components/showcase/ShowcasePending";
import { TotalPanel } from "@/components/showcase/TotalPanel";
import { Waterfall } from "@/components/showcase/Waterfall";
import { ratePercent, dollarsText } from "@/components/showcase/waterfall";
import styles from "@/components/showcase/Showcase.module.css";
import { Disclosure, PageHeader, Panel, PanelTitle, ResultsFooter } from "@/components/ui";
import { count } from "@/lib/format";
import { useShowcase } from "@/lib/showcase";

/** Screen 2: where Donabach's advantage over the advisor comes from, strategy by strategy, with a switch on each. */
export default function ShowcaseStrategiesPage() {
  const { status, data, analysis, enabled, computing, actions } = useShowcase();

  if (status !== "ready" || !data || !analysis) {
    return (
      <>
        <PageHeader title="Where the advantage comes from" />
        <ShowcasePending blocks={[150, 640]} label="Loading the strategies…" />
      </>
    );
  }

  const horizon = analysis.horizon_age;
  const total = analysis.bars.length;
  const on = analysis.bars.filter((bar) => bar.enabled).length;
  // Said aloud when the numbers change: that something is being worked out, then what the total came to.
  const announcement = computing
    ? "Recomputing the waterfall."
    : `Recomputed with ${on} of ${total} strategies on. Total advantage ${ratePercent(analysis.advantage.median_rate)} a year, ${dollarsText(
        analysis.advantage.median_dollars,
        horizon,
      )}, median of ${count(analysis.n_paths)} simulated futures.`;

  return (
    <>
      <PageHeader
        title="Where the advantage comes from"
        subtitle={
          <span className={styles.tagline}>
            Start from a {analysis.advisor_label.toLowerCase()}&apos;s plan and switch Donabach&apos;s strategies on one
            at a time. Each bar is what that strategy adds to median after-tax wealth at {horizon}, measured on the same{" "}
            {count(analysis.n_paths)} simulated futures.
          </span>
        }
      />

      <div className={styles.stack}>
        <ChangeError />
        <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {announcement}
        </p>

        <TotalPanel analysis={analysis} computing={computing} />

        <Panel aria-labelledby="waterfall-title">
          <PanelTitle id="waterfall-title">Strategy by strategy</PanelTitle>
          {total === 0 ? (
            <p className={styles.note}>
              For this household Donabach&apos;s plan is the {analysis.advisor_label.toLowerCase()}&apos;s own: no
              strategy differs, so there is nothing to switch on or off.
            </p>
          ) : (
            <>
              <p className={styles.note}>
                Switch any strategy off to see what it is worth. The bars are measured in order, each on top of the ones
                before it, so switching one off also changes the bars of the strategies that depend on it.
              </p>
              <Waterfall
                analysis={analysis}
                full={data.analysis}
                enabled={enabled}
                computing={computing}
                onToggle={actions.toggle}
                onAllOn={() => actions.setAll(true)}
              />
              <div className={styles.plan}>
                <Disclosure title="The whole plan, in words">
                  <p className={styles.planLabel}>{analysis.plan_label}</p>
                  <p className={styles.planText}>{analysis.plan_sentence}</p>
                </Disclosure>
              </div>
            </>
          )}
        </Panel>
      </div>

      <FlowNav
        back={{ href: "/showcase", label: "Back to the household" }}
        next={{ href: "/showcase/wealth", label: "See wealth over time" }}
      />
      <ResultsFooter />
    </>
  );
}
