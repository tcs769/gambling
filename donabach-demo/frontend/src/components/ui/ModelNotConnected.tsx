import type { ReactNode } from "react";
import { Icon } from "./Icon";
import styles from "./ModelNotConnected.module.css";

/**
 * What the app shows wherever a machine-learning model is not plugged in. It never stands in for a
 * prediction: no numbers, no bars, just the state and where the model file goes.
 */
export function ModelNotConnected({
  model,
  reason,
  children,
}: {
  model: string;
  reason?: string | null;
  children?: ReactNode;
}) {
  return (
    <div className={styles.box} role="status">
      <Icon name="plug" size={22} className={styles.icon} />
      <div>
        <div className={styles.title}>Model not connected</div>
        <p className={styles.text}>
          {children ?? `The ${model} model is not plugged in yet, so nothing is shown here in its place.`}
        </p>
        {reason && <p className={styles.reason}>{reason}</p>}
      </div>
    </div>
  );
}
