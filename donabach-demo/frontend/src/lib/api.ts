// Typed client for the Donabach API (proxied at /api, see next.config.ts).
import type {
  AdaptiveJob,
  Answers,
  DocumentInfo,
  ForecastResponse,
  Household,
  HouseholdEdits,
  HouseholdProfile,
  MarketShock,
  MissingField,
  ModelsStatus,
  ParseResponse,
  PlanResponse,
  PlanningStyle,
  Preset,
  ShowcaseResponse,
  ShowcaseWaterfall,
  WhatIfResponse,
  YearDetail,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public missing?: MissingField[],
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init);
  if (!response.ok) {
    let detail: unknown = undefined;
    try {
      detail = (await response.json()).detail;
    } catch {
      /* not JSON */
    }
    if (detail && typeof detail === "object" && !Array.isArray(detail) && "missing" in detail) {
      const d = detail as { message: string; missing: MissingField[] };
      throw new ApiError(response.status, d.message, d.missing);
    }
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ")
          : `Request failed (${response.status})`;
    throw new ApiError(response.status, message || `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

const post = <T>(path: string, body?: unknown, signal?: AbortSignal) =>
  request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });

export const NO_EDITS: HouseholdEdits = {
  retirement_age: null,
  retirement_spending: null,
  charitable_giving: null,
  home_purchase_in_years: null,
  home_down_payment: null,
  college_starts_in_years: null,
  college_annual_cost: null,
  primary_wages: null,
  spouse_wages: null,
  social_security_annual: null,
  roth_balance: null,
  cash: null,
  remove_home_purchase: false,
  remove_college: false,
};

export const api = {
  modelsStatus: () => request<ModelsStatus>("/models/status"),

  loadSampleDocuments: () => post<{ documents: DocumentInfo[] }>("/documents/sample"),
  uploadDocuments: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<{ documents: DocumentInfo[] }>("/documents/upload", { method: "POST", body: form });
  },
  parseDocument: (id: string) => post<ParseResponse>(`/documents/${id}/parse`),
  /** URL of the PDF itself, for the viewer. */
  documentUrl: (id: string) => `${BASE}/documents/${id}/file`,

  createHousehold: (documentIds: string[], overrides: Record<string, number | string>, answers: Answers) =>
    post<HouseholdProfile>("/household", { document_ids: documentIds, overrides, answers }),

  forecast: (household: Household, demoMode: boolean) =>
    post<ForecastResponse>("/forecast", { household, n_paths: 2000, demo_mode: demoMode }),

  /**
   * The fixed-strategy plan, at once. `adaptive` is the year-by-year plan when the API already has it; otherwise
   * `adaptive_job` is the id to poll with `adaptiveJob`. (The request asks for the API's defaults for both.)
   *
   * `planningStyle` is how the plan is searched (the default, equity-first, is what the demo shows). To compare styles on
   * the same futures pass the plan's own `settings.seed` as `seed` (without it a live, non-demo plan draws a new one), and
   * `adaptive: false` to skip the year-by-year job, which only the plan on the other screens needs.
   */
  plan: (
    household: Household,
    demoMode: boolean,
    nPaths = 400,
    shock: MarketShock | null = null,
    options: { planningStyle?: PlanningStyle; seed?: number; adaptive?: boolean } = {},
  ) =>
    post<PlanResponse>("/plan", {
      household,
      n_paths: nPaths,
      demo_mode: demoMode,
      shock,
      planning_style: options.planningStyle ?? "equity_first",
      ...(options.seed === undefined ? {} : { seed: options.seed }),
      ...(options.adaptive === false ? { adaptive: false } : {}),
    }),

  /** One poll of the background job that computes a plan's year-by-year (adaptive) part. */
  adaptiveJob: (id: string) => request<AdaptiveJob>(`/plan/adaptive/${encodeURIComponent(id)}`),

  /**
   * Tell the API this client no longer wants a year-by-year job (the plan on screen was replaced). The job stops once
   * nobody else is waiting for it, so abandoned work does not make the plan on screen wait behind it. Best effort:
   * a failure changes nothing for the person, so it is not reported.
   */
  cancelAdaptiveJob: (id: string): Promise<void> =>
    fetch(`${BASE}/plan/adaptive/${encodeURIComponent(id)}`, { method: "DELETE", keepalive: true }).then(
      () => undefined,
      () => undefined,
    ),

  yearDetail: (household: Household, choices: Record<string, string>, yearIndex: number, shock: MarketShock | null = null) =>
    post<YearDetail>("/plan/year-detail", { household, choices, year_index: yearIndex, shock }),

  /**
   * The showcase household (/showcase): its card, the waterfall with every strategy switched on, the whole plan's wealth over
   * time with both measures of the advantage, and the footer's note. All of it is worked out once; none of it changes when
   * strategies are switched off.
   */
  showcase: (signal?: AbortSignal) => request<ShowcaseResponse>("/showcase", { signal }),

  /**
   * The waterfall (median advantage only) with only the strategies in `enabled` switched on (null: all of them).
   * About half a second for a combination the API has not measured yet. Pass a signal to drop an answer nobody wants.
   */
  showcaseAnalysis: (enabled: readonly string[] | null, signal?: AbortSignal) =>
    post<ShowcaseWaterfall>("/showcase/analysis", { enabled }, signal),

  whatIf: (
    household: Household,
    presets: Preset[],
    edits: Partial<HouseholdEdits>,
    demoMode: boolean,
    nPaths = 400,
  ) =>
    post<WhatIfResponse>("/plan/whatif", {
      household,
      presets,
      edits: { ...NO_EDITS, ...edits },
      n_paths: nPaths,
      demo_mode: demoMode,
    }),
};
