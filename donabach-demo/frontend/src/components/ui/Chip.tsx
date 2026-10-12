import type { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./Chip.module.css";

/** A tap-to-select chip. Use inside role="radiogroup" for single choice. */
export function Chip({
  selected,
  children,
  className = "",
  ...rest
}: { selected?: boolean; children: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={!!selected}
      className={`${styles.chip} ${className}`}
      data-selected={!!selected}
      {...rest}
    >
      {children}
    </button>
  );
}

export function ChipGroup({
  label,
  describedBy,
  children,
}: {
  label: string;
  /** The id of text that explains the question (a helper line under it). */
  describedBy?: string;
  children: ReactNode;
}) {
  return (
    <div role="radiogroup" aria-label={label} aria-describedby={describedBy} className={styles.group}>
      {children}
    </div>
  );
}
