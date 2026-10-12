import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";
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

type LinkProps = Common & { href: string; className?: string } & Omit<
    AnchorHTMLAttributes<HTMLAnchorElement>,
    "href" | "className" | "children"
  >;

export function ButtonLink({ variant = "primary", arrow, children, href, className = "", ...rest }: LinkProps) {
  return (
    <Link href={href} className={`${styles.button} ${styles[variant]} ${className}`} {...rest}>
      {children}
      {arrow && <Icon name="arrow" size={18} />}
    </Link>
  );
}
