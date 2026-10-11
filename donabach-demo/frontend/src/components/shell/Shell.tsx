"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { DemoToggle } from "./DemoToggle";
import { StepNav } from "./StepNav";
import styles from "./Shell.module.css";

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link href="/" className={styles.brand} aria-label="Donabach home">
            <span className={styles.mark} aria-hidden="true" />
            Donabach
          </Link>
          <StepNav />
          <DemoToggle />
        </div>
      </header>
      {/* Keyed by route so each step eases in; the shell itself never re-renders its chrome. */}
      <main key={pathname} className={styles.main}>
        {children}
      </main>
    </div>
  );
}
