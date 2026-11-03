"use client";

import { useRouter } from "next/navigation";
import { InvestView } from "@/components/invest/InvestView";
import { Screen } from "@/components/portal/Screen";
import { useGuard } from "@/components/portal/useGuard";
import { DISCLAIMER } from "@/lib/invest-format";
import { usePortal } from "@/lib/portal-state";
import styles from "../Disclaimer.module.css";

export default function InvestPage() {
  const { state } = usePortal();
  const router = useRouter();
  const ready = useGuard("invest", "plan");
  if (!ready || !state.plan) return null;
  return (
    <Screen
      back={{ onClick: () => router.push("/goals") }}
      next={{ label: "Compare", onClick: () => router.push("/compare") }}
      footer={<p className={styles.disclaimer}>{DISCLAIMER}</p>}
    >
      <InvestView plan={state.plan} />
    </Screen>
  );
}
