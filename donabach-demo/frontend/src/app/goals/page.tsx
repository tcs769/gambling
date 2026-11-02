"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Choices, type Choice } from "@/components/portal/Choices";
import { Screen } from "@/components/portal/Screen";
import { useGuard } from "@/components/portal/useGuard";
import { Icon, NumberInput } from "@/components/ui";
import { portalApi } from "@/lib/portal-api";
import { dollarsWhole, sameValue } from "@/lib/portal-format";
import { usePortal } from "@/lib/portal-state";
import type { IncomeChange, PortalAnswers } from "@/lib/portal-types";
import styles from "./Goals.module.css";

const RETIREMENT_AGES = [55, 58, 60, 62, 65, 67, 70];
const SPENDING_CHOICES = [75_000, 105_000, 120_000];
const HOME_CHOICE = { years: 3, down: 150_000 };
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
  // Which questions have "Other" open (a value that matches no option opens it by itself).
  const [other, setOther] = useState({ age: false, spending: false, college: false, home: false });
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
      <Screen title="Goals" back={{ onClick: () => router.push("/review") }}>
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

  // --- retirement age
  const ageInList = RETIREMENT_AGES.includes(answers.retirement_age);
  const ageChoice = other.age || !ageInList ? "other" : String(answers.retirement_age);
  const ageOptions: Choice[] = [
    ...RETIREMENT_AGES.map((a) => ({ id: String(a), label: String(a) })),
    { id: "other", label: "Other" },
  ];

  // --- retirement spending (John's value is the API's default)
  const spendingValues = [...new Set([...SPENDING_CHOICES, defaults.retirement_spending])].sort((a, b) => a - b);
  const spendingMatch = spendingValues.find((v) => sameValue(v, answers.retirement_spending));
  const spendingChoice = other.spending || spendingMatch === undefined ? "other" : String(spendingMatch);
  const spendingOptions: Choice[] = [
    ...spendingValues.map((v) => ({ id: String(v), label: dollarsWhole(v) })),
    { id: "other", label: "Other" },
  ];

  // --- college
  const collegeYears = answers.college_starts_in_years ?? null;
  const johnCollege = defaults.college_starts_in_years ?? null;
  const collegeIsJohn =
    johnCollege !== null &&
    collegeYears === johnCollege &&
    sameValue(answers.college_annual_cost, defaults.college_annual_cost) &&
    answers.college_years === defaults.college_years;
  const collegeChoice = other.college ? "other" : collegeYears === null ? "none" : collegeIsJohn ? "john" : "other";
  const collegeOptions: Choice[] = [
    { id: "none", label: "None" },
    ...(johnCollege !== null
      ? [
          {
            id: "john",
            label: `In ${plural(johnCollege, "year")}, ${dollarsWhole(defaults.college_annual_cost ?? 0)} a year for ${plural(defaults.college_years ?? 4, "year")}`,
          },
        ]
      : []),
    { id: "other", label: "Other" },
  ];

  // --- home purchase
  const homeYears = answers.home_purchase_in_years ?? null;
  const homeIsPreset = homeYears === HOME_CHOICE.years && sameValue(answers.home_down_payment, HOME_CHOICE.down);
  const homeChoice = other.home ? "other" : homeYears === null ? "none" : homeIsPreset ? "preset" : "other";
  const homeOptions: Choice[] = [
    { id: "none", label: "None planned" },
    {
      id: "preset",
      label: `Within ${plural(HOME_CHOICE.years, "year")}, ${dollarsWhole(HOME_CHOICE.down)} down payment`,
    },
    { id: "other", label: "Other" },
  ];

  const invest = () => {
    void actions
      .invest()
      .then(() => router.push("/invest"))
      .catch(() => undefined); // shown below
  };

  return (
    <Screen
      title="Goals"
      back={{ onClick: () => router.push("/review") }}
      next={{ label: "Invest", onClick: invest, busy }}
    >
      <div className={styles.questions}>
        <Choices
          name="retirement_age"
          legend="Retirement age"
          options={ageOptions}
          value={ageChoice}
          onChange={(id) => {
            if (id === "other") setOther((o) => ({ ...o, age: true }));
            else {
              setOther((o) => ({ ...o, age: false }));
              set({ retirement_age: Number(id) });
            }
          }}
        >
          {ageChoice === "other" && (
            <div className={styles.otherRow}>
              <label className={styles.otherLabel}>
                Age
                <NumberInput
                  className={styles.input}
                  value={answers.retirement_age}
                  integer
                  min={50}
                  max={70}
                  aria-label="Retirement age, other"
                  onCommit={(v) => set({ retirement_age: v })}
                />
              </label>
            </div>
          )}
        </Choices>

        <Choices
          name="retirement_spending"
          legend="Retirement spending a year"
          options={spendingOptions}
          value={spendingChoice}
          onChange={(id) => {
            if (id === "other") setOther((o) => ({ ...o, spending: true }));
            else {
              setOther((o) => ({ ...o, spending: false }));
              set({ retirement_spending: Number(id) });
            }
          }}
        >
          {spendingChoice === "other" && (
            <div className={styles.otherRow}>
              <label className={styles.otherLabel}>
                Amount a year
                <NumberInput
                  className={styles.input}
                  value={Math.round(answers.retirement_spending)}
                  min={0}
                  prefixText="$"
                  aria-label="Retirement spending a year, other"
                  onCommit={(v) => set({ retirement_spending: v })}
                />
              </label>
            </div>
          )}
        </Choices>

        <Choices
          name="college"
          legend="College"
          options={collegeOptions}
          value={collegeChoice}
          onChange={(id) => {
            if (id === "none") {
              setOther((o) => ({ ...o, college: false }));
              set({ college_starts_in_years: null });
            } else if (id === "john") {
              setOther((o) => ({ ...o, college: false }));
              set({
                college_starts_in_years: defaults.college_starts_in_years,
                college_annual_cost: defaults.college_annual_cost,
                college_years: defaults.college_years,
              });
            } else {
              setOther((o) => ({ ...o, college: true }));
              if (collegeYears === null)
                set({
                  college_starts_in_years: defaults.college_starts_in_years ?? 8,
                  college_annual_cost: defaults.college_annual_cost || 40_000,
                  college_years: defaults.college_years ?? 4,
                });
            }
          }}
        >
          {collegeChoice === "other" && (
            <div className={styles.otherRow}>
              <label className={styles.otherLabel}>
                Starts in (years)
                <NumberInput
                  className={styles.input}
                  value={answers.college_starts_in_years ?? null}
                  integer
                  min={0}
                  max={30}
                  aria-label="College starts in years, other"
                  onCommit={(v) => set({ college_starts_in_years: v })}
                />
              </label>
              <label className={styles.otherLabel}>
                Cost a year
                <NumberInput
                  className={styles.input}
                  value={Math.round(answers.college_annual_cost ?? 0)}
                  min={0}
                  prefixText="$"
                  aria-label="College cost a year, other"
                  onCommit={(v) => set({ college_annual_cost: v })}
                />
              </label>
              <label className={styles.otherLabel}>
                Years of college
                <NumberInput
                  className={styles.input}
                  value={answers.college_years ?? 4}
                  integer
                  min={1}
                  max={8}
                  aria-label="Years of college, other"
                  onCommit={(v) => set({ college_years: v })}
                />
              </label>
            </div>
          )}
        </Choices>

        <Choices
          name="home_purchase"
          legend="Home purchase"
          options={homeOptions}
          value={homeChoice}
          onChange={(id) => {
            if (id === "none") {
              setOther((o) => ({ ...o, home: false }));
              set({ home_purchase_in_years: null, home_down_payment: defaults.home_down_payment });
            } else if (id === "preset") {
              setOther((o) => ({ ...o, home: false }));
              set({ home_purchase_in_years: HOME_CHOICE.years, home_down_payment: HOME_CHOICE.down });
            } else {
              setOther((o) => ({ ...o, home: true }));
              if (homeYears === null) set({ home_purchase_in_years: 5, home_down_payment: HOME_CHOICE.down });
            }
          }}
        >
          {homeChoice === "other" && (
            <div className={styles.otherRow}>
              <label className={styles.otherLabel}>
                In (years)
                <NumberInput
                  className={styles.input}
                  value={answers.home_purchase_in_years ?? null}
                  integer
                  min={0}
                  max={30}
                  aria-label="Home purchase in years, other"
                  onCommit={(v) => set({ home_purchase_in_years: v })}
                />
              </label>
              <label className={styles.otherLabel}>
                Down payment
                <NumberInput
                  className={styles.input}
                  value={Math.round(answers.home_down_payment ?? 0)}
                  min={0}
                  prefixText="$"
                  aria-label="Home down payment, other"
                  onCommit={(v) => set({ home_down_payment: v })}
                />
              </label>
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
