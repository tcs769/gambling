// How the portal writes values: exact, as printed on a document.
import type { ParsedField } from "./portal-types";

/** $645,776.59 or $204,268 (cents only when there are some). */
export function dollarsExact(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  const sign = rounded < 0 ? "−" : "";
  const cents = !Number.isInteger(rounded);
  return `${sign}$${Math.abs(rounded).toLocaleString("en-US", { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: 2 })}`;
}

/** Whole dollars: $90,015. */
export function dollarsWhole(value: number): string {
  const rounded = Math.round(value);
  return `${rounded < 0 ? "−" : ""}$${Math.abs(rounded).toLocaleString("en-US")}`;
}

export type FieldValue = number | string | null;

/** A field's value the way the document prints it. */
export function formatField(kind: ParsedField["kind"], value: FieldValue | undefined): string {
  if (value === null || value === undefined) return "Not found";
  switch (kind) {
    case "money":
      return dollarsExact(Number(value));
    case "integer":
      return Number(value).toLocaleString("en-US");
    case "percent":
      return `${+Number(value).toFixed(2)}%`;
    default:
      return String(value);
  }
}

export function sameValue(a: FieldValue | undefined, b: FieldValue | undefined): boolean {
  if (typeof a === "number" && typeof b === "number") return Math.abs(a - b) < 0.005;
  return a === b;
}

const KIND_LABEL: Record<string, string> = {
  form_1040: "Tax return",
  brokerage_statement: "Brokerage statement",
  retirement_401k: "401(k) statement",
  roth_ira: "Roth IRA statement",
};

/** What a document is called on screen: its kind, or the title the parser found. */
export function documentLabel(doc: { doc_kind: string; title: string }): string {
  return KIND_LABEL[doc.doc_kind] ?? doc.title;
}

/** A label from the API as the customer reads it: the word "plan" is not used on screen ("contributions (plan year)" is "(year)"). */
export const customerLabel = (text: string): string => text.replace(/\bplan year\b/gi, "year");
