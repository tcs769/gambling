import { Panel } from "@/components/ui";
import styles from "./Profile.module.css";

/** The profile's frames with the content greyed out, while the household is being built. */
export function ProfileSkeleton() {
  return (
    <div aria-busy="true">
      <div className={styles.summary}>
        {[4, 4, 3].map((rows, p) => (
          <Panel key={p} className={styles.bonePanel}>
            <span className={styles.bone} style={{ height: 28, width: "55%", marginBottom: 8 }} />
            {Array.from({ length: rows }, (_, i) => (
              <div key={i} className={styles.boneRow}>
                <span className={styles.bone} style={{ height: 22, width: `${40 + ((i * 17) % 25)}%` }} />
                <span className={styles.bone} style={{ height: 22, width: 90 }} />
              </div>
            ))}
          </Panel>
        ))}
      </div>
      <div className={styles.sectionHead}>
        <span className={styles.bone} style={{ height: 30, width: 260 }} />
      </div>
      <div className={styles.cards}>
        {Array.from({ length: 7 }, (_, i) => (
          <div key={i} className={`${styles.bone} ${styles.boneCard} ${i === 4 ? styles.wide : ""}`} />
        ))}
      </div>
    </div>
  );
}
