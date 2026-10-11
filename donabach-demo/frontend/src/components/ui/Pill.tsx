import type { ReactNode } from "react";
import styles from "./Pill.module.css";

export type PillTone = "neutral" | "gold" | "good" | "warn" | "bad";

/**
 * A small label chip at a readable size (14px). Status tones (good, warn, bad) never stand alone:
 * pass an icon and the text says what the state is.
 */
export function Pill({
  tone = "neutral",
  icon,
  children,
  title,
}: {
  tone?: PillTone;
  icon?: ReactNode;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span className={styles.pill} data-tone={tone} title={title}>
      {icon}
      {children}
    </span>
  );
}
