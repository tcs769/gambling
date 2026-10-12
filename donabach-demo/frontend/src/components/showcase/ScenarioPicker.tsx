"use client";

import { useId } from "react";
import type { ScenarioInfo } from "@/lib/types";
import styles from "./Scenario.module.css";

/** The unchanged household: not an event of the API's, the choice that shows the household as it is. */
export const NO_CHANGE = "none";

/**
 * The events to choose from, as real radio buttons in a labelled group: the arrow keys move the choice (and make it), Tab
 * leaves the group, and a screen reader hears "radio button, 2 of 3". "No change" comes first; the other labels are the
 * API's own. Below about 560px they stack, so nothing reaches past a 320px screen.
 */
export function ScenarioPicker({
  scenarios,
  value,
  onChange,
}: {
  scenarios: readonly ScenarioInfo[];
  value: string;
  onChange: (key: string) => void;
}) {
  const name = useId();
  const options = [{ key: NO_CHANGE, label: "No change" }, ...scenarios.map(({ key, label }) => ({ key, label }))];
  return (
    <fieldset className={styles.picker}>
      <legend className={styles.legend}>What happens to the household?</legend>
      <div className={styles.options}>
        {options.map((option) => (
          <label key={option.key} className={styles.option}>
            <input
              type="radio"
              name={name}
              value={option.key}
              className={styles.radio}
              checked={option.key === value}
              onChange={() => onChange(option.key)}
            />
            <span className={styles.face}>
              <span className={styles.dot} aria-hidden="true" />
              {option.label}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
