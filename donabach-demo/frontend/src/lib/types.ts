// Friendly names for the API's types. The source of truth is api-schema.d.ts, generated from the
// backend's OpenAPI document (`npm run gen:api` with the backend running).
import type { components } from "./api-schema";
import { years } from "./format";

type S = components["schemas"];

export type Household = S["Household"];
export type Answers = S["Answers"];
/** Reported in the body of a 422 from POST /household (not part of the OpenAPI response types). */
export interface MissingField {
  key: string;
  label: string;
}
export type DocumentInfo = S["DocumentInfo"];
export type ParseResponse = S["ParseResponse"];
export type ParsedDocument = S["ParsedDocument"];
export type ParsedField = S["ParsedField"];
export type CrossCheck = S["CrossCheck"];
export type Confidence = ParsedField["confidence"];
export type HouseholdProfile = S["HouseholdProfile"];
export type AccountLine = S["AccountLine"];
export type GoalLine = S["GoalLine"];
export type TaxReturn = S["TaxReturn"];
export type TaxLine = S["TaxLine"];
export type ForecastResponse = S["ForecastResponse"];
export type IncomeForecast = S["IncomeForecast"];
export type Factor = S["Factor"];
export type PlanResponse = S["PlanResponse"];
export type PlanRow = S["PlanRow"];
export type StrategyView = S["StrategyView"];
export type OutcomeView = S["OutcomeView"];
export type RankedRow = S["RankedRow"];
export type FanSeries = S["FanSeries"];
export type StatCards = S["StatCards"];
/** How a plan is searched: a spending reserve with everything else in stocks, a stock share with a glide path, or under two limits. */
export type PlanningStyle = PlanSettings["planning_style"];
/** The liability-matched plan against its two limits (null on a plan of any other style). */
export type LiabilityView = S["LiabilityView"];
export type AdvantageView = S["AdvantageView"];
export type BaselineView = S["BaselineView"];
export type PlanSettings = S["PlanSettings"];
export type AdvantageStep = S["AdvantageStep"];
export type RecommenderPanel = S["RecommenderPanel"];
export type Recommendation = S["Recommendation"];
export type YearDetail = S["YearDetail"];
export type Decision = S["Decision"];
export type WhatIfResponse = S["WhatIfResponse"];
export type Change = S["Change"];
export type HouseholdEdits = S["HouseholdEdits"];
export type Preset = NonNullable<S["WhatIfRequest"]["presets"]>[number];
export type MarketShock = S["MarketShock"];
export type ModelsStatus = S["ModelsStatus"];

// The adaptive (year-by-year) planner, spec part B.
export type AdaptiveSection = S["AdaptiveSection"];
export type AdaptiveJob = S["AdaptiveJob"];
export type AdaptivePlanRow = S["AdaptivePlanRow"];
export type ActionView = S["ActionView"];
export type AlternativeView = S["AlternativeView"];
export type YearDecisionView = S["YearDecisionView"];
export type StrategyOutcome = S["StrategyOutcome"];
export type StrategyKey = StrategyOutcome["key"];

// The showcase flow (/showcase): a household card, the waterfall from the advisor to Donabach (median advantage only, and
// the only part that changes with the switches), and the whole plan's wealth over time (both measures of the advantage,
// worked out once).
export type ShowcaseResponse = S["ShowcaseResponse"];
export type ShowcaseWaterfall = S["ShowcaseWaterfall"];
export type ShowcaseMedian = S["ShowcaseMedian"];
export type ShowcaseBar = S["ShowcaseBar"];
export type ShowcaseWealth = S["ShowcaseWealth"];
export type ShowcaseHeirs = S["ShowcaseHeirs"];
export type ShowcaseAdvantage = S["ShowcaseAdvantage"];
export type WealthLines = S["WealthLines"];
export type HouseholdCard = S["HouseholdCard"];
export type CardPerson = S["CardPerson"];
export type CardAccount = S["CardAccount"];
export type CardGoal = S["CardGoal"];

/** The choices that make up a strategy, in display order, with plain-language names. */
export const CHOICE_LABELS: Record<string, string> = {
  stock_share: "Stock share",
  conversion: "Roth conversions",
  private_credit: "Private credit sleeve",
  direct_indexing: "Direct indexing",
  goal_bonds: "Goal-matched bonds",
  k401: "401(k) contributions",
  goal_funding: "Paying for goals",
  reserve: "Spending reserve",
};

/**
 * Words for each choice's values (the API's vocabulary, see `Strategy.choices()` in the backend).
 * Private credit is a percent of long-term money ("0" to "15"); the stock share is "50" to "100".
 * A value this table does not know is shown as the API sent it, never hidden.
 */
export const OPTION_LABELS: Record<string, Record<string, string>> = {
  stock_share: {
    "50": "50% stocks",
    "60": "60% stocks",
    "70": "70% stocks",
    "80": "80% stocks",
    "90": "90% stocks",
    "100": "100% stocks",
  },
  conversion: {
    none: "None",
    fill12_low: "Fill 12% bracket, low-income years",
    fill12_every: "Fill 12% bracket, every year",
    fill22_low: "Fill 22% bracket, low-income years",
    fill22_every: "Fill 22% bracket, every year",
    fill24_low: "Fill 24% bracket, low-income years",
    fill24_every: "Fill 24% bracket, every year",
  },
  private_credit: { "0": "Off", "5": "5%", "10": "10%", "15": "15%" },
  direct_indexing: { on: "On", off: "Off" },
  goal_bonds: { on: "On", off: "Off" },
  k401: { pretax: "Pre-tax", roth: "Roth", roth_low: "Roth in low-income years only" },
  goal_funding: { sell: "Sell assets", borrow: "Borrow against the taxable account" },
  reserve: { off: "Off", "2": "2 years", "4": "4 years", "6": "6 years" },
};

/**
 * A choice's value in words, falling back to the raw value. The spending reserve is a number of years that the table does
 * not list in full (the liability-matched style picks from 2 to 12), so any whole number reads as years.
 */
export function optionLabel(choice: string, option: string): string {
  const known = OPTION_LABELS[choice]?.[option];
  if (known !== undefined) return known;
  if (choice === "reserve" && /^\d+$/.test(option)) return years(Number(option));
  return option;
}

/**
 * The value shown on a strategy's chip. With a spending reserve the stock share is not a choice: everything outside the
 * reserve is in stocks (the API sends "100"), so the chip says that instead of "100% stocks".
 */
export function chipValue(choices: Record<string, string>, choice: string): string {
  if (choice === "stock_share" && choices.reserve !== undefined && choices.reserve !== "off") return "Everything outside the reserve";
  return optionLabel(choice, choices[choice]);
}

/** True for values that mean the lever is not used ("off", no conversions, a 0% sleeve). */
export function optionIsOff(choice: string, option: string): boolean {
  return option === "off" || (choice === "conversion" && option === "none") || (choice === "private_credit" && option === "0");
}

/** The baseline with this key (the API sends the good RIA first, then the typical advisor). */
export function baselineOf(plan: PlanResponse, key: BaselineView["key"]): BaselineView | undefined {
  return plan.baselines.find((b) => b.key === key);
}
