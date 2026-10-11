// Small wording helpers shared by the showcase screens.

/** "4", "4 and 7", "4, 7 and 9". */
export function listOf(items: readonly (string | number)[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** "No children", "1 child, age 8", "2 children, ages 4 and 7". */
export function childrenText(ages: readonly number[]): string {
  if (ages.length === 0) return "No children";
  if (ages.length === 1) return `1 child, age ${ages[0]}`;
  return `${ages.length} children, ages ${listOf(ages)}`;
}

/** "1 strategy", "3 strategies". */
export const strategies = (n: number): string => `${n} ${n === 1 ? "strategy" : "strategies"}`;
