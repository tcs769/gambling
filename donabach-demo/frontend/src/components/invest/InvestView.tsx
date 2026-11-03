"use client";

import { useCallback, useEffect, useState } from "react";
import type { Plan } from "@/lib/portal-types";
import { GoalsTab } from "./GoalsTab";
import { HoldingsTab } from "./Holdings";
import { Overview } from "./Overview";
import { RetirementTab } from "./Retirement";
import { SummaryStrip } from "./SummaryStrip";
import { TaxesTab } from "./Taxes";
import { TabList, TabPanel } from "./Tabs";
import { WhatChanged } from "./WhatChanged";
import styles from "./InvestView.module.css";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "holdings", label: "Holdings" },
  { key: "taxes", label: "Taxes" },
  { key: "retirement", label: "Retirement income" },
  { key: "goals", label: "Goals" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

const isTab = (value: string): value is TabKey => TABS.some((t) => t.key === value);

/** The Invest page: the heading row with the five tabs, what changed, the summary strip, and the selected tab (kept in the URL hash). */
export function InvestView({ plan }: { plan: Plan }) {
  const [tab, setTab] = useState<TabKey>("overview");

  useEffect(() => {
    const read = () => {
      const hash = window.location.hash.replace(/^#/, "");
      setTab(isTab(hash) ? hash : "overview");
    };
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, []);

  const select = useCallback((key: TabKey) => {
    setTab(key);
    window.history.replaceState(null, "", key === "overview" ? window.location.pathname : `#${key}`);
  }, []);

  const { portfolio } = plan;
  return (
    <div data-plan-id={plan.plan_id}>
      <div className={styles.planhead}>
        <h1>Invest</h1>
        <TabList label="Invest sections" idPrefix="invest" tabs={[...TABS]} value={tab} onChange={select} />
      </div>
      {plan.what_changed && <WhatChanged change={plan.what_changed} horizon={portfolio.summary.horizon_age} />}
      <SummaryStrip summary={portfolio.summary} />
      <TabPanel idPrefix="invest" value={tab}>
        {tab === "overview" && <Overview plan={plan} />}
        {tab === "holdings" && <HoldingsTab holdings={portfolio.holdings} />}
        {tab === "taxes" && <TaxesTab taxes={portfolio.taxes} />}
        {tab === "retirement" && <RetirementTab retirement={portfolio.retirement} />}
        {tab === "goals" && <GoalsTab goals={portfolio.goals} />}
      </TabPanel>
    </div>
  );
}
