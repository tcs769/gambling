"use client";

import { useId, useState } from "react";
import { Icon, parseNumber } from "@/components/ui";
import { splitLabel } from "@/components/review/fieldLogic";
import { customerLabel, formatField, sameValue } from "@/lib/portal-format";
import type { ParsedField } from "@/lib/portal-types";
import styles from "./ReviewRow.module.css";

interface Props {
  field: ParsedField;
  /** The name to show instead of the field's own (the friendly rows). */
  label?: string;
  /** The value in effect: the customer's edit, or what was read. */
  value: number | string | null;
  edited: boolean;
  /** The reading was not sure of it (or could not find it). */
  flagged: boolean;
  /** Confirmed as printed, or edited. */
  resolved: boolean;
  confirmed: boolean;
  selected: boolean;
  onSelect: () => void;
  /** A number was typed. Typing back what the document says clears the edit. */
  onEdit: (value: number) => void;
  onReset: () => void;
  onConfirm: () => void;
}

const CONFIDENCE_LABEL = { high: "High confidence", medium: "Medium confidence", low: "Low confidence" } as const;

/** One extracted field: its label, an editable value, how sure the reading was, and (when flagged) the way to confirm it. */
export function ReviewRow({
  field,
  label,
  value,
  edited,
  flagged,
  resolved,
  confirmed,
  selected,
  onSelect,
  onEdit,
  onReset,
  onConfirm,
}: Props) {
  const { title: rawTitle, sub: rawSub } = splitLabel(field);
  const title = label ?? customerLabel(rawTitle);
  const sub = !label && rawSub ? customerLabel(rawSub) : undefined;
  const inputId = useId();
  const editable = field.kind !== "text";
  const waiting = flagged && !resolved;

  return (
    <li
      className={styles.field}
      data-field-key={field.key}
      data-selected={selected}
      data-flagged={flagged}
      data-waiting={waiting}
      aria-current={selected ? "true" : undefined}
      onClick={onSelect}
    >
      <label className={styles.label} htmlFor={editable ? inputId : undefined}>
        <span className={styles.title}>{title}</span>
        {sub && <span className={styles.sub}>{sub}</span>}
      </label>
      <span className="sr-only">{CONFIDENCE_LABEL[field.confidence]}</span>
      {editable ? (
        <ValueInput
          id={inputId}
          field={field}
          value={typeof value === "number" ? value : null}
          onFocus={onSelect}
          onCommit={onEdit}
          data-edited={edited}
        />
      ) : (
        <span className={`${styles.text} num`}>{formatField(field.kind, value)}</span>
      )}

      {(flagged || edited) && (
        <div className={styles.note}>
          {flagged && field.flag && !resolved && <p className={styles.flag}>{field.flag}</p>}
          <div className={styles.status}>
            {waiting && (
              <button type="button" className={styles.confirm} onClick={onConfirm}>
                Confirm
              </button>
            )}
            {flagged && resolved && !edited && confirmed && (
              <span className={styles.tag} data-tone="done">
                <Icon name="check" size={14} strokeWidth={2.6} />
                Confirmed
              </span>
            )}
            {edited && (
              <>
                <span className={styles.tag} data-tone="edited">
                  {flagged && <Icon name="check" size={14} strokeWidth={2.6} />}
                  Edited
                </span>
                <button type="button" className={styles.reset} onClick={onReset}>
                  Reset to {formatField(field.kind, field.value)}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

function ValueInput({
  id,
  field,
  value,
  onFocus,
  onCommit,
  ...rest
}: {
  id: string;
  field: ParsedField;
  value: number | null;
  onFocus: () => void;
  onCommit: (value: number) => void;
  "data-edited": boolean;
}) {
  const shown = value === null ? "" : formatNumber(field, value);
  const [draft, setDraft] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);

  const commit = () => {
    if (draft === null) return;
    const parsed = parseNumber(draft);
    const bad =
      parsed === null || Number.isNaN(parsed) || parsed < 0 || (field.kind === "integer" && !Number.isInteger(parsed));
    setDraft(null);
    setInvalid(false);
    if (bad) return;
    if (!sameValue(parsed, value)) onCommit(parsed);
  };

  return (
    <span className={styles.input} data-invalid={invalid} {...rest}>
      {field.kind === "money" && <span className={styles.affix}>$</span>}
      <input
        id={id}
        type="text"
        inputMode={field.kind === "integer" ? "numeric" : "decimal"}
        className={`${styles.fieldbox} num`}
        value={draft ?? shown}
        autoComplete="off"
        spellCheck={false}
        placeholder={value === null ? "Enter a value" : undefined}
        aria-invalid={invalid || undefined}
        onFocus={(e) => {
          onFocus();
          e.currentTarget.select();
        }}
        onChange={(e) => {
          setDraft(e.target.value);
          const parsed = parseNumber(e.target.value);
          setInvalid(parsed !== null && Number.isNaN(parsed));
        }}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          } else if (e.key === "Escape") {
            setDraft(null);
            setInvalid(false);
          }
        }}
      />
      {field.kind === "percent" && <span className={styles.affix}>%</span>}
    </span>
  );
}

function formatNumber(field: ParsedField, value: number): string {
  if (field.kind === "integer") return value.toLocaleString("en-US");
  const cents = !Number.isInteger(Math.round(value * 100) / 100);
  return value.toLocaleString("en-US", { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: 2 });
}
