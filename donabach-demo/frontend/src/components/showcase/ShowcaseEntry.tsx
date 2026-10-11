import { ButtonLink } from "@/components/ui";
import styles from "./ShowcaseEntry.module.css";

/**
 * The way into the showcase from the home page: a household, the strategies that earn its advantage over a good advisor,
 * and the wealth they build, in three screens that need no documents.
 */
export function ShowcaseEntry() {
  return (
    <aside className={styles.entry} aria-label="The showcase">
      <div className={styles.text}>
        <p className={styles.title}>Short on time? See it in three screens.</p>
        <p className={styles.lede}>
          A household&apos;s savings, the strategies that earn Donabach its advantage over a good advisor, and the
          wealth that builds. No documents needed.
        </p>
      </div>
      <ButtonLink href="/showcase" variant="secondary" arrow>
        Open the showcase
      </ButtonLink>
    </aside>
  );
}
