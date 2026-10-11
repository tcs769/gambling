import { Icon, Panel, Pill } from "@/components/ui";
import { CHOICE_LABELS, OPTION_LABELS, type PlanResponse } from "@/lib/types";
import styles from "./Plan.module.css";

/** The five choices of a strategy as small labelled chips: "Stock share · 70% stocks". */
export function ChoiceChips({ choices, label }: { choices: Record<string, string>; label: string }) {
  return (
    <ul className={styles.choices} aria-label={label}>
      {Object.keys(CHOICE_LABELS).map((choice) => {
        const option = choices[choice];
        if (option === undefined) return null;
        const isOn = option === "on";
        return (
          <li key={choice} className={styles.choice} data-off={option === "off"}>
            <span className={styles.choiceLabel}>{CHOICE_LABELS[choice]}</span>
            <span className={styles.choiceValue}>
              {isOn && <Icon name="check" size={15} strokeWidth={2.8} />}
              {OPTION_LABELS[choice]?.[option] ?? option}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** The top card: the strategy in one sentence, why, who chose it, and its five choices. */
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
      <ChoiceChips choices={plan.strategy.choices} label="The five choices in this strategy" />
    </Panel>
  );
}
