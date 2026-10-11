"use client";

import { DriversPanel } from "@/components/forecast/DriversPanel";
import { ForecastChart } from "@/components/forecast/ForecastChart";
import styles from "@/components/forecast/Forecast.module.css";
import { Pending } from "@/components/plan/Pending";
import { useEnsure } from "@/components/plan/useEnsure";
import { ButtonLink, Icon, ModelNotConnected, PageHeader, Panel, PanelTitle, Pill, ResultsFooter } from "@/components/ui";
import { money } from "@/lib/format";
import { useApp } from "@/lib/state";
import type { ForecastResponse } from "@/lib/types";

/** One computed sentence: where median income starts and where it ends up before retirement. */
function summarize(forecast: ForecastResponse, retirementAge: number | undefined): string {
  const { ages, p10, p50, p90 } = forecast.forecast;
  const n = ages.length;
  if (n < 2) return "";
  const beforeRetirement = retirementAge !== undefined && ages[n - 1] === retirementAge - 1;
  const end = beforeRetirement ? `${ages[n - 1]}, the year before retirement at ${retirementAge}` : `${ages[n - 1]}`;
  return (
    `Median household income starts at ${money(p50[0])} a year at age ${ages[0]} and reaches ${money(p50[n - 1])} at ${end}. ` +
    `By then, 8 in 10 simulated futures fall between ${money(p10[n - 1])} and ${money(p90[n - 1])}.`
  );
}

export default function ForecastPage() {
  const { state, household } = useApp();
  const { status, error, retry } = useEnsure("forecast");
  const forecast = state.forecast;

  if (status !== "ready" || !forecast) {
    return (
      <>
        <PageHeader title="Income forecast" subtitle="Where household income could go between now and retirement." />
        <Pending status={status} error={error} retry={retry} label="Building the income forecast..." blocks={[115, 605]} tail={43} />
        <ResultsFooter />
      </>
    );
  }

  // The placeholder's note opens with "Model not connected."; the callout's own title says that.
  const noteTail = forecast.note.replace(/^Model not connected\.\s*/i, "");
  const factors = forecast.top_factors?.length ? forecast.top_factors : (forecast.forecast.top_factors ?? []);

  return (
    <>
      <PageHeader title="Income forecast" subtitle="Where household income could go between now and retirement." />
      <div className={styles.stack}>
        {!forecast.connected && (
          <ModelNotConnected model="forecaster" reason={forecast.reason}>
            <strong>Placeholder forecast.</strong> {noteTail}
          </ModelNotConnected>
        )}

        <Panel>
          <PanelTitle
            aside={
              forecast.connected ? (
                <Pill tone="gold" icon={<Icon name="check" size={14} strokeWidth={2.6} />}>
                  {forecast.label}
                </Pill>
              ) : (
                <Pill icon={<Icon name="plug" size={14} />}>{forecast.label}</Pill>
              )
            }
          >
            Household income by age
          </PanelTitle>
          <p className={styles.summary}>{summarize(forecast, household?.goals?.retirement_age)}</p>
          <ForecastChart forecast={forecast.forecast} />
        </Panel>

        {forecast.connected && <DriversPanel factors={factors} />}

        <div className={styles.next}>
          <ButtonLink href="/plan" arrow>
            See your recommended plan
          </ButtonLink>
        </div>
      </div>
      <ResultsFooter />
    </>
  );
}
