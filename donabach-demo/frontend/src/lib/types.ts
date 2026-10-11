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

/** The five choices that make up a strategy, in display order, with plain-language names. */
export const CHOICE_LABELS: Record<string, string> = {
  stock_share: "Stock share",
  conversion: "Roth conversions",
  private_credit: "Private credit sleeve",
  direct_indexing: "Direct indexing",
  goal_bonds: "Goal-matched bonds",
};

export const OPTION_LABELS: Record<string, Record<string, string>> = {
  stock_share: { "70": "70% stocks", "80": "80% stocks", "90": "90% stocks", "100": "100% stocks" },
  conversion: {
    none: "None",
    fill12_low: "Fill 12% bracket, low-income years",
    fill12_every: "Fill 12% bracket, every year",
    fill22_low: "Fill 22% bracket, low-income years",
    fill22_every: "Fill 22% bracket, every year",
    fill24_low: "Fill 24% bracket, low-income years",
    fill24_every: "Fill 24% bracket, every year",
  },
  private_credit: { on: "10% sleeve", off: "Off" },
  direct_indexing: { on: "On", off: "Off" },
  goal_bonds: { on: "On", off: "Off" },
};
