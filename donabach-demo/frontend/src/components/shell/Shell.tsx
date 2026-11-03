"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { STEPS, stepOf, usePortal } from "@/lib/portal-state";
import styles from "./Shell.module.css";

/** The left rail (a top bar on narrow screens) and the screen beside it. */
export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { state, name } = usePortal();
  const current = stepOf(pathname);
  const currentIndex = STEPS.findIndex((step) => step.key === current);

  return (
    <div className={styles.shell}>
      <aside className={styles.rail}>
        <Link href="/" className={styles.wordmark}>
          WARAMOUG
          <small>Wealth management</small>
        </Link>
        <nav aria-label="Steps" className={styles.nav}>
          <ol className={styles.steps}>
            {STEPS.map((step, i) => {
              const visited = state.visited.includes(step.key);
              const isCurrent = step.key === current;
              const stepState = isCurrent ? "current" : i < currentIndex ? "done" : "todo";
              const content = (
                <>
                  <span className={styles.dot} aria-hidden="true">
                    {i + 1}
                  </span>
                  <span className={styles.lab}>{step.label}</span>
                </>
              );
              return (
                <li key={step.key} className={styles.item} data-state={stepState}>
                  {visited ? (
                    <Link
                      href={step.href}
                      className={styles.step}
                      data-current={isCurrent}
                      aria-current={isCurrent ? "step" : undefined}
                    >
                      {content}
                    </Link>
                  ) : (
                    <span className={styles.step} data-disabled="true" aria-disabled="true">
                      {content}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        </nav>
        <div className={styles.account}>
          <b>{name}</b>
          Signed in
        </div>
      </aside>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
