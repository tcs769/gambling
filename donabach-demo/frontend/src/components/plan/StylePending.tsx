import { Button, Icon, Spinner } from "@/components/ui";
import type { AltStyle, StyleSlot } from "@/lib/state";
import { STYLE_NAME } from "./styles";
import styles from "./StylePending.module.css";

/**
 * What stands in for a plan in another planning style while it is being searched for (a spinner and a line on how long that
 * takes), or when the API refused (its message, and a way to ask again). It is the content of one column, or of one panel.
 */
export function StylePending({
  style,
  slot,
  onRetry,
}: {
  style: AltStyle;
  slot: Exclude<StyleSlot, { status: "ready" }>;
  onRetry: () => void;
}) {
  const name = STYLE_NAME[style];
  if (slot.status === "failed") {
    return (
      <div className={styles.failure} role="alert">
        <Icon name="alert" size={20} className={styles.icon} />
        <div>
          <div className={styles.title}>The {name.toLowerCase()} plan could not be made</div>
          <p>{slot.message}</p>
          <Button variant="secondary" onClick={onRetry} aria-label={`Try again, ${name} plan`}>
            Try again
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className={styles.loading}>
      <Spinner label={`Planning in the ${name.toLowerCase()} style…`} />
      <p>The search takes several seconds. The plans that are already here stay usable while this one is worked out.</p>
    </div>
  );
}
