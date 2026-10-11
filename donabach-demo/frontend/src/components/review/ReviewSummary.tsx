import { Button, ButtonLink, Icon } from "@/components/ui";
import styles from "./Review.module.css";

interface Props {
  /** Numbers read across all documents. */
  total: number;
  documents: number;
  /** Numbers the parser flagged, and how many of those still wait on the user. */
  flagged: number;
  unresolved: number;
  onShow: () => void;
}

/** The status at the top of the list: how many numbers, and what (if anything) needs a look. */
export function ReviewSummary({ total, documents, flagged, unresolved, onShow }: Props) {
  const read = `We read ${total} ${total === 1 ? "number" : "numbers"} from ${documents} ${documents === 1 ? "document" : "documents"}.`;
  if (total === 0 && unresolved === 0) {
    return (
      <div className={styles.summary} data-tone="warn">
        <span className={styles.summaryIcon} aria-hidden="true">
          <Icon name="alert" size={22} />
        </span>
        <div className={styles.summaryText}>
          <p className={styles.summaryTitle}>We could not read any numbers</p>
          <p className={styles.summaryBody}>
            The demo reads its three sample templates, and these documents are not among them.
          </p>
        </div>
        <ButtonLink href="/" variant="secondary">
          Back to upload
        </ButtonLink>
      </div>
    );
  }
  if (unresolved > 0) {
    return (
      <div className={styles.summary} data-tone="warn">
        <span className={styles.summaryIcon} aria-hidden="true">
          <Icon name="alert" size={22} />
        </span>
        <div className={styles.summaryText}>
          <p className={styles.summaryTitle}>
            {unresolved} {unresolved === 1 ? "number needs" : "numbers need"} a look
          </p>
          <p className={styles.summaryBody}>{read} Everything else passed our checks.</p>
        </div>
        <Button variant="secondary" onClick={onShow}>
          Show me
        </Button>
      </div>
    );
  }
  return (
    <div className={styles.summary} data-tone="good">
      <span className={styles.summaryIcon} aria-hidden="true">
        <Icon name="check" size={22} strokeWidth={2.6} />
      </span>
      <div className={styles.summaryText}>
        <p className={styles.summaryTitle}>
          {flagged > 0 ? "Every number is confirmed" : "Every number passed our checks"}
        </p>
        <p className={styles.summaryBody}>
          {read}
          {flagged > 0 ? ` You checked the ${flagged} we flagged.` : ""}
        </p>
      </div>
    </div>
  );
}
