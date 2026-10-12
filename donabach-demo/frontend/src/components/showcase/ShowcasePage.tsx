"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import styles from "./ShowcasePage.module.css";

/** The flow's three screens, each one click from the others. */
const SCREENS = ["/showcase", "/showcase/strategies", "/showcase/wealth"];

/**
 * One screen of the showcase flow, easing in as the demo's screens do. The shell keeps a single `main` for the whole
 * flow (so the flow's state survives moving between its screens), which means the screens have to ease in on their own:
 * keyed by the path, this remounts only the page, never the layout and its provider.
 *
 * It also has the browser fetch the other screens' code now, so that the next one opens at once (a link only does that
 * once it scrolls into view, and the way on is at the foot of a long page).
 */
export function ShowcasePage({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    for (const screen of SCREENS) router.prefetch(screen);
  }, [router]);
  return (
    <div key={pathname} className={styles.page}>
      {children}
    </div>
  );
}
