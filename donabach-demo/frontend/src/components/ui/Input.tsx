"use client";

import {
  useEffect,
  useRef,
  useState,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
  type Ref,
} from "react";
import styles from "./Input.module.css";

interface ShellProps {
  /** Shown before the value, inside the field: "$". */
  prefixText?: ReactNode;
  /** Shown after the value, inside the field: "%". */
  suffixText?: ReactNode;
  invalid?: boolean;
  /** Class for the bordered shell (width, margins). */
  className?: string;
}

type NativeProps = Omit<InputHTMLAttributes<HTMLInputElement>, "prefix" | "value" | "onChange" | "type" | "className">;

/** A plain text field with the demo's look. Controlled: pass `value` and `onChange`. */
export function Input({
  prefixText,
  suffixText,
  invalid,
  className = "",
  value,
  onChange,
  inputRef,
  ...rest
}: ShellProps & NativeProps & { value: string; onChange: (value: string) => void; inputRef?: Ref<HTMLInputElement> }) {
  return (
    <span className={`${styles.field} ${className}`} data-invalid={!!invalid} data-disabled={!!rest.disabled}>
      {prefixText && <span className={styles.affix}>{prefixText}</span>}
      <input
        ref={inputRef}
        type="text"
        className={styles.input}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={invalid || undefined}
        autoComplete="off"
        spellCheck={false}
        {...rest}
      />
      {suffixText && <span className={styles.affix}>{suffixText}</span>}
    </span>
  );
}

/** "$1,234.5" and "1234" both read as numbers; an empty box is null; anything else is NaN. */
export function parseNumber(text: string): number | null {
  const cleaned = text.replace(/[\s,$%]/g, "").replace(/[−–]/g, "-");
  if (cleaned === "") return null;
  if (!/^-?(\d+\.?\d*|\.\d+)$/.test(cleaned)) return Number.NaN;
  return Number(cleaned);
}

const formatDraft = (value: number | null): string =>
  value === null ? "" : value.toLocaleString("en-US", { maximumFractionDigits: 2 });

interface NumberProps extends ShellProps, NativeProps {
  /** The committed value; null for an empty box. */
  value: number | null;
  /** As the user types: the number, or null when the box is empty or does not hold a usable number. */
  onValueChange?: (value: number | null) => void;
  /** When the user presses Enter, or leaves the box (unless `commitOnBlur` is off), with a usable number. */
  onCommit?: (value: number) => void;
  /** Leaving the box commits what was typed (default). Turn off when something else decides. */
  commitOnBlur?: boolean;
  /** Whole numbers only (ages, counts). */
  integer?: boolean;
  min?: number;
  max?: number;
}

/**
 * A number field that keeps what the user types while they type it, shows thousands separators
 * when they leave, and only hands back values that are numbers inside the limits.
 */
export function NumberInput({
  value,
  onValueChange,
  onCommit,
  integer,
  min,
  max,
  commitOnBlur = true,
  invalid,
  inputMode,
  onBlur,
  onFocus,
  onKeyDown,
  ...rest
}: NumberProps) {
  const [draft, setDraft] = useState(() => formatDraft(value));
  const [focused, setFocused] = useState(false);
  const [lastValue, setLastValue] = useState(value);
  const [badText, setBadText] = useState(false);
  // Whether the text changed since the box was last committed, so tabbing through does nothing.
  const dirty = useRef(false);
  const boxRef = useRef<HTMLInputElement>(null);

  // A box that opens with the cursor in it starts with its text selected: typing replaces it.
  const { autoFocus } = rest;
  useEffect(() => {
    if (autoFocus) boxRef.current?.select();
  }, [autoFocus]);

  // Follow the parent's value when it changes from outside (not while the user is typing).
  if (value !== lastValue) {
    setLastValue(value);
    if (!focused) setDraft(formatDraft(value));
  }

  const check = (text: string): { ok: boolean; parsed: number | null } => {
    const parsed = parseNumber(text);
    if (parsed === null) return { ok: true, parsed: null };
    const bad =
      Number.isNaN(parsed) ||
      (integer && !Number.isInteger(parsed)) ||
      (min !== undefined && parsed < min) ||
      (max !== undefined && parsed > max);
    return { ok: !bad, parsed };
  };

  const commit = (leaving: boolean) => {
    const { ok, parsed } = check(draft);
    if (!ok || parsed === null) {
      // Not usable. Leaving the box puts the last good value back; pressing Enter leaves the text
      // (and the red border) for the user to fix.
      if (leaving) {
        dirty.current = false;
        setDraft(formatDraft(value));
        setBadText(false);
      }
      return;
    }
    dirty.current = false;
    setDraft(formatDraft(parsed));
    setBadText(false);
    onCommit?.(parsed);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    onKeyDown?.(event);
    if (event.defaultPrevented) return;
    if (event.key === "Enter") {
      event.preventDefault();
      commit(false);
    }
  };

  return (
    <Input
      {...rest}
      inputRef={boxRef}
      value={draft}
      invalid={invalid || badText}
      inputMode={inputMode ?? (integer ? "numeric" : "decimal")}
      onChange={(text) => {
        setDraft(text);
        dirty.current = true;
        const { ok, parsed } = check(text);
        setBadText(!ok);
        onValueChange?.(ok ? parsed : null);
      }}
      onFocus={(event) => {
        setFocused(true);
        onFocus?.(event);
      }}
      onBlur={(event) => {
        setFocused(false);
        if (commitOnBlur) {
          if (dirty.current) commit(true);
          else setDraft(formatDraft(value));
        } else {
          const { ok, parsed } = check(draft);
          if (ok && parsed !== null) setDraft(formatDraft(parsed));
        }
        onBlur?.(event);
      }}
      onKeyDown={handleKeyDown}
    />
  );
}
