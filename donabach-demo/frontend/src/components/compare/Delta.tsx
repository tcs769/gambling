import styles from "./Compare.module.css";

function Arrow({ up }: { up: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={up ? "M12 19V5m0 0l-6 6m6-6l6 6" : "M12 5v14m0 0l-6-6m6 6l6-6"} />
    </svg>
  );
}

/**
 * How a number moved against the base plan when a what-if is on screen: an arrow and the words
 * "up" or "down" (never color alone), green when the move is good for the household, red when not.
 */
export function Delta({
  change,
  goodWhen,
  format,
}: {
  /** New value minus the base plan's value. */
  change: number;
  /** Which direction is good news for this number. */
  goodWhen: "up" | "down";
  format: (absoluteChange: number) => string;
}) {
  if (Math.abs(change) < 0.5) {
    return <span className={styles.delta}>No change from your plan</span>;
  }
  const up = change > 0;
  return (
    <span className={styles.delta} data-tone={(goodWhen === "up") === up ? "good" : "bad"}>
      <Arrow up={up} />
      {up ? "Up" : "Down"} {format(Math.abs(change))} from your plan
    </span>
  );
}
