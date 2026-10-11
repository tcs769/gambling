import type { ReactNode } from "react";
import styles from "./StatCard.module.css";

/** One headline number: label (sentence case), value, optional supporting line. */
export function StatCard({
  label,
  value,
  note,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: "default" | "accent";
}) {
  return (
    <div className={styles.card} data-tone={tone}>
      <div className={styles.label}>{label}</div>
      <div className={styles.value}>{value}</div>
      {note && <div className={styles.note}>{note}</div>}
    </div>
  );
}
