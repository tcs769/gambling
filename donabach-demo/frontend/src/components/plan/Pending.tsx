import { Button, Icon, Panel, Spinner } from "@/components/ui";
import type { EnsureStatus } from "./useEnsure";
import styles from "./Pending.module.css";

/**
 * What a results screen shows before its numbers exist: panels at roughly the real sizes (so the
 * page does not jump when the result lands) with a spinner, or the API's error with a retry.
 */
export function Pending({
  status,
  error,
  retry,
  label,
  blocks,
  tail = 0,
}: {
  status: EnsureStatus;
  error?: string;
  retry: () => void;
  label: string;
  /** Heights, in pixels, of the panels the finished screen will have. */
  blocks: number[];
  /** Height of the row of buttons that follows the panels, if any. */
  tail?: number;
}) {
  const failed = status === "failed" && !!error;
  return (
    <div className={styles.stack}>
      {blocks.map((height, i) => (
        <Panel key={i} className={styles.block} style={{ minHeight: height }} aria-busy={!failed}>
          {i === 0 &&
            (failed ? (
              <div className={styles.failure} role="alert">
                <Icon name="alert" size={22} className={styles.failureIcon} />
                <div>
                  <div className={styles.failureTitle}>Something went wrong</div>
                  <p>{error}</p>
                  <Button variant="secondary" onClick={retry}>
                    Try again
                  </Button>
                </div>
              </div>
            ) : (
              <Spinner label={label} />
            ))}
        </Panel>
      ))}
      {tail > 0 && <div style={{ height: tail }} aria-hidden="true" />}
    </div>
  );
}
