"use client";

import { useState } from "react";
import { Pending } from "@/components/plan/Pending";
import styles from "@/components/plan/Plan.module.css";
import { RecommenderPanel } from "@/components/plan/RecommenderPanel";
import { RefiningPill } from "@/components/plan/Refining";
import { StrategyCard } from "@/components/plan/StrategyCard";
import { useEnsure } from "@/components/plan/useEnsure";
import { YearDrawer } from "@/components/plan/YearDrawer";
import { YearTable, type PlanView } from "@/components/plan/YearTable";
import { ButtonLink, PageHeader, ResultsFooter } from "@/components/ui";
import { WhatChangedPanel } from "@/components/whatif/WhatChangedPanel";
import { WhatIfDrawer } from "@/components/whatif/WhatIfDrawer";
import { WhatIfButton, WhatIfLayout } from "@/components/whatif/WhatIfLayout";
import { adaptiveSection, useApp } from "@/lib/state";

export default function PlanPage() {
  const { state, plan, household, adaptive } = useApp();
  const { status, error, retry } = useEnsure("plan");
  // The year drawer overlays the page and the what-if panel docks beside it: one at a time.
  const [selected, setSelected] = useState<number | null>(null);
  const [whatIfOpen, setWhatIfOpen] = useState(false);
  // What the viewer picked in the switch; until they pick, the year-by-year plan is shown as soon as there is one.
  const [picked, setPicked] = useState<PlanView | null>(null);
  const section = adaptiveSection(adaptive);
  const view: PlanView = section && picked !== "fixed" ? "adaptive" : "fixed";

  const header = (
    <PageHeader
      title="Recommended plan"
      subtitle="How Donabach would invest, convert and spend for your household, year by year."
      status={plan && <RefiningPill adaptive={adaptive} />}
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
        <Pending status={status} error={error} retry={retry} label="Building your plan..." blocks={[382, 230, 640]} tail={43} />
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
          <WhatChangedPanel />
          <RecommenderPanel plan={plan} />
          <YearTable
            rows={view === "adaptive" && section ? section.rows : plan.rows}
            view={view}
            onView={setPicked}
            adaptive={adaptive}
            horizon={plan.settings.horizon_age}
            retirementAge={household.goals?.retirement_age}
            shock={plan.settings.market_shock}
            selected={selected}
            onSelect={(yearIndex) => {
              setWhatIfOpen(false);
              setSelected(yearIndex);
            }}
          />
          <div className={styles.next}>
            <ButtonLink href="/compare" arrow>
              Compare with two advisors
            </ButtonLink>
          </div>
        </div>
      </WhatIfLayout>
      <ResultsFooter />
      <YearDrawer
        plan={plan}
        household={household}
        adaptive={view === "adaptive" ? section : undefined}
        selected={selected}
        onSelect={setSelected}
      />
    </>
  );
}
