"use client";

import { useState } from "react";
import { Pending } from "@/components/plan/Pending";
import styles from "@/components/plan/Plan.module.css";
import { RecommenderPanel } from "@/components/plan/RecommenderPanel";
import { StrategyCard } from "@/components/plan/StrategyCard";
import { useEnsure } from "@/components/plan/useEnsure";
import { YearDrawer } from "@/components/plan/YearDrawer";
import { YearTable } from "@/components/plan/YearTable";
import { ButtonLink, PageHeader, ResultsFooter } from "@/components/ui";
import { WhatIfDrawer } from "@/components/whatif/WhatIfDrawer";
import { WhatIfButton, WhatIfLayout } from "@/components/whatif/WhatIfLayout";
import { useApp } from "@/lib/state";

export default function PlanPage() {
  const { state, plan, household } = useApp();
  const { status, error, retry } = useEnsure("plan");
  // The year drawer overlays the page and the what-if panel docks beside it: one at a time.
  const [selected, setSelected] = useState<number | null>(null);
  const [whatIfOpen, setWhatIfOpen] = useState(false);

  const header = (
    <PageHeader
      title="Recommended plan"
      subtitle="How Donabach would invest, convert and spend for your household, year by year."
      actions={
        plan && (
          <WhatIfButton
            open={whatIfOpen}
            onClick={() => {
              setSelected(null);
              setWhatIfOpen((open) => !open);
            }}
          />
        )
      }
    />
  );

  if (status !== "ready" || !plan || !household) {
    return (
      <>
        {header}
        <Pending status={status} error={error} retry={retry} label="Building your plan..." blocks={[307, 230, 595]} tail={43} />
        <ResultsFooter />
      </>
    );
  }

  return (
    <>
      {header}
      <WhatIfLayout
        open={whatIfOpen}
        stale={state.loading.whatIf}
        panel={<WhatIfDrawer onClose={() => setWhatIfOpen(false)} />}
      >
        <div className={styles.stack}>
          <StrategyCard plan={plan} />
          <RecommenderPanel plan={plan} />
          <YearTable
            rows={plan.rows}
            retirementAge={household.goals?.retirement_age}
            selected={selected}
            onSelect={(yearIndex) => {
              setWhatIfOpen(false);
              setSelected(yearIndex);
            }}
          />
          <div className={styles.next}>
            <ButtonLink href="/compare" arrow>
              Compare with a typical advisor
            </ButtonLink>
          </div>
        </div>
      </WhatIfLayout>
      <ResultsFooter />
      <YearDrawer plan={plan} household={household} selected={selected} onSelect={setSelected} />
    </>
  );
}
