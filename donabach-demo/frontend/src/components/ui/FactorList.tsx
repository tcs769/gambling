import type { Factor } from "@/lib/types";
import styles from "./FactorList.module.css";

/** "wages_total" -> "Wages total": the model's feature names, made readable. */
export function featureLabel(feature: string): string {
  const spaced = feature.replace(/[_-]+/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function Arrow({ direction }: { direction: "up" | "down" }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={direction === "up" ? "M12 19V5m0 0l-6 6m6-6l6 6" : "M12 5v14m0 0l-6-6m6 6l6-6"} />
    </svg>
  );
}

/**
 * The top factors a model reported: the input's name, which way it pushes (arrow and words, never
 * color alone) and a bar for its relative importance. Everything shown comes from the model.
 */
export function FactorList({
  factors,
  upText,
  downText,
  label,
}: {
  factors: readonly Factor[];
  /** What "up" means here, e.g. "pushes income up". */
  upText: string;
  downText: string;
  /** Names the list for screen readers. */
  label: string;
}) {
  return (
    <ul className={styles.list} aria-label={label}>
      {factors.map((factor) => (
        <li key={factor.feature} className={styles.row}>
          <span className={styles.name}>{featureLabel(factor.feature)}</span>
          <span className={styles.direction}>
            <Arrow direction={factor.direction} />
            {factor.direction === "up" ? upText : downText}
          </span>
          <span
            className={styles.bar}
            role="img"
            aria-label={`Relative importance ${factor.weight.toFixed(2)} out of 1`}
          >
            <span className={styles.fill} style={{ width: `${Math.max(0, Math.min(1, factor.weight)) * 100}%` }} />
          </span>
          <span className={styles.weight}>{factor.weight.toFixed(2)}</span>
        </li>
      ))}
    </ul>
  );
}
