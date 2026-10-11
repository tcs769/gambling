"use client";

import { Pending } from "@/components/plan/Pending";
import { useShowcase } from "@/lib/showcase";

/**
 * What a showcase screen shows until the household has loaded: panels about the size of the real ones, a spinner,
 * or the API's own error with a retry. The first call can take a moment (the API may still be working out the plan).
 */
export function ShowcasePending({ blocks, label }: { blocks: number[]; label: string }) {
  const { status, loadError, actions } = useShowcase();
  return (
    <Pending
      status={status}
      error={loadError ?? undefined}
      retry={actions.reload}
      label={label}
      blocks={blocks}
    />
  );
}
