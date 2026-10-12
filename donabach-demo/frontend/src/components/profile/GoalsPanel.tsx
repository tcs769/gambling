import { Panel, PanelTitle, Tag } from "@/components/ui";
import { dollars } from "@/lib/format";
import type { HouseholdProfile } from "@/lib/types";
import styles from "./Profile.module.css";

export function GoalsPanel({ profile }: { profile: HouseholdProfile }) {
  // The API's goal lines leave out charitable giving; the household's own goals have it (only listed when there is some).
  const giving = profile.household.goals?.charitable_giving ?? 0;
  return (
    <Panel as="section" aria-label="Goals">
      <PanelTitle>Goals</PanelTitle>
      <ul className={styles.list}>
        {profile.goals.map((goal) => (
          <li key={goal.label} className={styles.item}>
            <span className={styles.name}>
              {goal.label}
              {goal.estimated && <Tag tone="gold">Estimated</Tag>}
            </span>
            <span className={styles.detail}>{goal.detail}</span>
          </li>
        ))}
        {giving > 0 && (
          <li className={styles.item}>
            <span className={styles.name}>Charitable giving</span>
            <span className={styles.detail}>{dollars(giving)} a year</span>
          </li>
        )}
      </ul>
    </Panel>
  );
}
