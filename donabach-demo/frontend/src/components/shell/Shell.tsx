"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { inShowcase } from "@/lib/steps";
import { DemoToggle } from "./DemoToggle";
import { ShowcaseNav } from "./ShowcaseNav";
import { StepNav } from "./StepNav";
import styles from "./Shell.module.css";

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  // The showcase flow (/showcase) has its own three steps in the header, and none of the demo's switches: its numbers
  // are fixed on the API's side, so Demo mode has nothing to do there.
  const showcase = inShowcase(pathname);
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link href="/" className={styles.brand} aria-label="Donabach home">
            <span className={styles.mark} aria-hidden="true" />
            Donabach
          </Link>
          {showcase ? <ShowcaseNav /> : <StepNav />}
          {showcase ? (
            <Link href="/" className={styles.fullDemo}>
              Full demo
            </Link>
          ) : (
            <DemoToggle />
          )}
        </div>
      </header>
      {/* Keyed by route so each step eases in; the shell itself never re-renders its chrome. */}
      <main key={pathname} className={styles.main}>
        {children}
      </main>
    </div>
  );
}
