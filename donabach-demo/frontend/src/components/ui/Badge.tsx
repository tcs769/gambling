import type { ReactNode } from "react";
import type { Confidence } from "@/lib/types";
import { Icon } from "./Icon";
import styles from "./Badge.module.css";

const CONFIDENCE: Record<Confidence, { label: string; icon: "check" | "alert" | "cross" }> = {
  high: { label: "Looks right", icon: "check" },
  medium: { label: "Needs a look", icon: "alert" },
  low: { label: "Missing", icon: "cross" },
};

/** Confidence from the parser's cross-checks: always an icon and a word, never color alone. */
export function ConfidenceBadge({ confidence, label }: { confidence: Confidence; label?: string }) {
  const c = CONFIDENCE[confidence];
  return (
    <span className={styles.badge} data-tone={confidence === "high" ? "good" : confidence === "medium" ? "warn" : "bad"}>
      <Icon name={c.icon} size={13} strokeWidth={2.6} />
      {label ?? c.label}
    </span>
  );
}

/** A neutral tag, e.g. "Estimated". */
export function Tag({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "gold" }) {
  return (
    <span className={styles.badge} data-tone={tone}>
      {children}
    </span>
  );
}
