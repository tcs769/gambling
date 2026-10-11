"use client";

import Link from "next/link";
import { BadMarket } from "@/components/showcase/BadMarket";
import { ChangeError } from "@/components/showcase/ChangeError";
import { FlowNav } from "@/components/showcase/FlowNav";
import { ShowcasePending } from "@/components/showcase/ShowcasePending";
import { WealthFigure } from "@/components/showcase/WealthFigure";
import { WealthHeadline } from "@/components/showcase/WealthHeadline";
import { listOf, strategies, strategiesOn } from "@/components/showcase/text";
import { dollarsText, ratePercent } from "@/components/showcase/waterfall";
import styles from "@/components/showcase/Showcase.module.css";
import { Icon, PageHeader, Panel, PanelTitle, ResultsFooter, Spinner } from "@/components/ui";
import { count } from "@/lib/format";
import { useShowcase } from "@/lib/showcase";

/** Screen 3: after-tax wealth over time against the advisor, for the strategies chosen on the second screen. */
export default function ShowcaseWealthPage() {
  const { status, analysis, computing } = useShowcase();

  if (status !== "ready" || !analysis) {
    return (
      <>
        <PageHeader title="Wealth over time" />
        <ShowcasePending blocks={[190, 560, 190]} label="Loading wealth over time…" />
      </>
    );
  }

  const horizon = analysis.horizon_age;
  const advisor = analysis.advisor_label.toLowerCase();
  const total = analysis.bars.length;
  const off = analysis.bars.filter((bar) => !bar.enabled);
  const announcement = computing
    ? "Recomputing wealth over time."
    : `Wealth over time, ${strategiesOn(total - off.length, total).toLowerCase()}. Median advantage ${ratePercent(
        analysis.advantage.median_rate,
      )} a year, ${dollarsText(analysis.advantage.median_dollars, horizon)}.`;

  return (
    <>
      <PageHeader
        title="Wealth over time"
        subtitle={
          <span className={styles.tagline}>
            After-tax wealth by age, in 2026 dollars, for Donabach and a {advisor}, on the same{" "}
            {count(analysis.n_paths)} simulated futures.
          </span>
        }
      />

      <div className={styles.stack}>
        <ChangeError />
        <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {announcement}
        </p>

        {total > 0 && (
          <div className={styles.state} data-off={off.length > 0}>
            <Icon name={off.length > 0 ? "sliders" : "check"} size={20} className={styles.stateIcon} />
            <p className={styles.stateText}>
              {off.length === 0 ? (
                <>All {strategies(total)} on.</>
              ) : (
                <>
                  <strong>With {strategies(off.length)} off</strong>: {listOf(off.map((bar) => bar.label))}.
                  {off.length === total && (
                    <>
                      {" "}
                      Donabach&apos;s plan is then the {advisor}&apos;s own, so each Donabach line lies on the matching{" "}
                      {advisor} line.
                    </>
                  )}
                </>
              )}
            </p>
            {computing && (
              <span className={styles.stateBusy} aria-hidden="true">
                <Spinner size={14} />
                Recomputing…
              </span>
            )}
            <Link href="/showcase/strategies" className={styles.stateLink}>
              Change the strategies
            </Link>
          </div>
        )}

        <WealthHeadline analysis={analysis} computing={computing} />

        <Panel aria-labelledby="wealth-title">
          <PanelTitle id="wealth-title">Donabach and a {advisor} over time</PanelTitle>
          <WealthFigure analysis={analysis} computing={computing} />
        </Panel>

        <BadMarket analysis={analysis} computing={computing} />
      </div>

      <FlowNav
        back={{ href: "/showcase/strategies", label: "Back to the strategies" }}
        next={{ href: "/", label: "Explore the full demo" }}
      />
      <ResultsFooter />
    </>
  );
}
