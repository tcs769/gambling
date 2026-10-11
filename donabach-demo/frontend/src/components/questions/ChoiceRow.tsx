"use client";

import { useState, type KeyboardEvent } from "react";
import { Chip, ChipGroup, NumberInput, Tag } from "@/components/ui";
import styles from "./Questions.module.css";

export interface Choice<T> {
  value: T;
  label: string;
}

interface Props<T extends number | null> {
  /** The question. */
  label: string;
  /** A line under it. */
  hint?: string;
  choices: Choice<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Adds a "Custom" chip that reveals a box for any amount. */
  custom?: { prefix?: string; max?: number };
  /** The value is not in the documents. */
  estimated?: boolean;
  /** The question does not apply right now (e.g. a down payment when no home is planned). */
  disabled?: boolean;
}

/**
 * One question as a single-choice group of chips. Arrow keys move between them (one tab stop per
 * question), like any radio group.
 */
export function ChoiceRow<T extends number | null>({
  label,
  hint,
  choices,
  value,
  onChange,
  custom,
  estimated,
  disabled,
}: Props<T>) {
  const [customOpen, setCustomOpen] = useState(false);
  const [focusBox, setFocusBox] = useState(false);

  const preset = choices.some((c) => c.value === value);
  // Custom is shown when asked for, or when the value is not one of the presets.
  const showCustom = !!custom && (customOpen || (!preset && value !== null));
  const count = choices.length + (custom ? 1 : 0);
  const selected = showCustom
    ? choices.length
    : Math.max(
        0,
        choices.findIndex((c) => c.value === value),
      );

  const choose = (index: number, byKeyboard = false) => {
    if (index < choices.length) {
      setCustomOpen(false);
      onChange(choices[index].value);
    } else {
      setCustomOpen(true);
      setFocusBox(!byKeyboard); // clicking Custom puts the cursor in the box; arrowing onto it does not
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    let next = selected;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (selected + 1) % count;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (selected - 1 + count) % count;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = count - 1;
    else return;
    event.preventDefault();
    choose(next, true);
    event.currentTarget.querySelectorAll<HTMLElement>('[role="radio"]')[next]?.focus();
  };

  return (
    <div className={styles.row} data-disabled={!!disabled}>
      <div className={styles.label}>
        <span>{label}</span>
        {estimated && <Tag>Estimated</Tag>}
        {hint && <span className={styles.hint}>{hint}</span>}
      </div>
      <div className={styles.choices} onKeyDown={onKeyDown}>
        <ChipGroup label={label}>
          {choices.map((choice, i) => (
            <Chip
              key={String(choice.value)}
              selected={!showCustom && choice.value === value}
              tabIndex={i === selected ? 0 : -1}
              disabled={disabled}
              onClick={() => choose(i)}
            >
              {choice.label}
            </Chip>
          ))}
          {custom && (
            <Chip
              selected={showCustom}
              tabIndex={selected === choices.length ? 0 : -1}
              disabled={disabled}
              onClick={() => choose(choices.length)}
            >
              Custom
            </Chip>
          )}
        </ChipGroup>
        {showCustom && custom && (
          <NumberInput
            className={styles.custom}
            value={value}
            prefixText={custom.prefix}
            min={0}
            max={custom.max}
            autoFocus={focusBox}
            disabled={disabled}
            aria-label={`${label} (custom amount)`}
            onValueChange={(next) => {
              if (next !== null) onChange(next as T);
            }}
          />
        )}
      </div>
    </div>
  );
}
