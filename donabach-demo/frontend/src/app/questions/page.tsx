"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Icon, PageHeader, Panel, PanelTitle, Tag } from "@/components/ui";
import { ChoiceRow, type Choice } from "@/components/questions/ChoiceRow";
import {
  CASH_BALANCES,
  CHARITABLE_GIVING,
  COLLEGE_COST_A_YEAR,
  COLLEGE_IN_YEARS,
  HOME_DOWN_PAYMENT,
  HOME_IN_YEARS,
  RETIREMENT_AGES,
  RETIREMENT_SPENDING,
  ROTH_BALANCES,
  SOCIAL_SECURITY_A_YEAR,
} from "@/components/questions/options";
import styles from "@/components/questions/Questions.module.css";
import { useReadyDocuments } from "@/components/review/useDocuments";
import { money, years } from "@/lib/format";
import { useApp } from "@/lib/state";

const inYears = (values: readonly (number | null)[]): Choice<number | null>[] =>
  values.map((value) => ({ value, label: value === null ? "None" : `In ${years(value)}` }));
const amounts = (values: readonly number[]): Choice<number>[] =>
  values.map((value) => ({ value, label: money(value) }));

export default function QuestionsPage() {
  const { state, actions } = useApp();
  const router = useRouter();
  const { phase, retry } = useReadyDocuments();
  const [building, setBuilding] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const { answers } = state;

  const build = async () => {
    setBuilding(true);
    setMessage(null);
    const result = await actions.buildHousehold();
    if (result.ok) {
      router.push("/profile"); // stays busy until the next screen takes over
      return;
    }
    setBuilding(false);
    // Numbers the documents did not give: Review is where they get fixed.
    if (result.missing.length > 0) router.push("/review");
    else setMessage(result.message);
  };

  const noHome = answers.home_purchase_in_years === null;
  const noCollege = answers.college_starts_in_years === null;

  return (
    <>
      <PageHeader
        title="A few questions"
        subtitle="Your documents show what you have. Tell us what you are saving for, and we will estimate the rest."
        actions={
          <Button arrow busy={building} disabled={phase !== "ready"} onClick={build}>
            Build my profile
          </Button>
        }
      />

      {(message || phase === "failed") && (
        <div className={styles.alert} role="alert">
          <Icon name="alert" size={20} />
          <div>
            {phase === "failed" && !message ? (
              <>
                <p>We could not load the documents{state.error ? `: ${state.error}` : "."}</p>
                <Button variant="secondary" onClick={retry}>
                  Try again
                </Button>
              </>
            ) : (
              <p>We could not build your profile: {message}</p>
            )}
          </div>
        </div>
      )}

      <div className={styles.grid}>
        <Panel>
          <PanelTitle aside="Choose one for each">Your goals</PanelTitle>

          <section className={styles.topic} aria-labelledby="topic-home">
            <h3 id="topic-home" className={styles.topicTitle}>
              Buying a home
            </h3>
            <div className={styles.rows}>
              <ChoiceRow
                label="When would you like to buy?"
                choices={inYears(HOME_IN_YEARS)}
                value={answers.home_purchase_in_years}
                onChange={(value) => actions.setAnswers({ home_purchase_in_years: value })}
              />
              <ChoiceRow
                label="How much will you put down?"
                choices={amounts(HOME_DOWN_PAYMENT)}
                value={answers.home_down_payment}
                onChange={(value) => actions.setAnswers({ home_down_payment: value })}
                custom={{ prefix: "$" }}
                disabled={noHome}
              />
            </div>
          </section>

          <section className={styles.topic} aria-labelledby="topic-college">
            <h3 id="topic-college" className={styles.topicTitle}>
              College
            </h3>
            <div className={styles.rows}>
              <ChoiceRow
                label="When does college start?"
                choices={inYears(COLLEGE_IN_YEARS)}
                value={answers.college_starts_in_years}
                onChange={(value) => actions.setAnswers({ college_starts_in_years: value })}
              />
              <ChoiceRow
                label="What will it cost each year?"
                hint={`For ${years(answers.college_years)}`}
                choices={amounts(COLLEGE_COST_A_YEAR)}
                value={answers.college_annual_cost}
                onChange={(value) => actions.setAnswers({ college_annual_cost: value })}
                custom={{ prefix: "$" }}
                disabled={noCollege}
              />
            </div>
          </section>

          <section className={styles.topic} aria-labelledby="topic-retirement">
            <h3 id="topic-retirement" className={styles.topicTitle}>
              Retirement
            </h3>
            <div className={styles.rows}>
              <ChoiceRow
                label="At what age would you like to retire?"
                choices={RETIREMENT_AGES.map((value) => ({ value, label: String(value) }))}
                value={answers.retirement_age}
                onChange={(value) => actions.setAnswers({ retirement_age: value })}
              />
              <ChoiceRow
                label="How much will you spend each year?"
                hint="In today's dollars, before tax"
                choices={amounts(RETIREMENT_SPENDING)}
                value={answers.retirement_spending}
                onChange={(value) => actions.setAnswers({ retirement_spending: value })}
                custom={{ prefix: "$" }}
              />
            </div>
          </section>

          <section className={styles.topic} aria-labelledby="topic-giving">
            <h3 id="topic-giving" className={styles.topicTitle}>
              Giving
            </h3>
            <div className={styles.rows}>
              <ChoiceRow
                label="Charitable giving a year"
                help="Donabach gives shares that have gained the most instead of cash, so that gain is never taxed. Without itemizing, a couple deducts at most $2,000 of cash gifts."
                choices={amounts(CHARITABLE_GIVING)}
                value={answers.charitable_giving}
                onChange={(value) => actions.setAnswers({ charitable_giving: value })}
                custom={{ prefix: "$" }}
              />
            </div>
          </section>
        </Panel>

        <div className={styles.stack}>
          <Panel className={styles.stacked}>
            <PanelTitle aside={<Tag tone="gold">Estimated</Tag>}>Not in your documents</PanelTitle>
            <p className={styles.intro}>
              These are not on your statements, so we start from an estimate. Change any that look off.
            </p>
            <div className={styles.rows}>
              <ChoiceRow
                label="Roth IRA balance"
                estimated
                choices={amounts(ROTH_BALANCES)}
                value={answers.roth_balance}
                onChange={(value) => actions.setAnswers({ roth_balance: value })}
                custom={{ prefix: "$" }}
              />
              <ChoiceRow
                label="Cash savings"
                estimated
                choices={amounts(CASH_BALANCES)}
                value={answers.cash}
                onChange={(value) => actions.setAnswers({ cash: value })}
                custom={{ prefix: "$" }}
              />
              <ChoiceRow
                label="Social Security a year"
                hint={`For the household, from age ${answers.social_security_start_age}`}
                estimated
                choices={amounts(SOCIAL_SECURITY_A_YEAR)}
                value={answers.social_security_annual}
                onChange={(value) => actions.setAnswers({ social_security_annual: value })}
                custom={{ prefix: "$" }}
              />
            </div>
          </Panel>

          <Panel tone="plain" className={styles.next}>
            <h2>What happens next</h2>
            <p>
              We combine your documents with these answers to build your household profile: balances by account, this
              year&apos;s tax picture, and your goals.
            </p>
          </Panel>
        </div>
      </div>
    </>
  );
}
