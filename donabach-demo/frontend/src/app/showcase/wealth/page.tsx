"use client";

import { useEffect, useRef, useState } from "react";
import { AdvisorHeadline } from "@/components/showcase/AdvisorHeadline";
import { BadMarket } from "@/components/showcase/BadMarket";
import { FlowNav } from "@/components/showcase/FlowNav";
import { ShowcasePending } from "@/components/showcase/ShowcasePending";
import { WealthFigure } from "@/components/showcase/WealthFigure";
import { WealthHeadline, moreOrLess } from "@/components/showcase/WealthHeadline";
import { WealthHeirs } from "@/components/showcase/WealthHeirs";
import { ratePercent } from "@/components/showcase/waterfall";
import styles from "@/components/showcase/Showcase.module.css";
import { Button, PageHeader, Panel, PanelTitle, ResultsFooter } from "@/components/ui";
import { count } from "@/lib/format";
import { useShowcase } from "@/lib/showcase";

/**
 * Screens 2 and 4: after-tax wealth over time, for the whole plan (every strategy on). It reads the household answer's
 * `wealth`, which the API worked out once, and never asks for anything: switching strategies off on the strategies screen
 * changes the waterfall there and nothing here.
 *
 * It starts with the advisor alone (what a good advisor gets this household), and Donabach is not in the page at all until
 * it is shown: the button reveals it, and so does moving on to the strategies from here. Once shown it stays shown for the
 * session (the provider holds it), so the second visit has both.
 */
export default function ShowcaseWealthPage() {
  const { status, data, revealed, actions } = useShowcase();
  const headline = useRef<HTMLElement>(null);
  // Was Donabach revealed on this screen (rather than already shown when it opened)? Then focus moves to the headline and the
  // change is announced.
  const [pressed, setPressed] = useState(false);
  useEffect(() => {
    if (pressed && revealed) headline.current?.focus();
  }, [pressed, revealed]);

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
  const { advantage, horizon_age: horizon } = wealth;
  const show = () => {
    setPressed(true);
    actions.reveal();
  };

  return (
    <>
      <PageHeader
        title="Wealth over time"
        subtitle={
          <span className={styles.tagline}>
            {revealed ? (
              <>
                The whole plan, with every strategy on. After-tax wealth by age, in 2026 dollars, for Donabach and a{" "}
                {advisor}, on the same {count(wealth.n_paths)} simulated futures.
              </>
            ) : (
              <>
                What a {advisor} gets this household: after-tax wealth by age, in 2026 dollars, on{" "}
                {count(wealth.n_paths)} simulated futures.
              </>
            )}
          </span>
        }
      />

      {/* The slots are the same before and after Donabach is shown, so the live region and the figure carry on (the chart's
          advisor lines stay where they are and Donabach's lines draw in beside them). */}
      <div className={styles.stack}>
        <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {pressed && revealed
            ? `Donabach is now shown. Median advantage ${ratePercent(advantage.median_rate)} a year, ${moreOrLess(advantage.median_dollars, horizon)}.`
            : ""}
        </p>

        {revealed ? <WealthHeadline wealth={wealth} focusRef={headline} /> : <AdvisorHeadline wealth={wealth} />}

        {revealed ? (
          <WealthHeirs wealth={wealth} />
        ) : (
          <div className={styles.reveal}>
            <Button onClick={show} arrow data-testid="reveal">
              Show what Donabach does
            </Button>
          </div>
        )}

        <Panel aria-labelledby="wealth-title">
          <PanelTitle id="wealth-title" aside={wealth.liquidated_label}>
            {revealed ? `Donabach and a ${advisor} over time` : `A ${advisor} over time`}
          </PanelTitle>
          <WealthFigure wealth={wealth} advisorOnly={!revealed} />
        </Panel>

        {revealed && <BadMarket wealth={wealth} />}
      </div>

      {revealed ? (
        <FlowNav
          back={{ href: "/showcase/strategies", label: "Back to the strategies" }}
          next={{ href: "/showcase/whatif", label: "Change the household" }}
        />
      ) : (
        <FlowNav
          back={{ href: "/showcase", label: "Back to the household" }}
          next={{ href: "/showcase/strategies", label: "See what Donabach does" }}
        />
      )}
      <ResultsFooter note={data.footer_note} />
    </>
  );
}
