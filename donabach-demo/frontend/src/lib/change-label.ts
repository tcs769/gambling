// Words for what the customer changed since the last Invest ("Income: job loss next year", "Retirement age: 65").
// The API shows precomputed changes under its own label; this one is for a change it has to work out live.
import { dollarsWhole, formatField, sameValue } from "./portal-format";
import type { InvestInputs, ParsedField, PortalAnswers } from "./portal-types";

type Income = NonNullable<PortalAnswers["income_change"]>;

const INCOME: Record<Income, string> = {
  none: "Income: no change",
  job_loss: "Income: job loss next year",
  raise: "Income: a raise",
};

const plural = (n: number, unit: string) => `${n} ${unit}${n === 1 ? "" : "s"}`;

const collegeText = (a: PortalAnswers) =>
  a.college_starts_in_years === null || a.college_starts_in_years === undefined
    ? "none"
    : `${dollarsWhole(a.college_annual_cost ?? 0)} a year for ${plural(a.college_years ?? 4, "year")}, starting in ${plural(a.college_starts_in_years, "year")}`;

const homeText = (a: PortalAnswers) =>
  a.home_purchase_in_years === null || a.home_purchase_in_years === undefined
    ? "none"
    : `${dollarsWhole(a.home_down_payment ?? 0)} within ${plural(a.home_purchase_in_years, "year")}`;

/** The change between two Invests in words, joined with "; ", or null when nothing changed. */
export function changeLabel(previous: InvestInputs | null, next: InvestInputs, fields: ParsedField[]): string | null {
  if (!previous) return null;
  const a = previous.answers;
  const b = next.answers;
  const parts: string[] = [];

  if ((a.income_change ?? "none") !== (b.income_change ?? "none")) parts.push(INCOME[b.income_change ?? "none"]);
  if (a.retirement_age !== b.retirement_age) parts.push(`Retirement age: ${b.retirement_age}`);
  if (!sameValue(a.retirement_spending, b.retirement_spending))
    parts.push(`Retirement spending: ${dollarsWhole(b.retirement_spending)}`);
  const homeBefore = a.home_purchase_in_years ?? null;
  const homeAfter = b.home_purchase_in_years ?? null;
  if (homeBefore !== homeAfter || (homeAfter !== null && !sameValue(a.home_down_payment, b.home_down_payment)))
    parts.push(`Home purchase: ${homeText(b)}`);
  const collegeBefore = a.college_starts_in_years ?? null;
  const collegeAfter = b.college_starts_in_years ?? null;
  if (
    collegeBefore !== collegeAfter ||
    (collegeAfter !== null && (!sameValue(a.college_annual_cost, b.college_annual_cost) || a.college_years !== b.college_years))
  )
    parts.push(`College: ${collegeText(b)}`);

  const byKey = new Map(fields.map((f) => [f.key, f]));
  const keys = new Set([...Object.keys(previous.overrides), ...Object.keys(next.overrides)]);
  for (const key of keys) {
    const before = previous.overrides[key];
    const after = next.overrides[key];
    if (sameValue(before ?? null, after ?? null)) continue;
    const field = byKey.get(key);
    if (!field) continue;
    // An edit that was taken back is a change back to the value on the document.
    parts.push(`${field.label}: ${formatField(field.kind, after === undefined ? field.value : after)}`);
  }
  return parts.length > 0 ? parts.join("; ") : null;
}
