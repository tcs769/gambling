import styles from "./Spinner.module.css";

export function Spinner({ size = 18, label }: { size?: number; label?: string }) {
  return (
    <span className={styles.wrap} role="status">
      <span className={styles.spinner} style={{ width: size, height: size }} aria-hidden="true" />
      {label && <span>{label}</span>}
    </span>
  );
}
