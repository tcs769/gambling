"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Choices, type Choice } from "@/components/portal/Choices";
import { Screen } from "@/components/portal/Screen";
import { useGuard } from "@/components/portal/useGuard";
import { Icon, NumberInput } from "@/components/ui";
import { portalApi } from "@/lib/portal-api";
import { usePortal } from "@/lib/portal-state";
import type { IncomeChange, PortalAnswers } from "@/lib/portal-types";
import styles from "./Goals.module.css";

const RETIREMENT_AGES = [60, 62, 65, 67];
const HOME_YEARS = [3, 5];
/** The down payment a home purchase starts with when the customer picks one. */
const HOME_DOWN_PAYMENT = 150_000;
const INCOME_CHOICES: { id: IncomeChange; label: string }[] = [
  { id: "none", label: "No" },
  { id: "job_loss", label: "Job loss next year" },
  { id: "raise", label: "A raise" },
];

const plural = (n: number, unit: string) => `${n} ${unit}${n === 1 ? "" : "s"}`;

export default function GoalsPage() {
  const { state, actions, investing } = usePortal();
  const router = useRouter();
  const ready = useGuard("goals");
  const [defaults, setDefaults] = useState<PortalAnswers | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const answers = state.answers;
  const { setAnswers } = actions;

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    portalApi
      .defaults()
      .then((d) => {
        if (cancelled) return;
        setDefaults(d);
        if (!state.answers) setAnswers(d);
      })
      .catch((e: unknown) => !cancelled && setLoadError(e instanceof Error ? e.message : "Something went wrong."));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the defaults are fetched once, when the screen opens
  }, [ready]);

  useEffect(() => {
    router.prefetch("/invest");
  }, [router]);

  if (!ready) return null;
  if (!answers || !defaults) {
    return (
      <Screen title="A few questions" back={{ onClick: () => router.push("/review") }}>
        {loadError ? (
          <p className={styles.error} role="alert">
            {loadError}
          </p>
        ) : (
          <p className="muted" role="status">
            Loading…
          </p>
        )}
      </Screen>
    );
  }

  const set = (patch: Partial<PortalAnswers>) => setAnswers({ ...answers, ...patch });
  const busy = investing.busy;

  // --- retirement age: 60, 62, 65, 67; the API's own value is one more chip when it is not among them
  const ages = [...new Set([...RETIREMENT_AGES, answers.retirement_age])].sort((x, y) => x - y);
  const ageOptions: Choice[] = ages.map((a) => ({ id: String(a), label: String(a) }));

  // --- college: starts in N years (the API's value), or not planned
  const johnCollege = defaults.college_starts_in_years ?? null;
  const collegeChoice = answers.college_starts_in_years == null ? "no" : "yes";
  const collegeOptions: Choice[] = [
    ...(johnCollege !== null ? [{ id: "yes", label: `Starts in ${plural(johnCollege, "year")}` }] : []),
    { id: "no", label: "Not planned" },
  ];

  // --- buying a home: no plans, within 3 years, within 5 years (a value from before that matches neither shows as its own chip)
  const homeYears = answers.home_purchase_in_years ?? null;
  const homeList = [...new Set([...HOME_YEARS, ...(homeYears !== null ? [homeYears] : [])])].sort((x, y) => x - y);
  const homeOptions: Choice[] = [
    { id: "none", label: "No plans" },
    ...homeList.map((n) => ({ id: String(n), label: `Within ${plural(n, "year")}` })),
  ];
  const homeChoice = homeYears === null ? "none" : String(homeYears);

  const invest = () => {
    void actions
      .invest()
      .then(() => router.push("/invest"))
      .catch(() => undefined); // shown below
  };

  return (
    <Screen
      title="A few questions"
      lede="Your documents can't tell us these."
      back={{ onClick: () => router.push("/review") }}
      next={{ label: "Invest", onClick: invest, busy }}
    >
      <div className={styles.questions}>
        <Choices
          name="retirement_age"
          legend="When do you want to retire?"
          options={ageOptions}
          value={String(answers.retirement_age)}
          onChange={(id) => set({ retirement_age: Number(id) })}
        />

        <Choices
          name="college"
          legend="College for your child"
          options={collegeOptions}
          value={collegeChoice}
          onChange={(id) => {
            if (id === "no") set({ college_starts_in_years: null });
            else if (answers.college_starts_in_years == null)
              set({
                college_starts_in_years: defaults.college_starts_in_years,
                college_annual_cost: defaults.college_annual_cost,
                college_years: defaults.college_years ?? 4,
              });
          }}
        />

        <Choices
          name="home_purchase"
          legend="Buying a home?"
          options={homeOptions}
          value={homeChoice}
          onChange={(id) => {
            if (id === "none") set({ home_purchase_in_years: null, home_down_payment: defaults.home_down_payment });
            else {
              const down = homeYears !== null ? (answers.home_down_payment ?? HOME_DOWN_PAYMENT) : HOME_DOWN_PAYMENT;
              set({ home_purchase_in_years: Number(id), home_down_payment: down });
            }
          }}
        >
          {homeYears !== null && (
            <div className={styles.moneyIn}>
              <label htmlFor="down-payment">Down payment</label>
              <span>$</span>
              <NumberInput
                id="down-payment"
                className={styles.input}
                value={Math.round(answers.home_down_payment ?? HOME_DOWN_PAYMENT)}
                min={0}
                inputMode="numeric"
                onCommit={(v) => set({ home_down_payment: v })}
              />
            </div>
          )}
        </Choices>

        <Choices
          name="income_change"
          legend="Any income changes coming?"
          options={INCOME_CHOICES}
          value={answers.income_change ?? "none"}
          onChange={(id) => set({ income_change: id as IncomeChange })}
        />

        <div className={`${styles.q} ${styles.last}`}>
          <label htmlFor="spend" className={styles.qt}>
            Yearly spending in retirement
          </label>
          <div className={styles.moneyIn}>
            <span>$</span>
            <NumberInput
              id="spend"
              className={styles.input}
              value={Math.round(answers.retirement_spending)}
              min={0}
              inputMode="numeric"
              onCommit={(v) => set({ retirement_spending: v })}
            />
          </div>
        </div>
      </div>

      {busy && (
        <p className={styles.building} role="status">
          <span className={styles.spinner} aria-hidden="true" />
          Building your portfolio…
        </p>
      )}
      {investing.error && !busy && (
        <p className={styles.error} role="alert">
          <Icon name="alert" size={18} />
          {investing.error}
        </p>
      )}
    </Screen>
  );
}
