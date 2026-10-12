"use client";

import { useEffect, useState } from "react";
import { Pending } from "@/components/plan/Pending";
import styles from "@/components/plan/Plan.module.css";
import { PlanStyleSwitch } from "@/components/plan/PlanStyleSwitch";
import { RecommenderPanel } from "@/components/plan/RecommenderPanel";
import { RefiningPill } from "@/components/plan/Refining";
import { StrategyCard } from "@/components/plan/StrategyCard";
import { StyleComparison } from "@/components/plan/StyleComparison";
import { StylePending } from "@/components/plan/StylePending";
import { StyleResults } from "@/components/plan/StyleResults";
import { STYLE_NAME } from "@/components/plan/styles";
import { useEnsure } from "@/components/plan/useEnsure";
import { YearDrawer } from "@/components/plan/YearDrawer";
import { YearTable, type PlanView } from "@/components/plan/YearTable";
import { ButtonLink, PageHeader, Panel, ResultsFooter } from "@/components/ui";
import { WhatChangedPanel } from "@/components/whatif/WhatChangedPanel";
import { WhatIfDrawer } from "@/components/whatif/WhatIfDrawer";
import { WhatIfButton, WhatIfLayout } from "@/components/whatif/WhatIfLayout";
import {
  ALT_STYLES,
  adaptiveSection,
  useApp,
  type AdaptiveState,
  type AltStyle,
  type PlanStyleView,
  type StyleSlot,
} from "@/lib/state";

/** A plan in another planning style is asked for without the year-by-year job: only the equity-first plan has one. */
const NO_YEAR_BY_YEAR: AdaptiveState = { status: "unavailable" };
const NO_YEAR_BY_YEAR_NOTE =
  "The year-by-year planner runs for the equity-first plan only, so this is the fixed strategy.";
const ASKED: StyleSlot = { status: "loading" };

const noop = () => undefined;

export default function PlanPage() {
  const { state, actions, plan, household, adaptive, styleSlots } = useApp();
  const { status, error, retry } = useEnsure("plan");
  // The year drawer overlays the page and the what-if panel docks beside it: one at a time.
  const [selected, setSelected] = useState<number | null>(null);
  const [whatIfOpen, setWhatIfOpen] = useState(false);
  // What the viewer picked in the switch; until they pick, the year-by-year plan is shown as soon as there is one.
  const [picked, setPicked] = useState<PlanView | null>(null);
  const style = state.planStyle;
  const section = adaptiveSection(adaptive);
  const view: PlanView = section && picked !== "fixed" ? "adaptive" : "fixed";

  // The plans in the other styles that the switch is on are asked for (the store keeps them, so each is asked for once).
  useEffect(() => {
    if (!plan) return;
    for (const other of ALT_STYLES) if (style === other || style === "all") void actions.ensureStylePlan(other);
  }, [plan, style, actions]);

  const chooseStyle = (next: PlanStyleView) => {
    setSelected(null);
    actions.setPlanStyle(next);
  };
  const askAgain = (other: AltStyle) => void actions.ensureStylePlan(other, { retry: true });

  const header = (
    <PageHeader
      title="Recommended plan"
      subtitle="How Donabach would invest, convert and spend for your household, year by year."
      status={plan && style === "equity_first" && <RefiningPill adaptive={adaptive} />}
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
        <Pending
          status={status}
          error={error}
          retry={retry}
          label="Building your plan..."
          blocks={[382, 230, 640]}
          tail={43}
        />
        <ResultsFooter />
      </>
    );
  }

  // One style other than the default one: its plan, once it is here.
  const other = style === "balanced" || style === "liability_matched" ? style : null;
  const slot = other ? (styleSlots[other] ?? ASKED) : undefined;
  const otherPlan = slot?.status === "ready" ? slot.plan : undefined;
  const shown = otherPlan ?? plan;

  const yearTable = (rows: typeof plan.rows, forPlan: typeof plan) => (
    <YearTable
      rows={rows}
      view={other ? "fixed" : view}
      onView={other ? noop : setPicked}
      adaptive={other ? NO_YEAR_BY_YEAR : adaptive}
      unavailableNote={other ? NO_YEAR_BY_YEAR_NOTE : undefined}
      horizon={forPlan.settings.horizon_age}
      retirementAge={household.goals?.retirement_age}
      shock={forPlan.settings.market_shock}
      selected={selected}
      onSelect={(yearIndex) => {
        setWhatIfOpen(false);
        setSelected(yearIndex);
      }}
    />
  );

  return (
    <>
      {header}
      <WhatIfLayout
        open={whatIfOpen}
        stale={state.loading.whatIf}
        panel={<WhatIfDrawer onClose={() => setWhatIfOpen(false)} />}
      >
        <div className={styles.stack}>
          <PlanStyleSwitch value={style} onChange={chooseStyle} />

          {style === "equity_first" && (
            <>
              <StrategyCard plan={plan} />
              <WhatChangedPanel />
              <RecommenderPanel plan={plan} />
              {yearTable(view === "adaptive" && section ? section.rows : plan.rows, plan)}
            </>
          )}

          {style === "all" && <StyleComparison plan={plan} slots={styleSlots} onRetry={askAgain} />}

          {/* Said aloud when the plan arrives (the spinner in its place says that it is on its way). */}
          {other && (
            <p className="sr-only" role="status">
              {otherPlan ? `The ${STYLE_NAME[other].toLowerCase()} plan is ready.` : ""}
            </p>
          )}

          {other && slot && !otherPlan && (
            <Panel aria-busy={slot.status === "loading" || undefined}>
              {slot.status !== "ready" && <StylePending style={other} slot={slot} onRetry={() => askAgain(other)} />}
            </Panel>
          )}

          {other && otherPlan && (
            <>
              <StrategyCard plan={otherPlan} />
              <StyleResults plan={otherPlan} name={STYLE_NAME[other]} />
              {/* The liability-matched search does not consult the recommender model, and says so: nothing to show for it. */}
              {other === "balanced" && <RecommenderPanel plan={otherPlan} />}
              {yearTable(otherPlan.rows, otherPlan)}
            </>
          )}

          <div className={styles.next}>
            {style !== "equity_first" && (
              <p className={styles.nextNote}>
                The Comparison screen compares the equity-first plan with the two advisors.
              </p>
            )}
            <ButtonLink href="/compare" arrow>
              Compare with two advisors
            </ButtonLink>
          </div>
        </div>
      </WhatIfLayout>
      <ResultsFooter />
      <YearDrawer
        plan={shown}
        household={household}
        adaptive={!other && style === "equity_first" && view === "adaptive" ? section : undefined}
        selected={style === "all" ? null : selected}
        onSelect={setSelected}
      />
    </>
  );
}
