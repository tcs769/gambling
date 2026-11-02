"use client";

import type { ReactNode } from "react";
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
  /** What shows under the options when one of them asks for more (the "Other" value inputs). */
  children?: ReactNode;
}

/** A question answered by tapping one of a few options (radio buttons drawn as chips, so the keyboard works as usual). */
export function Choices({ name, legend, options, value, onChange, children }: Props) {
  return (
    <fieldset className={styles.group}>
      <legend className={styles.legend}>{legend}</legend>
      <div className={styles.chips} role="presentation">
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
    </fieldset>
  );
}
