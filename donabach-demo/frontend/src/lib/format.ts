// Money and number formatting. Real 2026 dollars throughout.

/** Compact money for headlines, cards, tables and charts: $850, $4.2k, $40k, $250k, $1.24M. */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value < 0 ? "−" : "";
  const abs = Math.abs(value);
  // From $999.5k up the thousands would round to "1000k": say $1M instead.
  if (abs >= 999_500) return `${sign}$${trim((abs / 1_000_000).toFixed(2))}M`;
  if (abs >= 100_000) return `${sign}$${Math.round(abs / 1_000)}k`;
  if (abs >= 1_000) return `${sign}$${trim((abs / 1_000).toFixed(1))}k`;
  return `${sign}$${Math.round(abs)}`;
}

/** Exact dollars with separators, for values that must match a document or a tax line: $206,300. */
export function dollars(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const rounded = Math.round(value);
  return `${rounded < 0 ? "−" : ""}$${Math.abs(rounded).toLocaleString("en-US")}`;
}

/** Signed compact money for changes and advantages: +$19k, −$3.2k. */
export function signedMoney(value: number): string {
  if (Math.abs(value) < 0.5) return "$0";
  return `${value > 0 ? "+" : ""}${money(value)}`;
}

/** 0.2234 -> "22%"; pass digits for more precision. */
export function percent(fraction: number, digits = 0): string {
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** A share without a trailing zero: 0.01 -> "1%", 0.075 -> "7.5%". For chances measured on a few hundred futures. */
export function percentTrim(fraction: number, maxDigits = 1): string {
  return `${Number((fraction * 100).toFixed(maxDigits))}%`;
}

/**
 * A fraction as a signed percentage with a true minus sign: 0.0027 -> "+0.27%", -0.0004 -> "−0.04%".
 * Something that rounds to nothing carries no sign ("0.00%"), so there is never a "-0.00%".
 */
export function signedPercent(fraction: number, digits = 2): string {
  const rounded = Number((fraction * 100).toFixed(digits));
  if (rounded === 0) return `${(0).toFixed(digits)}%`;
  return `${rounded > 0 ? "+" : "−"}${Math.abs(rounded).toFixed(digits)}%`;
}

/** A change between two percentages, in percentage points: 0.0012 -> "0.12 percentage points". */
export function percentagePoints(fraction: number, digits = 2): string {
  const points = Number((Math.abs(fraction) * 100).toFixed(digits));
  return `${points} percentage ${points === 1 ? "point" : "points"}`;
}

/** A whole number with thousands separators: 4032 -> "4,032". */
export function count(n: number): string {
  return Math.round(n).toLocaleString("en-US");
}

function trim(s: string): string {
  return s.includes(".") ? s.replace(/\.?0+$/, "") : s;
}

export const years = (n: number): string => `${n} ${n === 1 ? "year" : "years"}`;
