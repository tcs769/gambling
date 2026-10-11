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
    <button type="button" role="radio" aria-checked={!!selected} className={`${styles.chip} ${className}`} data-selected={!!selected} {...rest}>
      {children}
    </button>
  );
}

export function ChipGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="radiogroup" aria-label={label} className={styles.group}>
      {children}
    </div>
  );
}
