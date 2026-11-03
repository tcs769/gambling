"use client";

import { useId, type ReactNode } from "react";
import styles from "./Choices.module.css";

export interface Choice {
  id: string;
  label: string;
}

interface Props {
  name: string;
  legend: string;
  options: Choice[];
  value: string;
  onChange: (id: string) => void;
  /** What shows under the chips (a value that goes with the chosen one). */
  children?: ReactNode;
}

/** One question row of the mockup: the question on the left, chips on the right (radio buttons drawn as chips, so the keyboard works as usual). */
export function Choices({ name, legend, options, value, onChange, children }: Props) {
  const labelId = useId();
  return (
    <div className={styles.q}>
      <span id={labelId} className={styles.qt}>
        {legend}
      </span>
      <div>
        <div className={styles.chips} role="radiogroup" aria-labelledby={labelId}>
          {options.map((option) => (
            <label key={option.id} className={styles.chip}>
              <input
                type="radio"
                name={name}
                className={styles.radio}
                checked={value === option.id}
                onChange={() => onChange(option.id)}
              />
              <span className={styles.face}>{option.label}</span>
            </label>
          ))}
        </div>
        {children}
      </div>
    </div>
  );
}
