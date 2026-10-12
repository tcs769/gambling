"use client";

import { Panel, PanelTitle } from "@/components/ui";
import { count } from "@/lib/format";
import type { AltStyle, StyleSlot, StyleSlots } from "@/lib/state";
import type { PlanResponse } from "@/lib/types";
import { StyleColumn } from "./StyleColumn";
import { hasZeroRange } from "./StyleFigures";
import { STYLES } from "./styles";
import styles from "./StyleComparison.module.css";

const ASKED: StyleSlot = { status: "loading" };

/**
 * The three planning styles next to each other: the plan on screen (equity-first) and the other two's plans for the same
 * household, shock and seed, so every figure is measured on the same simulated futures. A style that has not answered yet
 * says so in its own column; the others are complete and usable.
 */
export function StyleComparison({
  plan,
  slots,
  onRetry,
}: {
  /** The equity-first plan on screen. */
  plan: PlanResponse;
  slots: StyleSlots;
  onRetry: (style: AltStyle) => void;
}) {
  const slotOf = (style: (typeof STYLES)[number]): StyleSlot =>
    style === "equity_first" ? { status: "ready", plan } : (slots[style] ?? ASKED);
  const ready = STYLES.map((style) => slotOf(style)).flatMap((slot) => (slot.status === "ready" ? [slot.plan] : []));
  const zero = ready.some(hasZeroRange);
  const failed = STYLES.filter((style) => slotOf(style).status === "failed").length;
  return (
    <Panel aria-labelledby="styles-title">
      <PanelTitle
        id="styles-title"
        aside={`After tax, in 2026 dollars · measured on ${count(plan.settings.n_eval_paths)} fresh futures`}
      >
        The three planning styles side by side
      </PanelTitle>
      <p className={styles.intro}>
        The same household planned in each style, on the same simulated futures. Where a good RIA has a figure to
        compare, it is shown beside the plan&apos;s.
      </p>
      {/* Said aloud as the plans arrive (a column filling in is otherwise silent). */}
      <p className="sr-only" role="status">
        {ready.length} of {STYLES.length} plans ready{failed > 0 ? `, ${failed} could not be made` : ""}.
      </p>
      <div className={styles.wrap}>
        <div className={styles.columns}>
          {STYLES.map((style) => (
            <StyleColumn
              key={style}
              style={style}
              slot={slotOf(style)}
              isDefault={style === "equity_first"}
              onRetry={onRetry}
            />
          ))}
        </div>
      </div>
      <p className={styles.note}>
        {zero ? (
          <>
            <strong>†</strong> The 90% range includes zero, so that advantage is not distinguishable from no effect.
          </>
        ) : (
          <>
            No advantage here has a 90% range that includes zero; a <strong>†</strong> would mark one that did.
          </>
        )}
      </p>
    </Panel>
  );
}
