"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { STEPS, stepIndex } from "@/lib/steps";
import { useApp } from "@/lib/state";
import { Icon } from "../ui/Icon";
import styles from "./StepNav.module.css";

export function StepNav() {
  const pathname = usePathname();
  const { state } = useApp();
  const current = stepIndex(pathname);
  const hasDocs = state.docs.some((d) => d.status === "ready");
  const hasProfile = !!state.profile;

  // You can always go back. Going forward needs the earlier steps done, except in demo mode,
  // where every screen prepares what it needs from the sample documents.
  const reachable = (i: number): boolean => {
    if (i <= current || state.demoMode) return true;
    if (i === 1 || i === 2) return hasDocs;
    return hasProfile;
  };

  return (
    <nav aria-label="Progress" className={styles.nav}>
      <ol className={styles.list}>
        {STEPS.map((step, i) => {
          const done = i < current;
          const active = i === current;
          const enabled = reachable(i);
          const body = (
            <>
              <span className={styles.dot} data-done={done} data-active={active}>
                {done ? <Icon name="check" size={14} strokeWidth={3} /> : i + 1}
              </span>
              <span className={styles.label}>{step.label}</span>
            </>
          );
          return (
            <li key={step.key} className={styles.item}>
              {enabled && !active ? (
                <Link href={step.href} className={styles.step} data-done={done}>
                  {body}
                </Link>
              ) : (
                <span className={styles.step} data-active={active} data-disabled={!enabled} aria-current={active ? "step" : undefined}>
                  {body}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
