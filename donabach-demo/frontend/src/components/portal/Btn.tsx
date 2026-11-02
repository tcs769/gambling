import type { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./Btn.module.css";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "link";
  busy?: boolean;
  children: ReactNode;
};

/** A button: primary (navy), secondary (outlined) or link (text). */
export function Btn({ variant = "primary", busy, disabled, className = "", children, ...rest }: Props) {
  return (
    <button
      type="button"
      className={`${styles.btn} ${styles[variant]} ${className}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy && <span className={styles.spinner} aria-hidden="true" />}
      {children}
    </button>
  );
}
