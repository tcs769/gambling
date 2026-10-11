// What the Review screen needs to know about a field: how to print it, and where it stands.
import { dollars } from "@/lib/format";
import type { CrossCheck, ParsedField } from "@/lib/types";

export type FieldValue = number | string | null;
export type Overrides = Record<string, number | string>;

/** A value as it appears on the page, by kind: $206,300, 38, 45%, Married filing jointly. */
export function formatValue(kind: ParsedField["kind"], value: FieldValue | undefined): string {
  if (value === null || value === undefined) return "Not found";
  switch (kind) {
    case "money":
      return dollars(Number(value));
    case "integer":
      return Number(value).toLocaleString("en-US");
    case "percent":
      // The parser reports 45.0 for 45%.
      return `${+Number(value).toFixed(2)}%`;
    default:
      return String(value);
  }
}

export function sameValue(a: FieldValue | undefined, b: FieldValue | undefined): boolean {
  if (typeof a === "number" && typeof b === "number") return Math.abs(a - b) < 0.005;
  return a === b;
}

export interface FieldStatus {
  /** What to show: the user's correction if there is one, else what was read. */
  value: FieldValue;
  /** The user typed a value different from the one read. */
  changed: boolean;
  /** The parser was not sure of it (medium) or could not find it (low). */
  needsLook: boolean;
  /** The user has corrected or confirmed it. */
  resolved: boolean;
}

export function fieldStatus(field: ParsedField, overrides: Overrides, acknowledged: string[]): FieldStatus {
  const corrected = field.key in overrides;
  const value = corrected ? overrides[field.key] : field.value;
  return {
    value,
    changed: corrected && !sameValue(overrides[field.key], field.value),
    needsLook: field.confidence !== "high",
    // A missing value can only be settled by typing one; a found value can also be kept as it is.
    resolved: corrected || (field.value !== null && acknowledged.includes(field.key)),
  };
}

/** Fields grouped by their `group`, in the order each group first appears. */
export function groupFields(fields: ParsedField[]): { name: string; fields: ParsedField[] }[] {
  const groups = new Map<string, ParsedField[]>();
  for (const field of fields) {
    const list = groups.get(field.group);
    if (list) list.push(field);
    else groups.set(field.group, [field]);
  }
  return Array.from(groups, ([name, list]) => ({ name, fields: list }));
}

const sentenceCase = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/**
 * Table rows are labelled "Fund name: value". Show the fund as the title and the column as a
 * quieter second line, instead of letting a long label wrap in the middle of a name.
 */
export function splitLabel(field: ParsedField): { title: string; sub?: string } {
  const name = field.meta?.name;
  if (typeof name === "string" && field.label.startsWith(`${name}: `)) {
    return { title: name, sub: sentenceCase(field.label.slice(name.length + 2)) };
  }
  return { title: field.label };
}

export const checkSummary = (checks: CrossCheck[]): { failed: number; text: string } => {
  const failed = checks.filter((c) => !c.passed).length;
  const noun = checks.length === 1 ? "check" : "checks";
  if (checks.length === 0) return { failed, text: "No checks" };
  if (failed === 0) return { failed, text: `${checks.length} ${noun}, all passed` };
  return { failed, text: `${checks.length} ${noun}, ${failed} did not pass` };
};

/** Values the household builder asks for that are not on any parsed document. */
const KNOWN_MISSING: Record<string, { label: string; kind: "money" | "integer" }> = {
  taxpayer_age: { label: "Taxpayer age", kind: "integer" },
  spouse_age: { label: "Spouse age", kind: "integer" },
  child_age_1: { label: "Age of child 1", kind: "integer" },
  w2_wages_taxpayer: { label: "Taxpayer W-2 wages (box 1)", kind: "money" },
  w2_wages_spouse: { label: "Spouse W-2 wages (box 1)", kind: "money" },
};

export function describeMissing(key: string, apiLabel: string): { label: string; kind: "money" | "integer" } {
  return KNOWN_MISSING[key] ?? { label: sentenceCase(apiLabel), kind: /age/.test(key) ? "integer" : "money" };
}
