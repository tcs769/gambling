// Friendly names for the API's types. The source of truth is api-schema.d.ts, generated from the
// backend's OpenAPI document (`npm run gen:api` with the backend running).
import type { components } from "./api-schema";

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

/** The choices that make up a strategy, in display order, with plain-language names. */
export const CHOICE_LABELS: Record<string, string> = {
  stock_share: "Stock share",
  conversion: "Roth conversions",
  private_credit: "Private credit sleeve",
  direct_indexing: "Direct indexing",
  goal_bonds: "Goal-matched bonds",
  k401: "401(k) contributions",
  goal_funding: "Paying for goals",
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
};

/** A choice's value in words, falling back to the raw value. */
export function optionLabel(choice: string, option: string): string {
  return OPTION_LABELS[choice]?.[option] ?? option;
}

/** True for values that mean the lever is not used ("off", no conversions, a 0% sleeve). */
export function optionIsOff(choice: string, option: string): boolean {
  return option === "off" || (choice === "conversion" && option === "none") || (choice === "private_credit" && option === "0");
}

/** The baseline with this key (the API sends the good RIA first, then the typical advisor). */
export function baselineOf(plan: PlanResponse, key: BaselineView["key"]): BaselineView | undefined {
  return plan.baselines.find((b) => b.key === key);
}
