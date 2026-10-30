"use client";

import { useRef, useState, type FocusEvent, type KeyboardEvent, type MouseEvent } from "react";
import { Button, Icon, Input, NumberInput } from "@/components/ui";
import type { ParsedField } from "@/lib/types";
import { formatValue, sameValue, type FieldValue } from "./fieldLogic";
import styles from "./Fields.module.css";

interface Props {
  field: ParsedField;
  /** The value in effect now: the user's correction, or what was read. */
  current: FieldValue;
  /** The user has already corrected it (so "use what was read" makes sense). */
  changed: boolean;
  /** The parser had a reason to flag it: say what it was. */
  showWhy: boolean;
  /** Nobody has dealt with it yet: this is the first ask, so "Keep as is" is on offer. */
  unresolved: boolean;
  /** Close without changing anything (only offered when this was opened on purpose). */
  onCancel?: () => void;
  /** Put the cursor in the box when it opens. */
  autoFocus?: boolean;
  /** Show the numbers behind the flag on the document. */
  onShowEvidence?: () => void;
  /** The user typed a value (or typed back what was read: the screen treats that as keeping it). */
  onSave: (value: number | string) => void;
  /** Keep what was read. */
  onKeep: () => void;
}

// Pressing a button here must not pull focus out of the box first, or leaving the box would save
// the draft just before the button's own action runs.
const holdFocus = (event: MouseEvent) => event.preventDefault();

/**
 * The inline fix for one number: why it was flagged, a box prefilled with the value, and the two
 * ways out. Enter saves; so does leaving the editor with a changed value.
 */
export function FieldEditor({
  field,
  current,
  changed,
  showWhy,
  unresolved,
  onCancel,
  autoFocus,
  onShowEvidence,
  onSave,
  onKeep,
}: Props) {
  const isNumber = field.kind !== "text";
  const [number, setNumber] = useState<number | null>(typeof current === "number" ? current : null);
  const [text, setText] = useState(typeof current === "string" ? current : "");
  const settled = useRef(false);

  const draft: FieldValue = isNumber ? number : text.trim() === "" ? null : text.trim();
  const canSave = draft !== null && !sameValue(draft, current);
  const missing = field.value === null;

  const save = () => {
    if (settled.current || draft === null || !canSave) return;
    settled.current = true;
    onSave(draft);
  };
  const keep = () => {
    if (settled.current) return;
    settled.current = true;
    onKeep();
  };
  const cancel = () => {
    if (settled.current || !onCancel) return;
    settled.current = true; // leaving the box now must not save the draft
    onCancel();
  };

  const onBlur = (event: FocusEvent<HTMLDivElement>) => {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return; // still inside
    if (canSave) save();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape" && onCancel) {
      event.preventDefault();
      cancel();
    } else if (event.key === "Enter" && !isNumber && (event.target as HTMLElement).tagName === "INPUT") {
      // Enter in the text box saves; Enter on a button still presses that button.
      event.preventDefault();
      save();
    }
  };

  const label = `${field.label}, ${missing ? "value to enter" : "corrected value"}`;
  const readValue = formatValue(field.kind, field.value);

  return (
    <div
      className={styles.editor}
      data-tone={unresolved ? "warn" : "neutral"}
      role="group"
      aria-label={`Fix ${field.label}`}
      onBlur={onBlur}
      onKeyDown={onKeyDown}
    >
      {showWhy && field.flag && (
        <div className={styles.why}>
          <Icon name="alert" size={20} className={styles.whyIcon} />
          <div>
            <p>{field.flag}</p>
            {onShowEvidence && (
              <button type="button" className={styles.link} onMouseDown={holdFocus} onClick={onShowEvidence}>
                Show the numbers we compared
              </button>
            )}
          </div>
        </div>
      )}
      <div className={styles.controls}>
        {isNumber ? (
          <NumberInput
            className={styles.amount}
            value={number}
            onValueChange={setNumber}
            onCommit={save}
            commitOnBlur={false}
            prefixText={field.kind === "money" ? "$" : undefined}
            suffixText={field.kind === "percent" ? "%" : undefined}
            integer={field.kind === "integer"}
            min={0}
            placeholder={missing ? "Enter a value" : undefined}
            aria-label={label}
            autoFocus={autoFocus}
          />
        ) : (
          <Input
            className={styles.wide}
            value={text}
            onChange={setText}
            placeholder="Enter a value"
            aria-label={label}
            autoFocus={autoFocus}
          />
        )}
        {(canSave || missing) && (
          <Button type="button" onMouseDown={holdFocus} onClick={save} disabled={!canSave}>
            {missing ? "Save value" : "Save correction"}
          </Button>
        )}
        {unresolved && !missing && (
          // Until something is typed, keeping the number is the thing to do.
          <Button type="button" variant={canSave ? "secondary" : "primary"} onMouseDown={holdFocus} onClick={keep}>
            Keep as is
          </Button>
        )}
        {changed && (
          <Button type="button" variant="secondary" onMouseDown={holdFocus} onClick={keep}>
            Use {readValue}
          </Button>
        )}
        {onCancel && (
          <Button type="button" variant="ghost" onMouseDown={holdFocus} onClick={cancel}>
            Cancel
          </Button>
        )}
      </div>
      <p className={styles.help}>
        {missing
          ? "We could not read this one. Type the number from the document, or add the document that has it."
          : unresolved
            ? "Check the document, then correct the number or keep it as it was read."
            : "Type the right value, then press Enter or choose Save correction."}
      </p>
    </div>
  );
}
