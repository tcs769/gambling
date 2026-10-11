// Money and number formatting. Real 2026 dollars throughout.

/** Compact money for headlines, cards, tables and charts: $850, $4.2k, $40k, $250k, $1.24M. */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value < 0 ? "−" : "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${sign}$${trim((abs / 1_000_000).toFixed(2))}M`;
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

function trim(s: string): string {
  return s.includes(".") ? s.replace(/\.?0+$/, "") : s;
}

export const years = (n: number): string => `${n} ${n === 1 ? "year" : "years"}`;
