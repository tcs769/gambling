import type { ReactNode } from "react";
import styles from "./PageHeader.module.css";

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
  status,
}: {
  /** A short line above the title that says what kind of thing this is (it wraps, unlike `status`). */
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  /** A short state of the page, beside the title (e.g. "Refining plan..."). It is shorter than the title, so it never changes the header's height. */
  status?: ReactNode;
}) {
  return (
    <div className={styles.header}>
      <div>
        {eyebrow && <p className={styles.eyebrow}>{eyebrow}</p>}
        <div className={styles.titleRow}>
          <h1>{title}</h1>
          {status}
        </div>
        {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
      </div>
      {actions && <div className={styles.actions}>{actions}</div>}
    </div>
  );
}
