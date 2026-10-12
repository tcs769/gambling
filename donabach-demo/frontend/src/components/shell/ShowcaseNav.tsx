"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SHOWCASE_STEPS, showcaseStepIndex } from "@/lib/steps";
import { Icon } from "../ui/Icon";
import styles from "./ShowcaseNav.module.css";

/**
 * The header's navigation inside the showcase flow: four steps instead of the demo's seven. Every step is reachable
 * at any time (each screen loads what it needs). Below about 520px only the step you are on keeps its word, and the
 * others are numbered dots that still carry their names for a screen reader.
 */
export function ShowcaseNav() {
  const pathname = usePathname();
  const current = showcaseStepIndex(pathname);
  return (
    <nav aria-label="Showcase progress" className={styles.nav}>
      <ol className={styles.list}>
        {SHOWCASE_STEPS.map((step, i) => {
          const done = i < current;
          const active = i === current;
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
              {active ? (
                <span className={styles.step} data-active="true" aria-current="step">
                  {body}
                </span>
              ) : (
                <Link href={step.href} className={styles.step} data-done={done}>
                  {body}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
