// Friendly names for the portal API's types (the source of truth is api-schema.d.ts, generated from the OpenAPI document).
import type { components } from "./api-schema";

type S = components["schemas"];

export type PortalDocuments = S["PortalDocuments"];
export type PortalAnswers = S["PortalAnswers"];
export type PortalHouseholdResponse = S["PortalHouseholdResponse"];
export type ParsedDocument = S["ParsedDocument"];
export type ParsedField = S["ParsedField"];
export type Household = S["Household"];
export type Plan = S["Plan"];
export type InvestRequest = S["InvestRequest"];
export type IncomeChange = NonNullable<PortalAnswers["income_change"]>;

/** The values a customer edited on Review, by field key. */
export type Overrides = Record<string, number>;

/** What an Invest was built from: used to say what changed since the one before. */
export interface InvestInputs {
  overrides: Overrides;
  answers: PortalAnswers;
}
