"use client";

import { useState } from "react";
import { FlowNav } from "@/components/showcase/FlowNav";
import { ScenarioChanges } from "@/components/showcase/ScenarioChanges";
import { ScenarioHeadline } from "@/components/showcase/ScenarioHeadline";
import { NO_CHANGE, ScenarioPicker } from "@/components/showcase/ScenarioPicker";
import { ScenarioYears } from "@/components/showcase/ScenarioYears";
import { ShowcasePending } from "@/components/showcase/ShowcasePending";
import { WealthFigure } from "@/components/showcase/WealthFigure";
import styles from "@/components/showcase/Scenario.module.css";
import { Button, Icon, PageHeader, Panel, PanelTitle, ResultsFooter, Spinner } from "@/components/ui";
import { useShowcase } from "@/lib/showcase";

/** A failure in the results area, in the API's words, with a retry. */
function Failure({ title, message, retry }: { title: string; message: string; retry: () => void }) {
  return (
    <div className={styles.error} role="alert">
      <Icon name="alert" size={20} className={styles.errorIcon} />
      <div className={styles.errorText}>
        <strong>{title}</strong> {message}
      </div>
      <Button variant="secondary" onClick={retry}>
        Try again
      </Button>
    </div>
  );
}

/**
 * Screen 5: what if the household changes. Pick an event (no change, a job loss next year, the market dropping 30%) and the
 * plan is shown again for the household after it: the headline against the advisor, what Donabach changes, the years that
 * changed and the wealth over time. Everything comes from the API; both events were asked for when the flow opened, so
 * choosing one is usually instant, and a loading state or an error (with a retry) is shown in the results area only.
 */
export default function ShowcaseWhatIfPage() {
  const { status, data, scenarios, scenariosError, scenarioStates, actions } = useShowcase();
  const [choice, setChoice] = useState(NO_CHANGE);

  if (status !== "ready" || !data) {
    return (
      <>
        <PageHeader title="What if things change?" />
        <ShowcasePending blocks={[120, 380, 560]} label="Loading the household…" />
      </>
    );
  }

  const advisor = data.wealth.advisor_label.toLowerCase();
  const chosen = choice === NO_CHANGE ? null : (scenarios?.find((s) => s.key === choice) ?? null);
  const state = chosen ? scenarioStates[chosen.key] : undefined;
  const scenario = state?.status === "ready" ? state.scenario : null;
  const busy = !!chosen && !scenario && state?.status !== "failed";

  return (
    <>
      <PageHeader
        title="What if things change?"
        subtitle={
          <span className={styles.tagline}>
            Donabach searches its strategies across simulated futures again for the changed household, so the plan
            adapts. Pick an event.
          </span>
        }
      />

      <div className={styles.stack}>
        {scenarios ? (
          <ScenarioPicker scenarios={scenarios} value={choice} onChange={setChoice} />
        ) : scenariosError ? (
          <Failure
            title="The events could not be loaded."
            message={scenariosError}
            retry={() => actions.retryScenario("")}
          />
        ) : (
          <Panel aria-busy="true">
            <Spinner label="Loading the events…" />
          </Panel>
        )}

        <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {scenario
            ? `Showing the household after: ${scenario.label}.`
            : chosen
              ? ""
              : "Showing the household as it is."}
        </p>

        <div className={styles.results} aria-busy={busy}>
          {chosen && state?.status === "failed" && (
            <Failure
              title={`${chosen.label} could not be loaded.`}
              message={state.error}
              retry={() => actions.retryScenario(chosen.key)}
            />
          )}

          {busy && (
            <Panel aria-busy="true" className={styles.loading}>
              <Spinner label={`Working out: ${chosen.label}…`} />
            </Panel>
          )}

          {chosen === null && (
            <>
              <ScenarioHeadline wealth={data.wealth} before={null} />
              <Panel aria-labelledby="whatif-wealth-title">
                <PanelTitle id="whatif-wealth-title" aside={data.wealth.liquidated_label}>
                  Donabach and a {advisor} over time
                </PanelTitle>
                <WealthFigure wealth={data.wealth} />
              </Panel>
            </>
          )}

          {scenario && (
            <>
              <p className={styles.event} data-testid="event">
                <Icon name="info" size={18} className={styles.eventIcon} />
                <span>{scenario.event}</span>
              </p>

              <ScenarioHeadline wealth={scenario.wealth} before={data.wealth} />

              <Panel aria-labelledby="whatif-changes-title">
                <PanelTitle id="whatif-changes-title">What Donabach changes</PanelTitle>
                <ScenarioChanges scenario={scenario} />
              </Panel>

              <Panel aria-labelledby="whatif-years-title">
                <PanelTitle id="whatif-years-title">Year by year</PanelTitle>
                <ScenarioYears key={scenario.key} years={scenario.years} eventLabel={scenario.label} />
              </Panel>

              <Panel aria-labelledby="whatif-wealth-title">
                <PanelTitle id="whatif-wealth-title" aside={scenario.wealth.liquidated_label}>
                  Donabach and a {advisor} after the event
                </PanelTitle>
                <WealthFigure wealth={scenario.wealth} />
              </Panel>
            </>
          )}
        </div>
      </div>

      <FlowNav
        back={{ href: "/showcase/wealth", label: "Back to wealth over time" }}
        next={{ href: "/", label: "Explore the full demo" }}
      />
      <ResultsFooter note={data.footer_note} />
    </>
  );
}
