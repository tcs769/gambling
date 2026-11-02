"use client";

import { useRouter } from "next/navigation";
import { Screen } from "@/components/portal/Screen";
import { useGuard } from "@/components/portal/useGuard";
import { usePortal } from "@/lib/portal-state";
import styles from "../Placeholder.module.css";

// A placeholder: the Invest screen is built next. The state it needs (the Plan result and approved[plan_id][move_key]) is in the provider.
export default function InvestPage() {
  const { state } = usePortal();
  const router = useRouter();
  const ready = useGuard("invest", "plan");
  if (!ready || !state.plan) return null;
  return (
    <Screen
      title="Invest"
      back={{ onClick: () => router.push("/goals") }}
      next={{ label: "Compare", onClick: () => router.push("/compare") }}
      footer={<p className={styles.disclaimer}>Illustration based on simulated outcomes. Not investment advice.</p>}
    >
      <p className={`${styles.id} num`} data-testid="plan-id">
        {state.plan.plan_id}
      </p>
    </Screen>
  );
}
