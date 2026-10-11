import { Icon, Panel, Pill } from "@/components/ui";
import { CHOICE_LABELS, chipValue, optionIsOff, optionLabel, type PlanResponse } from "@/lib/types";
import styles from "./Plan.module.css";

/**
 * A strategy's choices as small labelled chips: "Stock share · 70% stocks", "401(k) contributions · Roth".
 * Every choice the API sends is shown (a key this app has no name for keeps its raw name), in the order
 * of CHOICE_LABELS. With `changed` (a choice mapped to the option it had before) those chips are marked, in words
 * as well as in look: "was Off".
 */
export function ChoiceChips({
  choices,
  label,
  changed,
}: {
  choices: Record<string, string>;
  label: string;
  changed?: Record<string, string | undefined>;
}) {
  const known = Object.keys(CHOICE_LABELS).filter((choice) => choices[choice] !== undefined);
  const unknown = Object.keys(choices).filter((choice) => !(choice in CHOICE_LABELS));
  return (
    <ul className={styles.choices} aria-label={label}>
      {[...known, ...unknown].map((choice) => {
        const option = choices[choice];
        const isChanged = !!changed && choice in changed;
        const was = changed?.[choice];
        return (
          <li key={choice} className={styles.choice} data-off={optionIsOff(choice, option)} data-changed={isChanged || undefined}>
            <span className={styles.choiceLabel}>{CHOICE_LABELS[choice] ?? choice}</span>
            <span className={styles.choiceValue}>
              {option === "on" && <Icon name="check" size={15} strokeWidth={2.8} />}
              {chipValue(choices, choice)}
            </span>
            {isChanged && (
              <span className={styles.choiceWas}>{was === undefined ? "Changed" : `Changed, was ${optionLabel(choice, was)}`}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** The top card: the strategy in one sentence (the API's own), why, who chose it, and its choices. */
export function StrategyCard({ plan }: { plan: PlanResponse }) {
  return (
    <Panel className={styles.strategy} aria-labelledby="strategy-sentence">
      <div className={styles.kicker}>
        <Pill tone="gold" icon={<Icon name="info" size={14} />}>
          {plan.planner_label}
        </Pill>
      </div>
      <h2 id="strategy-sentence" className={styles.sentence}>
        {plan.strategy.sentence}
      </h2>
      <p className={styles.reason}>
        <strong>Why this plan.</strong> {plan.reason}
      </p>
      <ChoiceChips choices={plan.strategy.choices} label="The choices in this strategy" />
    </Panel>
  );
}
