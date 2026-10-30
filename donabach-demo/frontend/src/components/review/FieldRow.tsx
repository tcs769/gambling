"use client";

import { useRef } from "react";
import { ConfidenceBadge, Icon, Tag } from "@/components/ui";
import type { ParsedField } from "@/lib/types";
import { FieldEditor } from "./FieldEditor";
import { formatValue, splitLabel, type FieldStatus } from "./fieldLogic";
import styles from "./Fields.module.css";

interface Props {
  field: ParsedField;
  status: FieldStatus;
  /** This row (or a check that uses it) is the one shown on the document. */
  selected: boolean;
  /** The user opened the editor on purpose ("Edit again"). */
  editing: boolean;
  /** Show the numbers behind the flag (set when a failed check involves this number). */
  onShowEvidence?: () => void;
  onSelect: () => void;
  onEdit: () => void;
  onCancelEdit: () => void;
  onSave: (value: number | string) => void;
  onKeep: () => void;
}

/** One extracted number: label, value, confidence, and (when it needs a look) the fix right under it. */
export function FieldRow({
  field,
  status,
  selected,
  editing,
  onShowEvidence,
  onSelect,
  onEdit,
  onCancelEdit,
  onSave,
  onKeep,
}: Props) {
  const rowRef = useRef<HTMLButtonElement>(null);
  const { title, sub } = splitLabel(field);
  const { value, changed, needsLook, resolved } = status;
  // The editor goes away when it is done; keep the keyboard where it was.
  const settle = () => rowRef.current?.focus({ preventScroll: true });
  const open = (needsLook && !resolved) || editing;
  const waiting = needsLook && !resolved;

  return (
    <li className={styles.item} data-field-key={field.key}>
      <button
        ref={rowRef}
        type="button"
        className={styles.row}
        data-selected={selected}
        data-waiting={waiting}
        aria-current={selected ? "true" : undefined}
        onClick={onSelect}
      >
        <span className={styles.label}>
          <span className={styles.title}>{title}</span>
          {sub && <span className={styles.sub}>{sub}</span>}
        </span>
        <span className={`${styles.value} num`} data-missing={value === null}>
          {formatValue(field.kind, value)}
        </span>
        <span className={styles.status}>
          {resolved ? (
            <Tag>
              <Icon name="check" size={13} strokeWidth={2.6} />
              Confirmed by you
            </Tag>
          ) : (
            <ConfidenceBadge confidence={field.confidence} />
          )}
        </span>
      </button>

      {open ? (
        <FieldEditor
          // Start fresh whenever the value in effect changes underneath it.
          key={`${field.key}:${String(value)}:${editing}`}
          field={field}
          current={value}
          changed={changed}
          showWhy={needsLook}
          unresolved={waiting}
          onCancel={
            editing
              ? () => {
                  onCancelEdit();
                  settle();
                }
              : undefined
          }
          autoFocus={editing}
          onShowEvidence={onShowEvidence}
          onSave={(next) => {
            settle();
            onSave(next);
          }}
          onKeep={() => {
            settle();
            onKeep();
          }}
        />
      ) : (
        resolved && (
          <p className={styles.note}>
            <span>
              {field.value === null
                ? `You entered ${formatValue(field.kind, value)}.`
                : changed
                  ? `You changed this from ${formatValue(field.kind, field.value)} to ${formatValue(field.kind, value)}.`
                  : "You kept the value as it was read."}
            </span>
            <button type="button" className={styles.link} onClick={onEdit}>
              Edit again
            </button>
          </p>
        )
      )}
    </li>
  );
}
