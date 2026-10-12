"use client";

import { FlowNav } from "@/components/showcase/FlowNav";
import styles from "@/components/showcase/Showcase.module.css";
import { HouseholdCardView } from "@/components/showcase/HouseholdCardView";
import { ShowcasePending } from "@/components/showcase/ShowcasePending";
import { PageHeader, ResultsFooter } from "@/components/ui";
import { useShowcase } from "@/lib/showcase";

/** Screen 1: who the household is, what it has and what it is saving for. */
export default function ShowcaseHouseholdPage() {
  const { status, data } = useShowcase();

  if (status !== "ready" || !data) {
    return (
      <>
        {/* Neutral while the household loads and if it cannot be loaded: its name is not known yet. */}
        <PageHeader title="The household" />
        <ShowcasePending blocks={[900]} label="Loading the household…" />
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow={data.type_label}
        title={data.name}
        subtitle={<span className={styles.tagline}>{data.tagline}</span>}
      />
      <HouseholdCardView card={data.card} horizonAge={data.waterfall.horizon_age} />
      <FlowNav
        back={{ href: "/", label: "Back to the demo home" }}
        next={{ href: "/showcase/wealth", label: "See what a good advisor gets them" }}
      />
      <ResultsFooter note={data.footer_note} />
    </>
  );
}
