"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Icon, NumberInput, Spinner } from "@/components/ui";
import { useApp } from "@/lib/state";
import type { Household, HouseholdEdits, Preset } from "@/lib/types";
import { SwitchRow } from "./SwitchRow";
import styles from "./WhatIf.module.css";

const PRESETS: { id: Preset; label: string }[] = [
  { id: "home_next_year", label: "Move home purchase to next year" },
  { id: "spouse_b_income_cut", label: "Spouse B changes jobs, income down 20%" },
  { id: "retire_57", label: "Retire at 57" },
  { id: "market_drop_30", label: "Market drops 30% next year" },
];

type NumberField =
  | "retirement_age"
  | "retirement_spending"
  | "charitable_giving"
  | "home_purchase_in_years"
  | "home_down_payment"
  | "spouse_wages"
  | "social_security_annual";

const FIELD_LABELS: Record<NumberField, string> = {
  retirement_age: "Retirement age",
  retirement_spending: "Retirement spending",
  charitable_giving: "Charitable giving",
  home_purchase_in_years: "Home purchase timing",
  home_down_payment: "Down payment",
  spouse_wages: "Spouse B income",
  social_security_annual: "Social Security",
};

/** What the household has for a field today. */
function readField(household: Household | undefined, field: NumberField): number | null {
  if (!household) return null;
  switch (field) {
    case "retirement_age":
      return household.goals?.retirement_age ?? null;
    case "retirement_spending":
      return household.goals?.retirement_spending ?? null;
    case "charitable_giving":
      return household.goals?.charitable_giving ?? null;
    case "home_purchase_in_years":
      return household.goals?.home_purchase_in_years ?? null;
    case "home_down_payment":
      return household.goals?.home_down_payment ?? null;
    case "spouse_wages":
      return household.people[1]?.wages ?? null;
    case "social_security_annual":
      return household.social_security?.annual_benefit ?? null;
  }
}

/**
 * Edits to send. Switches that are off are left out. With no scenario on, a number typed back to
 * the original value is no change at all, so it is dropped (and typing everything back resets).
 */
function tidy(edits: Partial<HouseholdEdits>, presets: Preset[], base: Household | undefined): Partial<HouseholdEdits> {
  const out: Partial<HouseholdEdits> = {};
  for (const [key, value] of Object.entries(edits) as [keyof HouseholdEdits, HouseholdEdits[keyof HouseholdEdits]][]) {
    if (value === null || value === undefined || value === false) continue;
    if (presets.length === 0 && typeof value === "number" && value === readField(base, key as NumberField)) continue;
    (out as Record<string, unknown>)[key] = value;
  }
  return out;
}

/** The API's range messages ("Input should be less than or equal to 70") with the field named. */
function explain(message: string, field: NumberField | null): string {
  const range = message.match(/Input should be (greater|less) than or equal to (-?[\d.]+)/);
  if (range && field)
    return `${FIELD_LABELS[field]} has to be ${range[1] === "greater" ? "at least" : "at most"} ${range[2]}.`;
  return message;
}

interface FieldProps {
  field: NumberField;
  label: string;
  household: Household | undefined;
  integer?: boolean;
  prefixText?: string;
  suffixText?: string;
  disabled?: boolean;
  /** The field takes the whole row (the grid has two columns). */
  wide?: boolean;
  busy: boolean;
  resetKey: number;
  onDraft: (field: NumberField, value: number | null) => void;
  onCommit: (field: NumberField, value: number) => void;
}

function Field({
  field,
  label,
  household,
  integer,
  prefixText,
  suffixText,
  disabled,
  wide,
  busy,
  resetKey,
  onDraft,
  onCommit,
}: FieldProps) {
  return (
    <label className={styles.field} data-wide={wide || undefined}>
      <span className={styles.fieldLabel}>{label}</span>
      <NumberInput
        key={resetKey}
        value={readField(household, field)}
        integer={integer}
        min={0}
        prefixText={prefixText}
        suffixText={suffixText}
        disabled={disabled}
        readOnly={busy}
        onValueChange={(value) => onDraft(field, value)}
        onCommit={(value) => value !== null && onCommit(field, value)}
      />
    </label>
  );
}

/**
 * The what-if panel: scenario buttons that apply at once, a few editable assumptions (applied on
 * Enter, when you leave the box, or with "Update plan"), what changed, and a way back. The page
 * keeps showing the previous numbers, dimmed, while it re-plans.
 */
export function WhatIfDrawer({ onClose }: { onClose: () => void }) {
  const { state, actions, household } = useApp();
  const base = state.profile?.household;
  const applied = state.whatIf;
  const presets = applied?.presets ?? [];
  const edits = applied?.edits ?? {};
  const loading = state.loading.whatIf;

  const panel = useRef<HTMLDivElement>(null);
  const [drafts, setDrafts] = useState<Partial<Record<NumberField, number>>>({});
  const [lastField, setLastField] = useState<NumberField | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [resetKey, setResetKey] = useState(0);

  // Focus moves in when the panel opens, back to its button when it closes; Escape closes it.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });
  useEffect(() => {
    panel.current?.focus({ preventScroll: true });
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        onCloseRef.current();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.getElementById("whatif-button")?.focus({ preventScroll: true });
    };
  }, []);

  const apply = (nextPresets: Preset[], nextEdits: Partial<HouseholdEdits>, field: NumberField | null = null) => {
    if (loading) return;
    setAttempted(true);
    setLastField(field);
    void actions.runWhatIf(nextPresets, tidy(nextEdits, nextPresets, base));
  };

  const togglePreset = (id: Preset) =>
    apply(presets.includes(id) ? presets.filter((p) => p !== id) : [...presets, id], edits);

  const onDraft = (field: NumberField, value: number | null) => {
    setAttempted(false);
    setDrafts((current) => {
      const next = { ...current };
      if (value === null) delete next[field];
      else next[field] = value;
      return next;
    });
  };

  const onCommit = (field: NumberField, value: number) => {
    setDrafts((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });
    if (value === readField(household, field)) return;
    apply(presets, { ...edits, [field]: value }, field);
  };

  const pendingFields = (Object.keys(drafts) as NumberField[]).filter((f) => drafts[f] !== readField(household, f));
  const updatePlan = () => {
    const typed: Partial<HouseholdEdits> = {};
    for (const field of pendingFields) typed[field] = drafts[field];
    setDrafts({});
    apply(presets, { ...edits, ...typed }, pendingFields[0] ?? null);
  };

  const reset = () => {
    actions.resetWhatIf();
    setDrafts({});
    setAttempted(false);
    setResetKey((n) => n + 1);
  };

  const changes = applied?.response.changes ?? [];
  const failure = attempted && !loading && state.error ? explain(state.error, lastField) : null;

  return (
    <div
      id="whatif-panel"
      ref={panel}
      className={styles.panel}
      role="region"
      aria-labelledby="whatif-title"
      tabIndex={-1}
    >
      <header className={styles.panelHeader}>
        <div>
          <h2 id="whatif-title">What if...</h2>
          <p className={styles.panelSub}>
            Change something and the plan is worked out again on the same simulated futures.
          </p>
        </div>
        <button type="button" className={styles.close} onClick={onClose} aria-label="Close what-if panel">
          <Icon name="close" size={20} />
        </button>
      </header>

      <div className={styles.status} aria-live="polite">
        {loading ? (
          <Spinner label="Re-planning..." />
        ) : failure ? (
          <p className={styles.failure} role="alert">
            <Icon name="alert" size={18} />
            <span>{failure}</span>
          </p>
        ) : applied ? (
          <p className={styles.done}>
            <Icon name="check" size={18} strokeWidth={2.6} />
            <span>Plan updated</span>
          </p>
        ) : (
          <p className={styles.hint}>Pick a scenario or change a number.</p>
        )}
      </div>

      <section aria-labelledby="whatif-scenarios" className={styles.section}>
        <h3 id="whatif-scenarios">Scenarios</h3>
        <div className={styles.presets}>
          {PRESETS.map((preset) => {
            const on = presets.includes(preset.id);
            return (
              <button
                key={preset.id}
                type="button"
                className={styles.preset}
                data-on={on}
                aria-pressed={on}
                aria-disabled={loading || undefined}
                onClick={() => togglePreset(preset.id)}
              >
                <span className={styles.presetMark} aria-hidden="true">
                  {on && <Icon name="check" size={16} strokeWidth={3} />}
                </span>
                {preset.label}
              </button>
            );
          })}
        </div>
      </section>

      {applied && (
        <section aria-labelledby="whatif-changes" className={styles.section}>
          <div className={styles.sectionHead}>
            <h3 id="whatif-changes">What changed</h3>
            <Button variant="secondary" className={styles.resetButton} onClick={reset} disabled={loading}>
              Reset to your plan
            </Button>
          </div>
          {changes.length > 0 ? (
            <ul className={styles.changes}>
              {changes.map((change, i) => (
                <li key={`${change.field}-${i}`}>
                  <span className={styles.changeLabel}>{change.label}</span>
                  <span className={styles.changeValues}>
                    {change.before}
                    <Icon name="arrow" size={16} className={styles.changeArrow} />
                    <span className="sr-only">to</span>
                    <strong>{change.after}</strong>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.hint}>No difference from your plan.</p>
          )}
        </section>
      )}

      <section aria-labelledby="whatif-inputs" className={styles.section}>
        <h3 id="whatif-inputs">Your assumptions</h3>
        <div className={styles.fields}>
          <Field
            field="retirement_age"
            label="Retirement age"
            household={household}
            integer
            busy={loading}
            resetKey={resetKey}
            onDraft={onDraft}
            onCommit={onCommit}
          />
          <Field
            field="retirement_spending"
            label="Retirement spending"
            household={household}
            prefixText="$"
            suffixText="a year"
            busy={loading}
            resetKey={resetKey}
            onDraft={onDraft}
            onCommit={onCommit}
          />
          <Field
            field="charitable_giving"
            label="Charitable giving"
            household={household}
            prefixText="$"
            suffixText="a year"
            wide
            busy={loading}
            resetKey={resetKey}
            onDraft={onDraft}
            onCommit={onCommit}
          />
          <Field
            field="home_purchase_in_years"
            label="Home purchase in"
            household={household}
            integer
            suffixText="years"
            disabled={!!edits.remove_home_purchase}
            busy={loading}
            resetKey={resetKey}
            onDraft={onDraft}
            onCommit={onCommit}
          />
          <Field
            field="home_down_payment"
            label="Down payment"
            household={household}
            prefixText="$"
            disabled={!!edits.remove_home_purchase}
            busy={loading}
            resetKey={resetKey}
            onDraft={onDraft}
            onCommit={onCommit}
          />
        </div>
        <div className={styles.switches}>
          <SwitchRow
            label="No home purchase"
            checked={!!edits.remove_home_purchase}
            busy={loading}
            onChange={(checked) => apply(presets, { ...edits, remove_home_purchase: checked })}
          />
          <SwitchRow
            label="No college"
            checked={!!edits.remove_college}
            busy={loading}
            onChange={(checked) => apply(presets, { ...edits, remove_college: checked })}
          />
        </div>
        <div className={styles.fields}>
          {household && household.people.length > 1 && (
            <Field
              field="spouse_wages"
              label="Spouse B income"
              household={household}
              prefixText="$"
              suffixText="a year"
              busy={loading}
              resetKey={resetKey}
              onDraft={onDraft}
              onCommit={onCommit}
            />
          )}
          <Field
            field="social_security_annual"
            label="Social Security"
            household={household}
            prefixText="$"
            suffixText="a year"
            busy={loading}
            resetKey={resetKey}
            onDraft={onDraft}
            onCommit={onCommit}
          />
        </div>
      </section>

      <div className={styles.actions}>
        <Button onClick={updatePlan} disabled={loading || pendingFields.length === 0}>
          Update plan
        </Button>
      </div>
    </div>
  );
}
