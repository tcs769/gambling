// How the Invest and Compare screens write the API's figures. Formatting only: nothing here computes, rounds to a different
// figure or restates a number the API gave.
import { dollarsWhole } from "./portal-format";

/** $2.38M (two decimals) from a million up, else whole dollars. */
export function wealth(value: number): string {
  if (Math.abs(value) < 999_500) return dollarsWhole(value);
  return `${value < 0 ? "−" : ""}$${(Math.abs(value) / 1_000_000).toFixed(2)}M`;
}

/** A dollar amount, or the mockup's dash when there is nothing ($0). */
export function amountOrDash(value: number | null | undefined): string {
  return value === null || value === undefined || Math.abs(value) < 0.5 ? "–" : dollarsWhole(value);
}

/** 0.5525 -> "55%". */
export function percent0(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

/** 0.055 -> "5.5%", 0.22 -> "22%" (the digits it needs, up to two). */
export function percentTrim(fraction: number): string {
  return `${+(fraction * 100).toFixed(2)}%`;
}

/** 0.0035 -> "0.35%", 0.00967 -> "0.97%" (always two decimals). */
export function percent2(fraction: number): string {
  return `${(fraction * 100).toFixed(2)}%`;
}

/** +2.05% (a true minus sign). */
export function signedPercent2(fraction: number): string {
  const text = (Math.abs(fraction) * 100).toFixed(2);
  return `${fraction < 0 ? "−" : "+"}${text}%`;
}

/** "$4,176 (0.35%)". */
export function feeLine(dollars: number, rate: number, decimals: "trim" | "two" = "trim"): string {
  return `${dollarsWhole(dollars)} (${decimals === "two" ? percent2(rate) : percentTrim(rate)})`;
}

/** "$1.09M more at 80" / "$0.2M less at 80". */
export function moreAtHorizon(dollars: number, age: number): string {
  return `${wealth(Math.abs(dollars))} ${dollars < 0 ? "less" : "more"} at ${age}`;
}

/** The mix shares as a customer reads them: "55%"; with a decimal when two figures would read the same. */
export function beforeAfter(before: number, after: number): [string, string] {
  const a = percent0(before);
  const b = percent0(after);
  if (a !== b) return [a, b];
  return [`${+(before * 100).toFixed(1)}%`, `${+(after * 100).toFixed(1)}%`];
}

/** Chart axis: $1.5M, $800k. */
export function axisMoney(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `$${+(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `$${Math.round(value / 1_000)}k`;
  return dollarsWhole(value);
}

export const DISCLAIMER = "Illustration based on simulated outcomes. Not investment advice.";
