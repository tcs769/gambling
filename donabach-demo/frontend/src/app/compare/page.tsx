"use client";

import { useRouter } from "next/navigation";
import { CompareView } from "@/components/invest/CompareView";
import { Screen } from "@/components/portal/Screen";
import { useGuard } from "@/components/portal/useGuard";
import { DISCLAIMER } from "@/lib/invest-format";
import { usePortal } from "@/lib/portal-state";
import styles from "../Disclaimer.module.css";

export default function ComparePage() {
  const { state } = usePortal();
  const router = useRouter();
  const ready = useGuard("invest", "plan");
  if (!ready || !state.plan) return null;
  return (
    <Screen
      title="Compare"
      back={{ onClick: () => router.push("/invest") }}
      footer={<p className={styles.disclaimer}>{DISCLAIMER}</p>}
    >
      <CompareView plan={state.plan} />
    </Screen>
  );
}
