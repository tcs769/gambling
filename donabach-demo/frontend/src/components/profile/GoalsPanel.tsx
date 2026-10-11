import { Panel, PanelTitle, Tag } from "@/components/ui";
import type { HouseholdProfile } from "@/lib/types";
import styles from "./Profile.module.css";

export function GoalsPanel({ profile }: { profile: HouseholdProfile }) {
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
      </ul>
    </Panel>
  );
}
