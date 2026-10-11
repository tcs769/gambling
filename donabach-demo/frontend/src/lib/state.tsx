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
import type {
  Answers,
  DocumentInfo,
  ForecastResponse,
  Household,
  HouseholdEdits,
  HouseholdProfile,
  MissingField,
  ParsedDocument,
  PlanResponse,
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
  roth_balance: 30_000,
  cash: 40_000,
  social_security_annual: 50_000,
  social_security_start_age: 67,
};

/** Each upload/reading stage stays on screen at least this long so it is legible on a recording. */
const STAGE_MS = 450;
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

export interface WhatIfState {
  presets: Preset[];
  edits: Partial<HouseholdEdits>;
  response: WhatIfResponse;
}

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
  whatIf?: WhatIfState;
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
  whatIfActive: boolean;
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
            patch({ plan: await api.plan(household, current().demoMode), whatIf: undefined });
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
          patch({ whatIf: { presets, edits, response }, error: undefined });
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

  const value = useMemo<AppContextValue>(
    () => ({
      state,
      actions,
      household: state.whatIf?.response.household ?? state.profile?.household,
      plan: state.whatIf?.response.plan ?? state.plan,
      basePlan: state.plan,
      whatIfActive: !!state.whatIf,
    }),
    [state, actions],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
