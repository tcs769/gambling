"use client";

import { useId } from "react";
import type { PlanStyleView } from "@/lib/state";
import { VIEWS, VIEW_BLURB, VIEW_NAME } from "./styles";
import styles from "./PlanStyleSwitch.module.css";

/**
 * The planning-style switch: one style's plan, or all three side by side. Real radio buttons in one group, so the arrow keys
 * move the choice, Tab leaves the group, and a screen reader hears "radio button, 2 of 4". A line under it says what the
 * chosen setting is, and is the group's description.
 */
export function PlanStyleSwitch({
  value,
  onChange,
}: {
  value: PlanStyleView;
  onChange: (value: PlanStyleView) => void;
}) {
  const id = useId();
  return (
    <div className={styles.switch}>
      <p id={`${id}-label`} className={styles.label}>
        Planning style
      </p>
      <div role="radiogroup" aria-labelledby={`${id}-label`} aria-describedby={`${id}-blurb`} className={styles.group}>
        {VIEWS.map((view) => (
          <label key={view} className={styles.option}>
            <input
              type="radio"
              name={id}
              value={view}
              className={styles.radio}
              checked={view === value}
              onChange={() => onChange(view)}
            />
            <span className={styles.face}>{VIEW_NAME[view]}</span>
          </label>
        ))}
      </div>
      <p id={`${id}-blurb`} className={styles.blurb}>
        {VIEW_BLURB[value]}
      </p>
    </div>
  );
}
