import type { Plan } from "@/lib/portal-types";
import styles from "./GoalsTab.module.css";

type Goals = Plan["portfolio"]["goals"];

export function GoalsTab({ goals }: { goals: Goals }) {
  return (
    <ul className={styles.cards} data-testid="goal-cards">
      {goals.cards.map((card) => (
        <li key={card.key} className={styles.card} data-goal={card.key}>
          <h2 className={styles.label}>{card.label}</h2>
          <p className={`${styles.target} num`}>{card.target_label}</p>
          <p className={styles.timing}>{card.timing}</p>
          <div
            className={styles.track}
            role="progressbar"
            aria-label={`${card.label} progress`}
            aria-valuemin={0}
            aria-valuemax={1}
            aria-valuenow={card.progress}
            aria-valuetext={card.status}
          >
            <span className={styles.fill} data-status={card.status} style={{ width: `${card.progress * 100}%` }} />
          </div>
          <p className={styles.status} data-status={card.status}>
            {card.status}
          </p>
        </li>
      ))}
    </ul>
  );
}
