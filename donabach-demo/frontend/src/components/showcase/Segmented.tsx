"use client";

import { useId } from "react";
import styles from "./Segmented.module.css";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

/**
 * A segmented control: one choice out of a few, as real radio buttons (so the arrow keys move the choice and a
 * screen reader hears "radio button, 1 of 2"), drawn as a pill with the chosen part filled.
 */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  /** Names the group for screen readers. */
  label: string;
  value: T;
  options: readonly SegmentedOption<T>[];
  onChange: (value: T) => void;
}) {
  const name = useId();
  return (
    <div role="radiogroup" aria-label={label} className={styles.group}>
      {options.map((option) => (
        <label key={option.value} className={styles.option}>
          <input
            type="radio"
            name={name}
            value={option.value}
            className={styles.radio}
            checked={option.value === value}
            onChange={() => onChange(option.value)}
          />
          <span className={styles.face}>{option.label}</span>
        </label>
      ))}
    </div>
  );
}
