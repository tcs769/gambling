"use client";

import { useState } from "react";
import { AdaptivePlaceholder } from "@/components/compare/AdaptivePlaceholder";
import { AdvantageBars } from "@/components/compare/AdvantageBars";
import { AdvantagePanel } from "@/components/compare/AdvantagePanel";
import { BaselinesPanel } from "@/components/compare/BaselinesPanel";
import styles from "@/components/compare/Compare.module.css";
import { FanCompare } from "@/components/compare/FanCompare";
import { FourWayPanel } from "@/components/compare/FourWayPanel";
import { HowWeMeasure } from "@/components/compare/HowWeMeasure";
import { JudgmentPanel } from "@/components/compare/JudgmentPanel";
import { SearchedTable } from "@/components/compare/SearchedTable";
import { Pending } from "@/components/plan/Pending";
import { RefiningPill } from "@/components/plan/Refining";
import { useEnsure } from "@/components/plan/useEnsure";
import { PageHeader, Panel, PanelTitle, ResultsFooter } from "@/components/ui";
import { WhatChangedPanel } from "@/components/whatif/WhatChangedPanel";
import { WhatIfDrawer } from "@/components/whatif/WhatIfDrawer";
import { WhatIfButton, WhatIfLayout } from "@/components/whatif/WhatIfLayout";
import { count, money, signedMoney } from "@/lib/format";
import { adaptiveSection, useApp } from "@/lib/state";

export default function ComparePage() {
  const { state, plan, basePlan, adaptive, whatIfActive } = useApp();
  const { status, error, retry } = useEnsure("plan");
  const [whatIfOpen, setWhatIfOpen] = useState(false);

  const header = (
    <PageHeader
      title="Comparison"
      subtitle={
        plan
          ? `Your plan against a good RIA and a typical advisor, on the same ${count(plan.settings.n_eval_paths)} fresh simulated futures.`
          : "Your plan against a good RIA and a typical advisor."
      }
      status={plan && <RefiningPill adaptive={adaptive} />}
      actions={plan && <WhatIfButton open={whatIfOpen} onClick={() => setWhatIfOpen((open) => !open)} />}
    />
  );

  if (status !== "ready" || !plan) {
    return (
      <>
        {header}
        <Pending
          status={status}
          error={error}
          retry={retry}
          label="Comparing with a good RIA and a typical advisor..."
          blocks={[678, 662, 613, 607, 250, 913]}
        />
        <ResultsFooter />
      </>
    );
  }

  const stats = plan.stats;
  const horizon = plan.settings.horizon_age;
  const base = whatIfActive ? basePlan : undefined;
  const section = adaptiveSection(adaptive);
  return (
    <>
      {header}
      <WhatIfLayout
        open={whatIfOpen}
        stale={state.loading.whatIf}
        panel={<WhatIfDrawer onClose={() => setWhatIfOpen(false)} />}
      >
        <div className={styles.stack}>
          <WhatChangedPanel />

          <AdvantagePanel plan={plan} base={base} />

          <BaselinesPanel plan={plan} base={base} />

          <Panel>
            <PanelTitle aside="After-tax wealth, in 2026 dollars">Donabach and both advisors over time</PanelTitle>
            <FanCompare plan={plan} adaptive={adaptive} />
          </Panel>

          {section ? (
            <>
              <FourWayPanel plan={plan} section={section} />
              <JudgmentPanel plan={plan} section={section} />
            </>
          ) : (
            <AdaptivePlaceholder adaptive={adaptive} />
          )}

          <Panel>
            <PanelTitle>Where the advantage comes from</PanelTitle>
            <p className={styles.sectionNote}>
              Start from the good RIA and switch on Donabach&apos;s decisions one at a time. Each bar is the change in
              typical wealth at {horizon} from that decision.
            </p>
            <AdvantageBars steps={plan.advantage} horizon={horizon} />
            <p className={styles.total}>
              <strong>Total: {signedMoney(stats.advantage_total)}</strong> in typical wealth at {horizon} compared with a good
              RIA ({money(stats.typical_outcome.median)} against {money(stats.ria_typical_outcome.median)}). It is the
              same dollar gap as the median advantage above.
            </p>
          </Panel>

          <HowWeMeasure plan={plan} />

          <SearchedTable plan={plan} />
        </div>
      </WhatIfLayout>
      <ResultsFooter />
    </>
  );
}
