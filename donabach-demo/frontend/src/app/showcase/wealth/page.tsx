"use client";

import { BadMarket } from "@/components/showcase/BadMarket";
import { FlowNav } from "@/components/showcase/FlowNav";
import { ShowcasePending } from "@/components/showcase/ShowcasePending";
import { WealthFigure } from "@/components/showcase/WealthFigure";
import { WealthHeadline } from "@/components/showcase/WealthHeadline";
import { WealthHeirs } from "@/components/showcase/WealthHeirs";
import styles from "@/components/showcase/Showcase.module.css";
import { PageHeader, Panel, PanelTitle, ResultsFooter } from "@/components/ui";
import { count } from "@/lib/format";
import { useShowcase } from "@/lib/showcase";

/**
 * Screen 3: after-tax wealth over time against the advisor, for the whole plan (every strategy on). It reads the household
 * answer's `wealth`, which the API worked out once, and never asks for anything: switching strategies off on the
 * second screen changes the waterfall there and nothing here.
 */
export default function ShowcaseWealthPage() {
  const { status, data } = useShowcase();

  if (status !== "ready" || !data) {
    return (
      <>
        <PageHeader title="Wealth over time" />
        <ShowcasePending blocks={[190, 560, 190]} label="Loading wealth over time…" />
      </>
    );
  }

  const { wealth } = data;
  const advisor = wealth.advisor_label.toLowerCase();

  return (
    <>
      <PageHeader
        title="Wealth over time"
        subtitle={
          <span className={styles.tagline}>
            The whole plan, with every strategy on. After-tax wealth by age, in 2026 dollars, for Donabach and a{" "}
            {advisor}, on the same {count(wealth.n_paths)} simulated futures.
          </span>
        }
      />

      <div className={styles.stack}>
        <WealthHeadline wealth={wealth} />

        <WealthHeirs wealth={wealth} />

        <Panel aria-labelledby="wealth-title">
          <PanelTitle id="wealth-title" aside={wealth.liquidated_label}>
            Donabach and a {advisor} over time
          </PanelTitle>
          <WealthFigure wealth={wealth} />
        </Panel>

        <BadMarket wealth={wealth} />
      </div>

      <FlowNav
        back={{ href: "/showcase/strategies", label: "Back to the strategies" }}
        next={{ href: "/", label: "Explore the full demo" }}
      />
      <ResultsFooter note={data.footer_note} />
    </>
  );
}
