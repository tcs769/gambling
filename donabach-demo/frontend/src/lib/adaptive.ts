// What the year-by-year (adaptive) planner's results say, in words, and the comparisons the screens make between
// two of them (a plan before and after a what-if). Everything here is arithmetic and wording over numbers the API
// sent; it decides nothing and invents no figure.
import { count, money, percent } from "./format";
import type { AdaptiveSection, AlternativeView, MarketShock, PlanRow, YearDecisionView } from "./types";

/** Plain names for the decisions the planner can change. A name this table does not know is shown as the API sent it. */
export const DECISION_NAMES: Record<string, string> = {
  conversion: "Roth conversion",
  realize_gains: "Realizing gains",
  goal_funding: "How the goal is paid",
  k401: "401(k) type",
  private_credit: "Private credit",
  stock_share: "Stock share",
};

export const decisionName = (key: string): string => DECISION_NAMES[key] ?? key;

/** "Roth conversion, Stock share" */
export const decisionList = (keys: readonly string[]): string => keys.map(decisionName).join(", ");

/** The text marker on a year the planner changed: "Changed: Roth conversion, Stock share". */
export const changedTag = (departures: readonly string[]): string => `Changed: ${decisionList(departures)}`;

/** "age 55", "ages 55 and 71", "ages 55, 71 and 78", and past `limit` ages "ages 55, 71, 72 and 5 more". */
export function agesList(ages: readonly number[], limit = 8): string {
  if (ages.length === 0) return "";
  if (ages.length === 1) return `age ${ages[0]}`;
  const shown = ages.slice(0, limit);
  const more = ages.length - shown.length;
  const head = shown.slice(0, -1).join(", ");
  return `ages ${head} and ${more > 0 ? `${shown[shown.length - 1]} and ${more} more` : shown[shown.length - 1]}`;
}

/** A row of either plan, with the planner's departures when it comes from the year-by-year plan. */
export type YearRow = PlanRow & { departs?: boolean; departures?: string[] };

// --------------------------------------------------------------------------------------------
// "Why this year"
// --------------------------------------------------------------------------------------------

export interface GapWords {
  kind: "same" | "lower" | "higher";
  text: string;
}

/**
 * How an alternative's rollout score compares with the chosen action's. `ce_gap` is the chosen action's score minus
 * the alternative's, in dollars of certainty-equivalent wealth at the horizon: positive means the alternative
 * scored lower. Negative means it scored higher in the search but not convincingly, so the plan did not switch.
 */
export function describeGap(gap: number): GapWords {
  if (Math.abs(gap) < 0.5) return { kind: "same", text: "Scored the same as the chosen action" };
  return gap > 0
    ? { kind: "lower", text: `Scored ${money(gap)} lower` }
    : { kind: "higher", text: `Scored ${money(-gap)} higher, but not convincingly` };
}

/** Which decisions an alternative changes, in plain words. */
export const differsIn = (alternative: AlternativeView): string => decisionList(alternative.differs_in);

/**
 * The re-test result in one honest line: how many changes the search proposed and how many held up on fresh futures.
 * Where none were kept the chosen action is the fixed strategy's own, so there is no score to compare and none is quoted.
 */
export function retestLine(decision: YearDecisionView, section: Pick<AdaptiveSection, "plan_path_confirm_k">): string {
  const futures = `${count(section.plan_path_confirm_k)} fresh futures`;
  const proposed = decision.changes_proposed;
  const kept = decision.changes_kept;
  const changes = (n: number) => `${n} ${n === 1 ? "change" : "changes"}`;
  if (proposed === 0) return "The search proposed no change, so there was nothing to re-test.";
  if (kept === 0) {
    return `The search proposed ${changes(proposed)}, but ${proposed === 1 ? "it" : "none of them"} held up when re-tested on ${futures}.`;
  }
  const held = kept === proposed ? (kept === 1 ? "it held up" : "all held up") : `${kept} held up`;
  const fresh = decision.ce_chosen_fresh - decision.ce_fixed_fresh;
  const against =
    Math.abs(fresh) < 0.5
      ? "the same as the fixed strategy's action"
      : `${money(Math.abs(fresh))} ${fresh > 0 ? "higher" : "lower"} than the fixed strategy's action`;
  return `The search proposed ${changes(proposed)} and ${held} when re-tested on ${futures}: there, the chosen action scored ${against}.`;
}

/**
 * The market in the year of a what-if's drop, from the numbers the planner saw ("The market fell 30% this year").
 * Only the shock year says anything: on the plan path every other year is at expected returns.
 */
export function marketNote(decision: YearDecisionView, shock: MarketShock | null | undefined): string | null {
  const market = decision.facts.market_return;
  if (!shock || shock.year !== decision.year_index || market === undefined || Math.abs(market) < 0.005) return null;
  return `The market ${market < 0 ? "fell" : "rose"} ${percent(Math.abs(market))} this year.`;
}

/**
 * What the planner could not know. A what-if's drop comes without warning: the planner decides each year after
 * that year's returns are known, so a year before the drop differs from the unmodified plan only because the fixed
 * strategy it continues differs.
 */
export const BEFORE_DROP_REASON = "differs only because the fixed strategy it continues differs";

/**
 * The same for a what-if that changes more than the market (retiring earlier, say): the planner still cannot have
 * seen the drop coming, but the household differs from the start, so "only" would claim too much.
 */
export const BEFORE_DROP_REASON_WITH_OTHER_CHANGES =
  "the planner could not see it coming; the household and the fixed strategy it continues differ here";

/** Why a year before the drop differs, for a what-if that changes only the market or more than it. */
export const beforeDropReason = (otherChanges: boolean): string =>
  otherChanges ? BEFORE_DROP_REASON_WITH_OTHER_CHANGES : BEFORE_DROP_REASON;

/** The label for a year before the drop: "before the drop: differs only because the fixed strategy it continues differs". */
export const beforeDropNote = (otherChanges: boolean): string => `before the drop: ${beforeDropReason(otherChanges)}`;

export const isBeforeShock = (yearIndex: number, shock: MarketShock | null | undefined): boolean =>
  !!shock && yearIndex < shock.year;

/** Sentence case for a note that starts a line: "before the drop: ..." becomes "Before the drop: ...". */
export const sentence = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);

// --------------------------------------------------------------------------------------------
// Ranges
// --------------------------------------------------------------------------------------------

/**
 * Where a 90% range sits against zero, judged on the numbers as they are printed (`digits` decimals of a percent): a
 * range whose printed end is 0.00% is not called one-sided. "spans" is also what a range that crosses zero is.
 */
export function rangeVerdict(low: number, high: number, digits = 2): "above" | "below" | "spans" {
  const printed = (x: number) => Number((x * 100).toFixed(digits));
  if (printed(low) > 0) return "above";
  if (printed(high) < 0) return "below";
  return "spans";
}

/** One sentence on what a range says about "no effect", as strong as the range is and no stronger. */
export function rangeSentence(low: number, high: number, digits = 2): string {
  switch (rangeVerdict(low, high, digits)) {
    case "above":
      return "The whole 90% range is above zero.";
    case "below":
      return "The whole 90% range is below zero.";
    default:
      return "The 90% range includes zero, so this is not distinguishable from no effect.";
  }
}

// --------------------------------------------------------------------------------------------
// Before and after a what-if
// --------------------------------------------------------------------------------------------

/** The choices of the recommended strategy that differ, with the option each had before (undefined: it had none). */
export function changedChoices(before: Record<string, string>, after: Record<string, string>): Record<string, string | undefined> {
  const out: Record<string, string | undefined> = {};
  for (const [choice, option] of Object.entries(after)) {
    if (before[choice] !== option) out[choice] = before[choice];
  }
  return out;
}

export interface YearDifference {
  yearIndex: number;
  age: number;
  before: string;
  after: string;
  /** The year is before a what-if's market drop, so the planner cannot have been reacting to it. */
  beforeShock: boolean;
}

/** The years whose chosen action (its label) differs between two year-by-year plans, matched by year. */
export function differingYears(
  before: AdaptiveSection,
  after: AdaptiveSection,
  shock: MarketShock | null | undefined,
): { compared: number; differing: YearDifference[] } {
  const earlier = new Map(before.decisions.map((d) => [d.year_index, d] as const));
  const differing: YearDifference[] = [];
  let compared = 0;
  for (const now of after.decisions) {
    const was = earlier.get(now.year_index);
    if (!was) continue;
    compared++;
    if (was.chosen.label !== now.chosen.label) {
      differing.push({
        yearIndex: now.year_index,
        age: now.age,
        before: was.chosen.label,
        after: now.chosen.label,
        beforeShock: isBeforeShock(now.year_index, shock),
      });
    }
  }
  return { compared, differing };
}

export interface RateComparison {
  id: string;
  label: string;
  /** Share of the evaluation futures in which the planner changes something, before the what-if. */
  before: number;
  /** ... and with it. */
  after: number;
}

const mean = (values: readonly number[]) => (values.length ? values.reduce((sum, x) => sum + x, 0) / values.length : 0);
const ages = (from: number, to: number) => (from === to ? `age ${from}` : `ages ${from} to ${to}`);

/**
 * How often the planner changes anything, before and after a what-if, from `departure_by_year`. With a market drop
 * the years are split at it (before, the year of the drop, after); otherwise there is one figure for all years.
 */
export function departureComparison(
  before: AdaptiveSection,
  after: AdaptiveSection,
  shock: MarketShock | null | undefined,
): RateComparison[] {
  const years = Math.min(before.departure_by_year.length, after.departure_by_year.length);
  const ageAt = (i: number) => after.rows.find((row) => row.year_index === i)?.age;
  if (!shock || shock.year < 0 || shock.year >= years) {
    return [{ id: "all", label: "All years", before: before.departure_share, after: after.departure_share }];
  }
  const slice = (plan: AdaptiveSection, from: number, to: number) => mean(plan.departure_by_year.slice(from, to));
  const out: RateComparison[] = [];
  const s = shock.year;
  const first = ageAt(0);
  const dropAge = ageAt(s);
  const last = ageAt(years - 1);
  if (s > 0 && first !== undefined && dropAge !== undefined) {
    out.push({
      id: "before",
      label: `Before the drop (${ages(first, dropAge - 1)})`,
      before: slice(before, 0, s),
      after: slice(after, 0, s),
    });
  }
  out.push({
    id: "year",
    label: `Year of the drop${dropAge === undefined ? "" : ` (age ${dropAge})`}`,
    before: before.departure_by_year[s],
    after: after.departure_by_year[s],
  });
  if (s + 1 < years && dropAge !== undefined && last !== undefined) {
    out.push({
      id: "after",
      label: `Years after the drop (${ages(dropAge + 1, last)})`,
      before: slice(before, s + 1, years),
      after: slice(after, s + 1, years),
    });
  }
  return out;
}
