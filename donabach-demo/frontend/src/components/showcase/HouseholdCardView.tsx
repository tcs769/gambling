import { Icon, Panel } from "@/components/ui";
import { dollars } from "@/lib/format";
import type { HouseholdCard } from "@/lib/types";
import { GoalsTimeline } from "./GoalsTimeline";
import { SavingsBar } from "./SavingsBar";
import { childrenText } from "./text";
import styles from "./HouseholdCardView.module.css";

/**
 * One card for the whole household: who they are and what they earn and have saved, where the savings sit, what
 * they are saving for, and what stands out. Everything on it is the API's (`card`), so any household reads the same
 * way: one earner or two, children or none, a goal or two or four, a note or none.
 */
export function HouseholdCardView({ card, horizonAge }: { card: HouseholdCard; horizonAge: number }) {
  const startAge = card.people[0]?.age;
  return (
    <Panel as="article" className={styles.card} aria-label="Household summary">
      <section className={styles.who} aria-labelledby="card-people">
        <div>
          <h2 id="card-people" className={styles.sectionTitle}>
            Who they are
          </h2>
          <ul className={styles.people}>
            {card.people.map((person, i) => (
              <li key={i} className={styles.person}>
                <span className={styles.personName}>{person.label}</span>
                <span className={styles.personMeta}>Age {person.age}</span>
                <span className={`${styles.wages} num`}>
                  {dollars(person.wages)}
                  <span className={styles.per}> a year in wages</span>
                </span>
              </li>
            ))}
            <li className={styles.person}>
              <span className={styles.personName}>{childrenText(card.children_ages)}</span>
            </li>
          </ul>
        </div>
        <dl className={styles.figures}>
          <div className={styles.figure}>
            <dt>Household income</dt>
            <dd>
              {dollars(card.annual_income)}
              <span className={styles.per}> a year</span>
            </dd>
          </div>
          <div className={styles.figure}>
            <dt>Total saved</dt>
            <dd>{dollars(card.total_savings)}</dd>
          </div>
        </dl>
      </section>

      <section className={styles.section} aria-labelledby="card-savings">
        <h2 id="card-savings" className={styles.sectionTitle}>
          Where the savings are
        </h2>
        <SavingsBar accounts={card.accounts} total={card.total_savings} />
      </section>

      <section className={styles.section} aria-labelledby="card-goals">
        <h2 id="card-goals" className={styles.sectionTitle}>
          What they are saving for
        </h2>
        <GoalsTimeline goals={card.goals} startAge={startAge} endAge={horizonAge} />
      </section>

      {card.notes.length > 0 && (
        <section className={styles.section} aria-labelledby="card-notes">
          <h2 id="card-notes" className={styles.sectionTitle}>
            What stands out
          </h2>
          <ul className={styles.notes}>
            {card.notes.map((note) => (
              <li key={note}>
                <Icon name="info" size={20} className={styles.noteIcon} />
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Panel>
  );
}
