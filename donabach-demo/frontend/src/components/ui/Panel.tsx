import type { HTMLAttributes, ReactNode } from "react";
import styles from "./Panel.module.css";

interface Props extends HTMLAttributes<HTMLElement> {
  children: ReactNode;
  /** `plain` has no fill, only a hairline: for content that sits inside another panel. */
  tone?: "panel" | "plain";
  as?: "section" | "div" | "article" | "aside";
}

export function Panel({ children, tone = "panel", as: Tag = "section", className = "", ...rest }: Props) {
  return (
    <Tag className={`${styles.panel} ${tone === "plain" ? styles.plain : ""} ${className}`} {...rest}>
      {children}
    </Tag>
  );
}

export function PanelTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className={styles.title}>
      <h2>{children}</h2>
      {aside && <div className={styles.aside}>{aside}</div>}
    </div>
  );
}
