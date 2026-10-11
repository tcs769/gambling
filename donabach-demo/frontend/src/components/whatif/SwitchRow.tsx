import styles from "./WhatIf.module.css";

/** An on/off row: a real checkbox with the switch role, styled like the Demo mode toggle. */
export function SwitchRow({
  label,
  checked,
  onChange,
  busy = false,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** A re-plan is running: ignore changes (the switch stays focusable). */
  busy?: boolean;
}) {
  return (
    <label className={styles.switchRow}>
      <span>{label}</span>
      <input
        type="checkbox"
        role="switch"
        className={styles.switchInput}
        checked={checked}
        aria-disabled={busy || undefined}
        onChange={(event) => {
          if (!busy) onChange(event.target.checked);
        }}
      />
      <span className={styles.switchTrack} aria-hidden="true">
        <span className={styles.switchThumb} />
      </span>
    </label>
  );
}
