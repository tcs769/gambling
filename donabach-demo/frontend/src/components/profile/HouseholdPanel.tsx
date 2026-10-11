import { Panel, PanelTitle } from "@/components/ui";
import { dollars } from "@/lib/format";
import type { HouseholdProfile } from "@/lib/types";
import styles from "./Profile.module.css";

/** Who is in the household, as the documents describe them. */
export function HouseholdPanel({ profile }: { profile: HouseholdProfile }) {
  const { people, children_ages: kids = [] } = profile.household;
  const roles = ["Taxpayer", "Spouse"];
  return (
    <Panel as="section" aria-label="Your household">
      <PanelTitle>Your household</PanelTitle>
      <ul className={styles.list}>
        {people.map((person, i) => (
          <li key={i} className={styles.person}>
            <span className={styles.name}>
              {person.name || roles[i] || `Person ${i + 1}`}, age {person.age}
            </span>
            <span className={styles.detail}>
              Wages {dollars(person.wages)} a year
              {person.pretax_401k > 0 ? `, saving ${dollars(person.pretax_401k)} to a 401(k)` : ""}
            </span>
          </li>
        ))}
        <li className={styles.person}>
          <span className={styles.name}>
            {kids.length === 0 ? "No children" : kids.length === 1 ? "1 child" : `${kids.length} children`}
          </span>
          {kids.length > 0 && (
            <span className={styles.detail}>{kids.length === 1 ? `Age ${kids[0]}` : `Ages ${kids.join(", ")}`}</span>
          )}
        </li>
      </ul>
    </Panel>
  );
}
