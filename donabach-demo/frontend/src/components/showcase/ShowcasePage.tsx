"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import styles from "./ShowcasePage.module.css";

/**
 * One screen of the showcase flow, easing in as the demo's screens do. The shell keeps a single `main` for the whole
 * flow (so the flow's state survives moving between its screens), which means the screens have to ease in on their own:
 * keyed by the path, this remounts only the page, never the layout and its provider.
 */
export function ShowcasePage({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div key={pathname} className={styles.page}>
      {children}
    </div>
  );
}
