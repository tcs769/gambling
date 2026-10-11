import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Icon } from "./Icon";
import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "ghost";

interface Common {
  variant?: Variant;
  children: ReactNode;
  /** Show a trailing arrow (for "continue" actions). */
  arrow?: boolean;
  busy?: boolean;
}

export function Button({
  variant = "primary",
  arrow,
  busy,
  children,
  className = "",
  disabled,
  ...rest
}: Common & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={`${styles.button} ${styles[variant]} ${className}`} disabled={disabled || busy} {...rest}>
      {busy && <span className={styles.spinner} aria-hidden="true" />}
      {children}
      {arrow && !busy && <Icon name="arrow" size={18} />}
    </button>
  );
}

export function ButtonLink({
  variant = "primary",
  arrow,
  children,
  href,
  className = "",
}: Common & { href: string; className?: string }) {
  return (
    <Link href={href} className={`${styles.button} ${styles[variant]} ${className}`}>
      {children}
      {arrow && <Icon name="arrow" size={18} />}
    </Link>
  );
}
