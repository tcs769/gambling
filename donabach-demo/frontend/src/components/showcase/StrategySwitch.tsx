import styles from "./StrategySwitch.module.css";

/**
 * A strategy's on/off switch: a real checkbox with the switch role (Space flips it), labelled with the strategy's name,
 * and described by the sentence that says what it does (which a screen reader reads on focus, shown or not).
 */
export function StrategySwitch({
  label,
  checked,
  onChange,
  describedBy,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  describedBy?: string;
}) {
  return (
    <label className={styles.switch}>
      <input
        type="checkbox"
        role="switch"
        className={styles.input}
        checked={checked}
        aria-describedby={describedBy}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className={styles.track} aria-hidden="true">
        <span className={styles.thumb} />
      </span>
      <span className={styles.text}>{label}</span>
    </label>
  );
}
