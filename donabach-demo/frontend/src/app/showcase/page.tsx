"use client";

import { FlowNav } from "@/components/showcase/FlowNav";
import { HouseholdCardView } from "@/components/showcase/HouseholdCardView";
import { ShowcasePending } from "@/components/showcase/ShowcasePending";
import { PageHeader, ResultsFooter } from "@/components/ui";
import { useShowcase } from "@/lib/showcase";

/** Screen 1: who the household is, what it has and what it is saving for. */
export default function ShowcaseHouseholdPage() {
  const { status, data, analysis } = useShowcase();

  if (status !== "ready" || !data || !analysis) {
    return (
      <>
        <PageHeader title="Loading the household…" />
        <ShowcasePending blocks={[900]} label="Loading the household…" />
      </>
    );
  }

  return (
    <>
      <PageHeader eyebrow={data.type_label} title={data.name} subtitle={data.tagline} />
      <HouseholdCardView card={data.card} horizonAge={analysis.horizon_age} />
      <FlowNav back={{ href: "/", label: "Back to the demo home" }} next={{ href: "/showcase/strategies", label: "See the strategies" }} />
      <ResultsFooter />
    </>
  );
}
