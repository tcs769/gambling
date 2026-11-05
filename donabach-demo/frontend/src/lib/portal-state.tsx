"use client";

// The portal's state: the dropped PDF (id and parsed documents), the customer's edits and confirmations, the goal answers and the
// last Invest result. One provider for the whole flow, mirrored to sessionStorage so a reload keeps it. Going back never drops
// anything: the PDF is only replaced when the customer chooses another one.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { changeLabel } from "./change-label";
import { portalApi, PortalApiError } from "./portal-api";
import type { InvestInputs, Overrides, Plan, PortalAnswers, PortalDocuments } from "./portal-types";

export type StepKey = "documents" | "review" | "goals" | "invest";

export const STEPS: { key: StepKey; label: string; href: string }[] = [
  { key: "documents", label: "Documents", href: "/" },
  { key: "review", label: "Review", href: "/review" },
  { key: "goals", label: "Goals", href: "/goals" },
  { key: "invest", label: "Invest", href: "/invest" },
];

/** Which rail step a route belongs to (Reading counts as Documents, Compare as Invest). */
export function stepOf(pathname: string): StepKey {
  if (pathname.startsWith("/review")) return "review";
  if (pathname.startsWith("/goals")) return "goals";
  if (pathname.startsWith("/invest") || pathname.startsWith("/compare")) return "invest";
  return "documents";
}

export interface PortalState {
  docs: PortalDocuments | null;
  /** The list of documents has been shown as read (Reading does not replay, and does not move on by itself, after that). */
  readDone: boolean;
  /** What the customer edited, by field key (only values that differ from the document). */
  overrides: Overrides;
  /** Flagged fields the customer confirmed (kept as printed). */
  confirmed: string[];
  answers: PortalAnswers | null;
  /** The last Invest result, and what it was built from. */
  plan: Plan | null;
  planInputs: InvestInputs | null;
  /** approved[plan_id][move_key]: the moves the customer said yes to (for the Invest screen). */
  approved: Record<string, Record<string, boolean>>;
  visited: StepKey[];
  /** The saved state has been read (not saved itself). */
  hydrated: boolean;
}

const EMPTY: PortalState = {
  docs: null,
  readDone: false,
  overrides: {},
  confirmed: [],
  answers: null,
  plan: null,
  planInputs: null,
  approved: {},
  visited: ["documents"],
  hydrated: false,
};

type Action =
  | { type: "restore"; state: PortalState | null }
  | { type: "docs"; docs: PortalDocuments }
  | { type: "readDone" }
  | { type: "override"; key: string; value: number | null }
  | { type: "confirm"; key: string }
  | { type: "answers"; answers: PortalAnswers }
  | { type: "plan"; plan: Plan; inputs: InvestInputs }
  | { type: "approve"; planId: string; moveKey: string; value: boolean }
  | { type: "visit"; step: StepKey };

function reducer(state: PortalState, action: Action): PortalState {
  switch (action.type) {
    case "restore":
      return { ...(action.state ?? state), hydrated: true };
    case "docs":
      // A new PDF starts the flow again from Review; the answers stay (they are the customer's, not the document's).
      return { ...EMPTY, docs: action.docs, answers: state.answers, visited: ["documents"], hydrated: true };
    case "readDone":
      return state.readDone ? state : { ...state, readDone: true };
    case "override": {
      const overrides = { ...state.overrides };
      if (action.value === null) delete overrides[action.key];
      else overrides[action.key] = action.value;
      return { ...state, overrides };
    }
    case "confirm":
      return state.confirmed.includes(action.key) ? state : { ...state, confirmed: [...state.confirmed, action.key] };
    case "answers":
      return { ...state, answers: action.answers };
    case "plan": {
      // A move the new plan leaves as it was (same amount and status) keeps the customer's approval of it.
      const before = state.plan;
      const kept: Record<string, boolean> = {};
      if (before) {
        const said = state.approved[before.plan_id] ?? {};
        for (const move of action.plan.portfolio.overview.moves) {
          const old = before.portfolio.overview.moves.find((m) => m.key === move.key);
          if (old && said[move.key] && old.amount === move.amount && old.status === move.status) kept[move.key] = true;
        }
      }
      const approved =
        Object.keys(kept).length > 0
          ? { ...state.approved, [action.plan.plan_id]: { ...state.approved[action.plan.plan_id], ...kept } }
          : state.approved;
      return { ...state, plan: action.plan, planInputs: action.inputs, approved };
    }
    case "approve":
      return {
        ...state,
        approved: {
          ...state.approved,
          [action.planId]: { ...state.approved[action.planId], [action.moveKey]: action.value },
        },
      };
    case "visit":
      return state.visited.includes(action.step) ? state : { ...state, visited: [...state.visited, action.step] };
  }
}

const STORAGE_KEY = "waramoug.portal.v1";

function load(): PortalState | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return { ...EMPTY, ...(JSON.parse(raw) as Partial<PortalState>), hydrated: false };
  } catch {
    return null;
  }
}

export interface InvestStatus {
  busy: boolean;
  error: string | null;
}

interface PortalActions {
  /** Load John Smith's PDF from the API. */
  useSample: () => Promise<PortalDocuments>;
  /** Send a dropped or chosen PDF. */
  upload: (file: File) => Promise<PortalDocuments>;
  markRead: () => void;
  /** Set a value, or clear it (null) to go back to what the document says. */
  setOverride: (key: string, value: number | null) => void;
  confirm: (key: string) => void;
  setAnswers: (answers: PortalAnswers) => void;
  /** Build the household and the portfolio from the current edits and answers. */
  invest: () => Promise<Plan>;
  approve: (planId: string, moveKey: string, value: boolean) => void;
  visit: (step: StepKey) => void;
}

interface PortalContextValue {
  state: PortalState;
  /** The saved state has been read (before this, nothing is known: do not redirect). */
  hydrated: boolean;
  /** The customer's name: the taxpayer name read from the documents. */
  name: string;
  investing: InvestStatus;
  actions: PortalActions;
}

const PortalContext = createContext<PortalContextValue | null>(null);

export function PortalProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, EMPTY);
  const [investing, setInvesting] = useState<InvestStatus>({ busy: false, error: null });
  const latest = useRef(state);
  useEffect(() => {
    latest.current = state;
  });
  const hydrated = state.hydrated;

  useEffect(() => {
    dispatch({ type: "restore", state: load() });
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      const { hydrated: _unused, ...saved } = state;
      void _unused;
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
    } catch {
      /* storage full or blocked: the flow still works, a reload just starts over */
    }
  }, [state, hydrated]);

  const invest = useCallback(async (): Promise<Plan> => {
    const current = latest.current;
    if (!current.docs || !current.answers) throw new PortalApiError(0, "Add your documents first.");
    setInvesting({ busy: true, error: null });
    try {
      const inputs: InvestInputs = { overrides: current.overrides, answers: current.answers };
      const { household } = await portalApi.household(current.docs.id, current.overrides, current.answers);
      const fields = current.docs.documents.flatMap((d) => d.fields);
      const plan = await portalApi.invest({
        household,
        event: current.answers.income_change ?? "none",
        previous_plan_id: current.plan?.plan_id ?? null,
        change_label: changeLabel(current.planInputs, inputs, fields),
      });
      dispatch({ type: "plan", plan, inputs });
      setInvesting({ busy: false, error: null });
      return plan;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Something went wrong.";
      setInvesting({ busy: false, error: message });
      throw error;
    }
  }, []);

  const actions = useMemo<PortalActions>(
    () => ({
      useSample: async () => {
        const docs = await portalApi.sampleDocuments();
        dispatch({ type: "docs", docs });
        return docs;
      },
      upload: async (file) => {
        const docs = await portalApi.uploadDocuments(file);
        dispatch({ type: "docs", docs });
        return docs;
      },
      markRead: () => dispatch({ type: "readDone" }),
      setOverride: (key, value) => dispatch({ type: "override", key, value }),
      confirm: (key) => dispatch({ type: "confirm", key }),
      setAnswers: (answers) => dispatch({ type: "answers", answers }),
      invest,
      approve: (planId, moveKey, value) => dispatch({ type: "approve", planId, moveKey, value }),
      visit: (step) => dispatch({ type: "visit", step }),
    }),
    [invest],
  );

  const name = useMemo(() => {
    const field = state.docs?.documents.flatMap((d) => d.fields).find((f) => f.key === "taxpayer_name");
    return typeof field?.value === "string" && field.value.trim() ? field.value : "John Smith";
  }, [state.docs]);

  const value = useMemo(
    () => ({ state, hydrated, name, investing, actions }),
    [state, hydrated, name, investing, actions],
  );
  return <PortalContext.Provider value={value}>{children}</PortalContext.Provider>;
}

export function usePortal(): PortalContextValue {
  const value = useContext(PortalContext);
  if (!value) throw new Error("usePortal must be used inside PortalProvider");
  return value;
}
