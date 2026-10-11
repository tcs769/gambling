import type { ReactNode } from "react";
import styles from "./PageHeader.module.css";

export function PageHeader({
  title,
  subtitle,
  actions,
  status,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  /** A short state of the page, beside the title (e.g. "Refining plan..."). It is shorter than the title, so it never changes the header's height. */
  status?: ReactNode;
}) {
  return (
    <div className={styles.header}>
      <div>
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
