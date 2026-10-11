import styles from "./Advantage.module.css";

/** The span an axis covers, in the units of the numbers drawn on it. */
export interface RangeScale {
  min: number;
  max: number;
}

/**
 * A scale that holds every range given, with zero always inside and a little room at both ends, so a
 * row of range bars shares one axis and can be compared by eye.
 */
export function scaleFor(ranges: readonly { low: number; high: number }[]): RangeScale {
  const min = Math.min(0, ...ranges.map((r) => r.low));
  const max = Math.max(0, ...ranges.map((r) => r.high));
  const pad = Math.max(max - min, 1e-9) * 0.08;
  return { min: min - pad, max: max + pad };
}

/**
 * One advantage as a point with its 90% range on a shared axis, zero marked. It repeats what the
 * text beside it says (the numbers are all written out), so it is hidden from screen readers.
 */
export function RangeBar({
  value,
  low,
  high,
  scale,
  compact = false,
}: {
  value: number;
  low: number;
  high: number;
  scale: RangeScale;
  /** A shorter bar, for a table cell. */
  compact?: boolean;
}) {
  const span = scale.max - scale.min || 1;
  const at = (x: number) => `${((x - scale.min) / span) * 100}%`;
  return (
    <div className={styles.rangeBar} data-compact={compact || undefined} aria-hidden="true">
      <span className={styles.rangeTrack} />
      <span className={styles.rangeSpan} style={{ left: at(low), width: `${((high - low) / span) * 100}%` }} />
      <span className={styles.rangeZero} style={{ left: at(0) }} />
      <span className={styles.rangeZeroLabel} style={{ left: at(0) }}>
        0%
      </span>
      <span className={styles.rangePoint} style={{ left: at(value) }} />
    </div>
  );
}
