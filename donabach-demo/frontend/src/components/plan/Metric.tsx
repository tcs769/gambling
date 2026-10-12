import type { ReactNode } from "react";
import styles from "./StyleFigures.module.css";

/** One figure in a definition list: its name, its value, and a line under it. */
export function Metric({ label, figure, detail }: { label: ReactNode; figure: ReactNode; detail?: ReactNode }) {
  return (
    <div className={styles.metric}>
      <dt>{label}</dt>
      <dd className={styles.figure}>{figure}</dd>
      {detail && <dd className={styles.detail}>{detail}</dd>}
    </div>
  );
}
