"use client";

import type { ReactNode } from "react";
import { Button, Icon } from "@/components/ui";
import { WhatIfBanner } from "./WhatIfBanner";
import styles from "./WhatIf.module.css";

/** The "What if..." button that opens the what-if panel. */
export function WhatIfButton({ open, onClick }: { open: boolean; onClick: () => void }) {
  return (
    <Button
      id="whatif-button"
      variant="secondary"
      className={styles.whatIfButton}
      onClick={onClick}
      aria-expanded={open}
      aria-controls="whatif-panel"
    >
      <Icon name="sliders" size={18} />
      What if...
    </Button>
  );
}

/**
 * The page content beside the what-if panel. With the panel open the content narrows to make room
 * (nothing is covered, so the charts can be watched while they re-plan); while a re-plan runs the
 * content stays as it was, at reduced opacity, and new numbers glide in when they arrive. The
 * what-if banner sits at the top of the content column, so the panel stays where it is when the
 * banner appears.
 */
export function WhatIfLayout({
  open,
  stale,
  panel,
  children,
}: {
  open: boolean;
  /** A re-plan is running. */
  stale: boolean;
  /** The panel itself (rendered only while open). */
  panel: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={styles.layout} data-open={open}>
      <div className={styles.column}>
        <WhatIfBanner />
        <div className={styles.main} data-stale={stale} aria-busy={stale}>
          {children}
        </div>
      </div>
      {open && <aside className={styles.side}>{panel}</aside>}
    </div>
  );
}
