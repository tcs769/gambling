"use client";

// One provider holds the whole demo: documents, corrections, answers, and everything computed from
// them. Screens read state with `useApp()` and call `actions`; nothing here invents a number, it
// only stores what the API returned.

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { ApiError, api } from "./api";
import { errorMessage } from "./showcase";
import type {
  AdaptiveSection,
  Answers,
  DocumentInfo,
  ForecastResponse,
  Household,
  HouseholdEdits,
  HouseholdProfile,
  MissingField,
  ParsedDocument,
  PlanResponse,
  PlanningStyle,
  Preset,
  WhatIfResponse,
} from "./types";

/** Defaults the questions screen starts from (the spec's demo household goals and estimates). */
export const DEFAULT_ANSWERS: Answers = {
  home_purchase_in_years: 3,
  home_down_payment: 120_000,
  college_starts_in_years: 10,
  college_annual_cost: 35_000,
  college_years: 4,
  retirement_age: 62,
  retirement_spending: 110_000,
  charitable_giving: 0,
  roth_balance: 30_000,
  cash: 40_000,
  social_security_annual: 50_000,
  social_security_start_age: 67,
};

/** Each upload/reading stage stays on screen at least this long so it is legible on a recording. */
const STAGE_MS = 450;
/** How often a year-by-year job is asked how far it has got. */
const POLL_MS = 700;
/** Network failures in a row before a job is reported as lost (a job the API no longer knows is lost at once). */
const POLL_FAILURES = 4;
const DEMO_KEY = "donabach-demo-mode";
/** What the viewer typed survives an accidental reload (everything computed is rebuilt from it). */
const SESSION_KEY = "donabach-session";

interface SavedSession {
  answers: Answers;
  overrides: Record<string, number | string>;
  acknowledged: string[];
}

export type DocStatus = "uploading" | "reading" | "ready" | "error";

export interface DocState {
  info: DocumentInfo;
  status: DocStatus;
  parsed?: ParsedDocument;
  error?: string;
}

/**
 * Where a plan's year-by-year (adaptive) part stands. The fixed-strategy plan arrives at once; the year-by-year part
 * is either in the same response (the API already had it), or a background job that is followed until it ends.
 */
export type AdaptiveState =
  | { status: "ready"; section: AdaptiveSection }
  | { status: "refining"; jobId: string; progress: number }
  | { status: "failed"; message: string }
  /** The response held neither a year-by-year plan nor a job to follow. */
  | { status: "unavailable" };

/** The year-by-year plan itself, once there is one. */
export const adaptiveSection = (adaptive: AdaptiveState | undefined): AdaptiveSection | undefined =>
  adaptive?.status === "ready" ? adaptive.section : undefined;

const startAdaptive = (plan: PlanResponse): AdaptiveState =>
  plan.adaptive
    ? { status: "ready", section: plan.adaptive }
    : plan.adaptive_job
      ? { status: "refining", jobId: plan.adaptive_job, progress: 0 }
      : { status: "unavailable" };

export interface WhatIfState {
  presets: Preset[];
  edits: Partial<HouseholdEdits>;
  response: WhatIfResponse;
  /** The year-by-year part of this what-if's plan: its own, never the base plan's. */
  adaptive: AdaptiveState;
}

/** What the Plan screen's switch is on: one planning style, or all three side by side. */
export type PlanStyleView = PlanningStyle | "all";

/** The two styles other than the default one, whose plans are asked for when the Plan screen's switch lands on them. */
export type AltStyle = Exclude<PlanningStyle, "equity_first">;
export const ALT_STYLES: readonly AltStyle[] = ["balanced", "liability_matched"];

/** One of the other styles' plans for the household on screen: on its way, here, or refused. */
export type StyleSlot =
  | { status: "loading" }
  | { status: "ready"; plan: PlanResponse }
  | { status: "failed"; message: string };
export type StyleSlots = Partial<Record<AltStyle, StyleSlot>>;

/**
 * The other styles' plans for one equity-first plan (`base`, the plan the household on screen has: the base plan or a
 * what-if's). They are asked for on the same household, shock and seed, so the three plans are measured on the same futures.
 */
interface StylePlans {
  base: PlanResponse;
  slots: StyleSlots;
}

const NO_SLOTS: StyleSlots = {};

const withSlot = (entries: StylePlans[], base: PlanResponse, style: AltStyle, slot: StyleSlot): StylePlans[] =>
  entries.some((e) => e.base === base)
    ? entries.map((e) => (e.base === base ? { base, slots: { ...e.slots, [style]: slot } } : e))
    : [...entries, { base, slots: { [style]: slot } }];

export interface AppState {
  demoMode: boolean;
  docs: DocState[];
  /** Values the user corrected, by field key. They override what the parser read. */
  overrides: Record<string, number | string>;
  /** Flagged fields the user confirmed as they are. */
  acknowledged: string[];
  answers: Answers;
  /** Fields the household could not be built without (set when the API says so). */
  missing: MissingField[];
  profile?: HouseholdProfile;
  forecast?: ForecastResponse;
  plan?: PlanResponse;
  /**
   * The base plan's year-by-year part, kept with the plan it belongs to: once that plan is replaced (a new
   * household, answers or mode) this no longer matches `plan` and is ignored, so a stale year-by-year plan is
   * never shown against a newer fixed plan.
   */
  adaptive?: { plan: PlanResponse; state: AdaptiveState };
  whatIf?: WhatIfState;
  /** Where the Plan screen's planning-style switch is (it keeps its place while the viewer visits other screens). */
  planStyle: PlanStyleView;
  /** The other planning styles' plans, kept per plan they were asked for so toggling back is instant (see `StylePlans`). */
  stylePlans: StylePlans[];
  loading: { docs: boolean; household: boolean; forecast: boolean; plan: boolean; whatIf: boolean };
  error?: string;
}

const initial: AppState = {
  demoMode: true,
  docs: [],
  overrides: {},
  acknowledged: [],
  answers: DEFAULT_ANSWERS,
  missing: [],
  planStyle: "equity_first",
  stylePlans: [],
  loading: { docs: false, household: false, forecast: false, plan: false, whatIf: false },
};

type Patch = Partial<AppState> | ((s: AppState) => Partial<AppState>);

/**
 * State lives in a small external store rather than in React state, so actions can always read the
 * latest values (right after a `patch`, before React has re-rendered) and components subscribe
 * through `useSyncExternalStore`.
 */
class Store {
  private state: AppState = initial;
  private listeners = new Set<() => void>();
  readonly inflight = new Map<string, Promise<unknown>>();
  /** Resolves once saved inputs have been restored (child effects run before the provider's). */
  readonly restored: Promise<void>;
  private markRestored!: () => void;

  constructor() {
    this.restored = new Promise<void>((resolve) => {
      this.markRestored = resolve;
    });
  }
  /** Bumped by every what-if request and by reset, so a slow response cannot overwrite a newer one. */
  private whatIfTicket = 0;
  nextWhatIfTicket = (): number => ++this.whatIfTicket;
  isLatestWhatIf = (ticket: number): boolean => ticket === this.whatIfTicket;

  getState = (): AppState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  patch = (change: Patch): void => {
    const before = this.state;
    this.state = { ...before, ...(typeof change === "function" ? change(before) : change) };
    // The other styles' plans are kept only for the plans that are still on hand (the base plan and a what-if's).
    if (this.state.stylePlans.length > 0) {
      const live = [this.state.plan, this.state.whatIf?.response.plan];
      const kept = this.state.stylePlans.filter((entry) => live.includes(entry.base));
      if (kept.length !== this.state.stylePlans.length) this.state = { ...this.state, stylePlans: kept };
    }
    if (
      this.state.answers !== before.answers ||
      this.state.overrides !== before.overrides ||
      this.state.acknowledged !== before.acknowledged
    ) {
      this.persist();
    }
    this.listeners.forEach((listener) => listener());
  };

  private persist(): void {
    if (typeof window === "undefined") return;
    const { answers, overrides, acknowledged } = this.state;
    try {
      window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({ answers, overrides, acknowledged } satisfies SavedSession));
    } catch {
      /* storage unavailable: the demo still works, it just forgets on reload */
    }
  }

  restore(): void {
    try {
      const raw = window.sessionStorage.getItem(SESSION_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw) as Partial<SavedSession>;
      this.state = {
        ...this.state,
        answers: { ...DEFAULT_ANSWERS, ...saved.answers },
        overrides: saved.overrides ?? {},
        acknowledged: saved.acknowledged ?? [],
      };
      this.listeners.forEach((listener) => listener());
    } catch {
      /* corrupt or unavailable: start from the defaults */
    } finally {
      this.markRestored();
    }
  }

  clearSaved(): void {
    try {
      window.sessionStorage.removeItem(SESSION_KEY);
    } catch {
      /* ignore */
    }
  }
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
let pendingCounter = 0;

export type BuildResult = { ok: true } | { ok: false; message: string; missing: MissingField[] };

export interface Actions {
  setDemoMode(on: boolean): void;
  /** Add the three sample PDFs. `animate: false` skips the on-screen stages (used when bootstrapping). */
  loadSamples(options?: { animate?: boolean }): Promise<void>;
  uploadFiles(files: File[]): Promise<void>;
  removeDoc(id: string): void;
  setOverride(key: string, value: number | string): void;
  clearOverride(key: string): void;
  acknowledge(key: string): void;
  setAnswers(patch: Partial<Answers>): void;
  /** Build the household from the documents, corrections and answers (POST /household). */
  buildHousehold(): Promise<BuildResult>;
  runForecast(): Promise<void>;
  runPlan(): Promise<void>;
  /** Re-plan from the base household with these presets and edits. Empty selections reset. */
  runWhatIf(presets: Preset[], edits: Partial<HouseholdEdits>): Promise<void>;
  resetWhatIf(): void;
  /** Move the Plan screen's planning-style switch. */
  setPlanStyle(view: PlanStyleView): void;
  /**
   * Ask for the plan in one of the other planning styles, for the household on screen (a what-if's if one is active), on
   * the same futures as the plan on screen. Nothing happens when it is already here or on its way; `retry` asks again
   * after a refusal.
   */
  ensureStylePlan(style: AltStyle, options?: { retry?: boolean }): Promise<void>;
  /** Make sure the household / forecast / plan exist, bootstrapping in demo mode. False = go back to Upload. */
  ensureProfile(): Promise<boolean>;
  ensureForecast(): Promise<boolean>;
  ensurePlan(): Promise<boolean>;
  reset(): void;
}

interface AppContextValue {
  state: AppState;
  actions: Actions;
  /** The household being planned for: the what-if's if one is active, else the base household. */
  household?: Household;
  /** The plan on screen: the what-if's if one is active, else the base plan. */
  plan?: PlanResponse;
  /** The base plan, untouched by any what-if (for before/after comparisons). */
  basePlan?: PlanResponse;
  /** The year-by-year part of the plan on screen (the what-if's if one is active). */
  adaptive?: AdaptiveState;
  /** The year-by-year part of the base plan, kept while a what-if is on screen. */
  baseAdaptive?: AdaptiveState;
  whatIfActive: boolean;
  /** The other planning styles' plans for the plan on screen, as far as they have been asked for. */
  styleSlots: StyleSlots;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [store] = useState(() => new Store());
  const state = useSyncExternalStore(store.subscribe, store.getState, store.getState);

  useEffect(() => {
    const saved = window.localStorage.getItem(DEMO_KEY);
    if (saved !== null) store.patch({ demoMode: saved === "true" });
    store.restore();
  }, [store]);

  const actions = useMemo<Actions>(() => {
    const { patch } = store;
    const current = store.getState;
    const once = <T,>(key: string, run: () => Promise<T>): Promise<T> => {
      const existing = store.inflight.get(key) as Promise<T> | undefined;
      if (existing) return existing;
      const p = run().finally(() => store.inflight.delete(key));
      store.inflight.set(key, p);
      return p;
    };
    const setLoading = (key: keyof AppState["loading"], value: boolean) =>
      patch((s) => ({ loading: { ...s.loading, [key]: value } }));
    const updateDoc = (id: string, change: Partial<DocState> & { info?: DocumentInfo }) =>
      patch((s) => ({ docs: s.docs.map((d) => (d.info.id === id ? { ...d, ...change } : d)) }));
    const invalidateResults = () =>
      patch({ profile: undefined, forecast: undefined, plan: undefined, whatIf: undefined });

    /**
     * Follows a year-by-year job until it ends, writing its progress and result through `set`. It stops quietly
     * the moment `isCurrent` says the plan it belongs to is no longer on screen (a re-plan, a reset, new answers):
     * an old job is never polled for a plan that has been replaced, and its result is never shown. It also asks the
     * API to drop the job, so a newer plan does not queue behind work nobody wants.
     */
    async function followAdaptive(jobId: string, isCurrent: () => boolean, set: (state: AdaptiveState) => void) {
      let failures = 0;
      let progress = 0;
      // Walking away from a job that is still running tells the API, which stops it once no one else waits for it.
      const walkAway = () => void api.cancelAdaptiveJob(jobId);
      for (;;) {
        await sleep(POLL_MS);
        if (!isCurrent()) return walkAway();
        try {
          const job = await api.adaptiveJob(jobId);
          if (!isCurrent()) return walkAway();
          failures = 0;
          if (job.status === "done") {
            set(
              job.result
                ? { status: "ready", section: job.result }
                : { status: "failed", message: "The year-by-year plan finished without a result." },
            );
            return;
          }
          if (job.status === "error") {
            set({ status: "failed", message: job.error || "The year-by-year plan could not be computed." });
            return;
          }
          if (job.progress !== progress) {
            progress = job.progress;
            set({ status: "refining", jobId, progress });
          }
        } catch (e) {
          if (!isCurrent()) return walkAway();
          const lost = e instanceof ApiError && e.status === 404;
          if (lost || ++failures >= POLL_FAILURES) {
            set({
              status: "failed",
              message: lost
                ? "The year-by-year plan is no longer on the server (it may have restarted)."
                : `The year-by-year plan could not be fetched: ${(e as Error).message}`,
            });
            return;
          }
        }
      }
    }

    /** Follow the base plan's year-by-year job, if it has one still running (`plan` is the object stored in `state.plan`). */
    const followBase = (plan: PlanResponse, start: AdaptiveState) => {
      if (start.status !== "refining") return;
      void followAdaptive(
        start.jobId,
        () => current().plan === plan,
        (next) => patch((s) => (s.plan === plan ? { adaptive: { plan, state: next } } : {})),
      );
    };

    /** The same for a what-if's plan: `response` is the object stored in `state.whatIf`, which stands in for its identity. */
    const followWhatIf = (response: WhatIfResponse, start: AdaptiveState) => {
      if (start.status !== "refining") return;
      void followAdaptive(
        start.jobId,
        () => current().whatIf?.response === response,
        (next) => patch((s) => (s.whatIf?.response === response ? { whatIf: { ...s.whatIf, adaptive: next } } : {})),
      );
    };

    async function readDocument(id: string, animate: boolean) {
      if (animate) await sleep(STAGE_MS);
      updateDoc(id, { status: "reading" });
      const started = performance.now();
      try {
        const { document, parsed } = await api.parseDocument(id);
        if (animate) await sleep(Math.max(0, STAGE_MS - (performance.now() - started)));
        updateDoc(id, { status: "ready", parsed, info: document });
      } catch (e) {
        updateDoc(id, { status: "error", error: (e as Error).message });
      }
    }

    const a: Actions = {
      setDemoMode(on) {
        window.localStorage.setItem(DEMO_KEY, String(on));
        patch({ demoMode: on });
        // Seeds differ between modes, so anything computed is stale.
        patch({ forecast: undefined, plan: undefined, whatIf: undefined });
      },

      async loadSamples({ animate = true } = {}) {
        await once("samples", async () => {
          setLoading("docs", true);
          try {
            const { documents } = await api.loadSampleDocuments();
            const have = new Set(current().docs.map((d) => d.info.id));
            const fresh = documents.filter((d) => !have.has(d.id));
            patch((s) => ({
              docs: [...s.docs, ...fresh.map((info) => ({ info, status: "uploading" as const }))],
              profile: undefined,
              forecast: undefined,
              plan: undefined,
              whatIf: undefined,
            }));
            await Promise.all(fresh.map((d) => readDocument(d.id, animate)));
          } catch (e) {
            patch({ error: (e as Error).message });
          } finally {
            setLoading("docs", false);
          }
        });
      },

      async uploadFiles(files) {
        setLoading("docs", true);
        try {
          await Promise.all(
            files.map(async (file) => {
              const pendingId = `pending-${++pendingCounter}`;
              const placeholder: DocumentInfo = { id: pendingId, name: file.name, size_bytes: file.size, pages: 0, kind: null };
              patch((s) => ({ docs: [...s.docs, { info: placeholder, status: "uploading" }] }));
              try {
                const started = performance.now();
                const { documents } = await api.uploadDocuments([file]);
                await sleep(Math.max(0, STAGE_MS - (performance.now() - started)));
                const info = documents[0];
                patch((s) => ({
                  docs: s.docs.map((d) => (d.info.id === pendingId ? { ...d, info, status: "reading" as const } : d)),
                  profile: undefined,
                  forecast: undefined,
                  plan: undefined,
                  whatIf: undefined,
                }));
                await readDocument(info.id, true);
              } catch (e) {
                patch((s) => ({
                  docs: s.docs.map((d) =>
                    d.info.id === pendingId ? { ...d, status: "error" as const, error: (e as Error).message } : d,
                  ),
                }));
              }
            }),
          );
        } finally {
          setLoading("docs", false);
        }
      },

      removeDoc(id) {
        patch((s) => ({ docs: s.docs.filter((d) => d.info.id !== id) }));
        invalidateResults();
      },

      setOverride(key, value) {
        patch((s) => ({ overrides: { ...s.overrides, [key]: value } }));
        invalidateResults();
      },
      clearOverride(key) {
        patch((s) => {
          const rest = { ...s.overrides };
          delete rest[key];
          return { overrides: rest };
        });
        invalidateResults();
      },
      acknowledge(key) {
        patch((s) => (s.acknowledged.includes(key) ? {} : { acknowledged: [...s.acknowledged, key] }));
      },

      setAnswers(change) {
        patch((s) => ({ answers: { ...s.answers, ...change } }));
        invalidateResults();
      },

      async buildHousehold() {
        return once("household", async (): Promise<BuildResult> => {
          setLoading("household", true);
          const s = current();
          const ids = s.docs.filter((d) => d.status === "ready").map((d) => d.info.id);
          try {
            const profile = await api.createHousehold(ids, s.overrides, s.answers);
            patch({ profile, missing: [], forecast: undefined, plan: undefined, whatIf: undefined, error: undefined });
            return { ok: true };
          } catch (e) {
            const err = e as ApiError;
            if (err.missing?.length) patch({ missing: err.missing });
            else patch({ error: err.message });
            return { ok: false, message: err.message, missing: err.missing ?? [] };
          } finally {
            setLoading("household", false);
          }
        });
      },

      async runForecast() {
        const household = current().profile?.household;
        if (!household) return;
        await once("forecast", async () => {
          setLoading("forecast", true);
          try {
            patch({ forecast: await api.forecast(household, current().demoMode) });
          } catch (e) {
            patch({ error: (e as Error).message });
          } finally {
            setLoading("forecast", false);
          }
        });
      },

      async runPlan() {
        const household = current().profile?.household;
        if (!household) return;
        await once("plan", async () => {
          setLoading("plan", true);
          try {
            const plan = await api.plan(household, current().demoMode);
            // One update: the fixed plan and where its year-by-year part stands, so no screen sees one without the other.
            const adaptive = startAdaptive(plan);
            patch({ plan, whatIf: undefined, adaptive: { plan, state: adaptive } });
            followBase(plan, adaptive);
          } catch (e) {
            patch({ error: (e as Error).message });
          } finally {
            setLoading("plan", false);
          }
        });
      },

      async runWhatIf(presets, edits) {
        const base = current().profile?.household;
        if (!base) return;
        const hasEdits = Object.values(edits).some((v) => v !== null && v !== undefined && v !== false);
        if (presets.length === 0 && !hasEdits) {
          a.resetWhatIf();
          return;
        }
        const ticket = store.nextWhatIfTicket();
        patch({ error: undefined });
        setLoading("whatIf", true);
        try {
          const response = await api.whatIf(base, presets, edits, current().demoMode);
          if (!store.isLatestWhatIf(ticket)) return; // a newer request or a reset superseded this one
          // The fixed plan is on screen at once; its year-by-year part follows (a new job, or the finished plan).
          const adaptive = startAdaptive(response.plan);
          patch({ whatIf: { presets, edits, response, adaptive }, error: undefined });
          followWhatIf(response, adaptive);
        } catch (e) {
          if (store.isLatestWhatIf(ticket)) patch({ error: (e as Error).message });
        } finally {
          if (store.isLatestWhatIf(ticket)) setLoading("whatIf", false);
        }
      },

      resetWhatIf() {
        store.nextWhatIfTicket();
        patch({ whatIf: undefined, error: undefined });
        setLoading("whatIf", false);
      },

      setPlanStyle(view) {
        patch({ planStyle: view });
      },

      async ensureStylePlan(style, { retry = false } = {}) {
        const s = current();
        // The household on screen, and the equity-first plan that goes with it (a what-if's, if one is active).
        const response = s.whatIf?.response;
        const base = response?.plan ?? s.plan;
        const household = response?.household ?? s.profile?.household;
        if (!base || !household) return;
        const known = s.stylePlans.find((entry) => entry.base === base)?.slots[style];
        if (known && !(retry && known.status === "failed")) return;
        const put = (slot: StyleSlot) => patch((now) => ({ stylePlans: withSlot(now.stylePlans, base, style, slot) }));
        put({ status: "loading" });
        try {
          // The same futures as the plan on screen (its seed), and no year-by-year job: only the equity-first plan has one.
          const plan = await api.plan(household, s.demoMode, undefined, base.settings.market_shock ?? null, {
            planningStyle: style,
            seed: base.settings.seed,
            adaptive: false,
          });
          put({ status: "ready", plan });
        } catch (e) {
          put({ status: "failed", message: errorMessage(e) });
        }
      },

      async ensureProfile() {
        await store.restored;
        if (current().profile) return true;
        return once("ensure-profile", async () => {
          const s = current();
          if (!s.docs.some((d) => d.status === "ready")) {
            if (!s.demoMode) return false;
            await a.loadSamples({ animate: false });
          }
          return (await a.buildHousehold()).ok;
        });
      },
      async ensureForecast() {
        if (!(await a.ensureProfile())) return false;
        if (!current().forecast) await a.runForecast();
        return !!current().forecast;
      },
      async ensurePlan() {
        if (!(await a.ensureProfile())) return false;
        if (!current().plan) await a.runPlan();
        return !!current().plan;
      },

      reset() {
        store.clearSaved();
        patch({ ...initial, demoMode: current().demoMode });
      },
    };
    return a;
  }, [store]);

  const value = useMemo<AppContextValue>(() => {
    // The base plan's year-by-year part counts only while it belongs to the base plan on hand.
    const baseAdaptive = state.adaptive && state.adaptive.plan === state.plan ? state.adaptive.state : undefined;
    const onScreen = state.whatIf?.response.plan ?? state.plan;
    return {
      state,
      actions,
      household: state.whatIf?.response.household ?? state.profile?.household,
      plan: state.whatIf?.response.plan ?? state.plan,
      basePlan: state.plan,
      adaptive: state.whatIf ? state.whatIf.adaptive : baseAdaptive,
      baseAdaptive,
      whatIfActive: !!state.whatIf,
      styleSlots: state.stylePlans.find((entry) => entry.base === onScreen)?.slots ?? NO_SLOTS,
    };
  }, [state, actions]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
