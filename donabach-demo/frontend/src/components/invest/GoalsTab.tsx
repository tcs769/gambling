import type { Plan } from "@/lib/portal-types";
import styles from "./GoalsTab.module.css";
import t from "./invest.module.css";

type Goals = Plan["portfolio"]["goals"];

export function GoalsTab({ goals }: { goals: Goals }) {
  return (
    <ul className={styles.goals} data-testid="goal-cards">
      {goals.cards.map((card) => (
        <li key={card.key} className={`${t.panel} ${styles.goal}`} data-goal={card.key}>
          <h2 className={styles.gt}>{card.label}</h2>
          <p className={styles.gs}>{card.timing}</p>
          <div
            className={styles.prog}
            role="progressbar"
            aria-label={`${card.label} progress`}
            aria-valuemin={0}
            aria-valuemax={1}
            aria-valuenow={card.progress}
            aria-valuetext={card.status}
          >
            <i data-status={card.status} style={{ width: `${card.progress * 100}%` }} />
          </div>
          <div className={styles.gf}>
            <b className="num">{card.target_label}</b>
            <span data-status={card.status}>{card.status}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
