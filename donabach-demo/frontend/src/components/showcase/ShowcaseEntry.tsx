"use client";

import { useEffect } from "react";
import { ButtonLink } from "@/components/ui";
import { prefetchShowcase } from "@/lib/showcase";
import styles from "./ShowcaseEntry.module.css";

/**
 * The way into the showcase from the home page: a household, the strategies that earn its advantage over a good advisor,
 * and the wealth they build, and a plan that re-plans when the household changes, in four screens that need no documents.
 *
 * The showcase's first screen needs the household from the API, so it is asked for as soon as this link is on the page,
 * and again whenever the link is hovered, focused or touched (that asks only if the answer never came or is old): by the
 * time the link is followed the household is usually here and the screen draws with no placeholder.
 */
export function ShowcaseEntry() {
  useEffect(() => {
    prefetchShowcase();
  }, []);
  return (
    <aside className={styles.entry} aria-label="The showcase">
      <div className={styles.text}>
        <p className={styles.title}>Short on time? See it in four screens.</p>
        <p className={styles.lede}>
          A household&apos;s savings, what a good advisor gets them, the strategies that earn Donabach its advantage,
          and how the plan adapts when the household changes. No documents needed.
        </p>
      </div>
      <ButtonLink
        href="/showcase"
        variant="secondary"
        arrow
        onPointerEnter={prefetchShowcase}
        onPointerDown={prefetchShowcase}
        onFocus={prefetchShowcase}
      >
        Open the showcase
      </ButtonLink>
    </aside>
  );
}
