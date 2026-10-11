"use client";

import { useApp } from "@/lib/state";
import styles from "./DemoToggle.module.css";

export function DemoToggle() {
  const { state, actions } = useApp();
  return (
    <label
      className={styles.toggle}
      title="Preloads the sample documents and fixes the random seed, so every run shows the same numbers."
    >
      <span className={styles.text}>Demo mode</span>
      <input
        type="checkbox"
        role="switch"
        className={styles.input}
        checked={state.demoMode}
        onChange={(e) => actions.setDemoMode(e.target.checked)}
      />
      <span className={styles.track} aria-hidden="true">
        <span className={styles.thumb} />
      </span>
    </label>
  );
}
