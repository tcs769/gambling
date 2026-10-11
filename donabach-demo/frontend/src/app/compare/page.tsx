"use client";

import { useState } from "react";
import { AdvantageBars } from "@/components/compare/AdvantageBars";
import styles from "@/components/compare/Compare.module.css";
import { FanCompare } from "@/components/compare/FanCompare";
import { SearchedTable } from "@/components/compare/SearchedTable";
import { StatGrid } from "@/components/compare/StatGrid";
import { Pending } from "@/components/plan/Pending";
import { useEnsure } from "@/components/plan/useEnsure";
import { PageHeader, Panel, PanelTitle, ResultsFooter } from "@/components/ui";
import { WhatIfDrawer } from "@/components/whatif/WhatIfDrawer";
import { WhatIfButton, WhatIfLayout } from "@/components/whatif/WhatIfLayout";
import { money, signedMoney } from "@/lib/format";
import { useApp } from "@/lib/state";

export default function ComparePage() {
  const { state, plan, basePlan, whatIfActive } = useApp();
  const { status, error, retry } = useEnsure("plan");
  const [whatIfOpen, setWhatIfOpen] = useState(false);

  const header = (
    <PageHeader
      title="Comparison"
      subtitle={
        plan
          ? `Your plan against a good traditional advisor, on the same ${plan.settings.n_paths} simulated futures.`
          : "Your plan against a good traditional advisor."
      }
      actions={plan && <WhatIfButton open={whatIfOpen} onClick={() => setWhatIfOpen((open) => !open)} />}
    />
  );

  if (status !== "ready" || !plan) {
    return (
      <>
        {header}
        <Pending status={status} error={error} retry={retry} label="Comparing with a typical advisor..." blocks={[226, 556, 582, 826]} />
        <ResultsFooter />
      </>
    );
  }

  const stats = plan.stats;
  return (
    <>
      {header}
      <WhatIfLayout
        open={whatIfOpen}
        stale={state.loading.whatIf}
        panel={<WhatIfDrawer onClose={() => setWhatIfOpen(false)} />}
      >
        <div className={styles.stack}>
          <StatGrid plan={plan} base={whatIfActive ? basePlan : undefined} />

          <Panel>
            <PanelTitle aside="After-tax wealth, in 2026 dollars">Both strategies over time</PanelTitle>
            <FanCompare plan={plan} />
          </Panel>

          <Panel>
            <PanelTitle>Where the advantage comes from</PanelTitle>
            <p className={styles.sectionNote}>
              Start from a good traditional advisor and switch on Donabach&apos;s decisions one at a time. Each bar is the
              change in typical wealth at 70 from that decision.
            </p>
            <AdvantageBars steps={plan.advantage} />
            <p className={styles.total}>
              <strong>Total: {signedMoney(stats.advantage_total)}</strong> in typical wealth at 70 compared with a typical
              advisor, about {signedMoney(stats.advantage_per_year)} a year over {stats.years} years (
              {money(stats.typical_outcome.median)} against {money(stats.ria_typical_outcome.median)}).
            </p>
          </Panel>

          <SearchedTable plan={plan} />
        </div>
      </WhatIfLayout>
      <ResultsFooter />
    </>
  );
}
