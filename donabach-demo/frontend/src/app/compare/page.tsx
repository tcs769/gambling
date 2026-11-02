"use client";

import { useRouter } from "next/navigation";
import { Screen } from "@/components/portal/Screen";
import { useGuard } from "@/components/portal/useGuard";
import { usePortal } from "@/lib/portal-state";
import styles from "../Placeholder.module.css";

// A placeholder: the Compare screen is built next.
export default function ComparePage() {
  const { state } = usePortal();
  const router = useRouter();
  const ready = useGuard("invest", "plan");
  if (!ready || !state.plan) return null;
  return (
    <Screen
      title="Compare"
      back={{ onClick: () => router.push("/invest") }}
      footer={<p className={styles.disclaimer}>Illustration based on simulated outcomes. Not investment advice.</p>}
    >
      <p className={`${styles.id} num`} data-testid="plan-id">
        {state.plan.plan_id}
      </p>
    </Screen>
  );
}
