import { Button, PageHeader, Panel } from "@/components/ui";
import styles from "./Review.module.css";

/** The Review layout with the content greyed out, while the sample documents load. */
export function ReviewSkeleton() {
  return (
    <div aria-busy="true">
      <PageHeader
        title="Review extracted numbers"
        subtitle="Check what we read from your documents. Choose any number to see where it came from."
        actions={
          <Button arrow disabled>
            Confirm and continue
          </Button>
        }
      />
      <div className={styles.split}>
        <div className={styles.fields}>
          <div className={styles.bone} style={{ height: 102, borderRadius: 14 }} />
          <Panel>
            <div className={styles.bone} style={{ height: 44, width: "55%", marginBottom: 16 }} />
            {Array.from({ length: 7 }, (_, i) => (
              <div key={i} className={styles.skeletonRow}>
                <div className={styles.bone} style={{ height: 20, width: `${38 + ((i * 13) % 30)}%` }} />
                <div className={styles.bone} style={{ height: 20, width: 110 }} />
              </div>
            ))}
          </Panel>
        </div>
        <div className={styles.viewerColumn}>
          <div className={styles.bone} style={{ height: "100%", borderRadius: 14 }} />
        </div>
      </div>
    </div>
  );
}
