"use client";

// The showcase flow's shared state (/showcase, /showcase/wealth, /showcase/strategies, /showcase/whatif). It lives in the layout of
// /showcase, so the screens share one household and one set of switches. Nothing here invents a number: it stores what
// the API returned.
//
// The household answer (GET /showcase) holds everything the flow shows at first: the card, the waterfall with every
// strategy on, the whole plan's wealth over time (both measures of the advantage, worked out once) and the footer's
// note. Only the waterfall changes with the switches, and only the median advantage in it: the wealth screen reads
// `data.wealth` and never asks for anything.
//
// How a change flows. A toggle changes `enabled` at once (the switch moves), and the waterfall for the new set is asked
// of the API (POST /showcase/analysis). Until it arrives the strategies screen keeps showing the waterfall it has,
// dimmed (`computing`). Answers are remembered by the set they are for, so switching a strategy back is instant; a
// change made while an answer is on its way drops that answer (its request is aborted and, should it arrive anyway, it
// is ignored). If the API refuses, the switches go back to the set the numbers on screen are for and the API's message
// is kept in `changeError`, so what the switches say and what the numbers show never disagree for long.
//
// Asking early. The household is asked for once, by whoever needs it first: the home page's "Open the showcase" link
// asks as soon as it mounts and again when it is hovered, focused or touched (`prefetchShowcase`), so by the time the
// link is followed the answer is usually here and the first screen draws without a placeholder.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, api } from "./api";
import type { ScenarioInfo, ShowcaseResponse, ShowcaseScenario, ShowcaseWaterfall } from "./types";

export type ShowcaseStatus = "loading" | "ready" | "failed";

/** One event the household can be asked about ("Job loss next year"): its answer, on its way, or the API's refusal. */
export type ScenarioState =
  | { status: "loading" }
  | { status: "ready"; scenario: ShowcaseScenario }
  | { status: "failed"; error: string };

interface Shown {
  /** `setKey` of the set this waterfall is for (what was asked, whatever order or spelling the API answered in). */
  key: string;
  set: readonly string[];
  waterfall: ShowcaseWaterfall;
}

interface ShowcaseState {
  data: ShowcaseResponse | null;
  loadError: string | null;
  enabled: readonly string[];
  shown: Shown | null;
  changeError: string | null;
}

export interface ShowcaseActions {
  /** Switch one strategy on or off. */
  toggle: (key: string, on: boolean) => void;
  /** Switch every strategy on (true) or off (false). */
  setAll: (on: boolean) => void;
  /** Forget the message about a change the API refused. */
  dismissError: () => void;
  /** Ask for the household again after it could not be loaded. */
  reload: () => void;
  /** Show Donabach on the wealth screen (it starts with the advisor alone). Once shown it stays for the session. */
  reveal: () => void;
  /** Ask again for an event (or for the list of events) that could not be loaded. */
  retryScenario: (key: string) => void;
}

export interface ShowcaseValue {
  status: ShowcaseStatus;
  /** Why the household could not be loaded, in the API's words. */
  loadError: string | null;
  /**
   * The household, its card, the whole plan's wealth over time (`wealth`: every strategy on, never changes), the waterfall
   * with every strategy on (`waterfall`) and the footer's note.
   */
  data: ShowcaseResponse | null;
  /** The waterfall on screen. It is for the set in `waterfall.enabled`, which is a step behind `enabled` while `computing`. */
  waterfall: ShowcaseWaterfall | null;
  /** Every strategy, in the order they are switched on (the waterfall's order). */
  keys: readonly string[];
  /** The strategies the person has switched on: what the switches show. */
  enabled: readonly string[];
  /** The waterfall for `enabled` is on its way: what is on screen is for the previous set. */
  computing: boolean;
  /** The API's message when the last change could not be applied (the switches went back to what is on screen). */
  changeError: string | null;
  /** Has Donabach been shown on the wealth screen? False until the button is pressed or the strategies are opened from there. */
  revealed: boolean;
  /** The events the household can be asked about, in the API's order and words (null until the list arrives). */
  scenarios: readonly ScenarioInfo[] | null;
  /** Why the list of events could not be loaded, in the API's words. */
  scenariosError: string | null;
  /** Each event's answer by key. They are asked for as soon as the flow opens, so choosing one is usually instant. */
  scenarioStates: Readonly<Record<string, ScenarioState>>;
  actions: ShowcaseActions;
}

/** A name for a set of strategies that does not depend on the order it was written in. */
export const setKey = (keys: readonly string[]): string => [...keys].sort().join("|");

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return `The API could not be reached (${error.message}).`;
  return "Something went wrong.";
}

const ShowcaseContext = createContext<ShowcaseValue | null>(null);

// One request for the household at a time, shared by every mount that asks while it is on its way (in development React
// mounts the provider twice, and the API should not be asked twice for the same thing). The answer is kept for a minute
// for a flow that opens after it was asked for; a later visit asks again, so a household the API has changed is not
// shown stale.
const FRESH_FOR_MS = 60_000;
let loading: Promise<ShowcaseResponse> | null = null;
let loaded: { response: ShowcaseResponse; at: number } | null = null;

/** The household as it was asked for a moment ago (null when it was not, or too long ago). */
function freshHousehold(): ShowcaseResponse | null {
  return loaded !== null && Date.now() - loaded.at < FRESH_FOR_MS ? loaded.response : null;
}

function loadHousehold(): Promise<ShowcaseResponse> {
  loading ??= api
    .showcase()
    .then((response) => {
      loaded = { response, at: Date.now() };
      return response;
    })
    .finally(() => {
      loading = null;
    });
  return loading;
}

/** The household: the answer asked for a moment ago, else the one on its way, else a new request. */
function household(): Promise<ShowcaseResponse> {
  const asked = freshHousehold();
  return asked ? Promise.resolve(asked) : loadHousehold();
}

// The events ("Job loss next year", "Market drops 30% next year") are asked for the same way: one request each at a time,
// shared by every mount that asks, and the answer kept for a minute. The API has worked them out at start-up, so each
// answers at once. They are asked for as soon as the flow opens (the provider mounts), so that choosing one on the
// what-if screen shows it with no wait.
const scenarioListing: {
  loading: Promise<ScenarioInfo[]> | null;
  loaded: { value: ScenarioInfo[]; at: number } | null;
} = {
  loading: null,
  loaded: null,
};
const scenarioAnswers = new Map<
  string,
  { loading: Promise<ShowcaseScenario> | null; loaded: { value: ShowcaseScenario; at: number } | null }
>();

function scenarioList(): Promise<ScenarioInfo[]> {
  const { loaded } = scenarioListing;
  if (loaded && Date.now() - loaded.at < FRESH_FOR_MS) return Promise.resolve(loaded.value);
  scenarioListing.loading ??= api
    .showcaseScenarios()
    .then((value) => {
      scenarioListing.loaded = { value, at: Date.now() };
      return value;
    })
    .finally(() => {
      scenarioListing.loading = null;
    });
  return scenarioListing.loading;
}

function scenarioAnswer(key: string): Promise<ShowcaseScenario> {
  const entry = scenarioAnswers.get(key) ?? { loading: null, loaded: null };
  scenarioAnswers.set(key, entry);
  if (entry.loaded && Date.now() - entry.loaded.at < FRESH_FOR_MS) return Promise.resolve(entry.loaded.value);
  entry.loading ??= api
    .showcaseScenario(key)
    .then((value) => {
      entry.loaded = { value, at: Date.now() };
      return value;
    })
    .finally(() => {
      entry.loading = null;
    });
  return entry.loading;
}

/**
 * Start asking the API for the household now, so it is here when the flow opens. It does nothing when the household is
 * already here (or on its way); a failure is left for the flow to report when it asks itself.
 */
export function prefetchShowcase(): void {
  if (freshHousehold() !== null || loading !== null) return;
  loadHousehold().catch(() => undefined);
}

/** What the screens start from once the household is in hand: every strategy on, and the waterfall for that. */
function readyState(response: ShowcaseResponse): ShowcaseState & { data: ShowcaseResponse; shown: Shown } {
  const set = response.waterfall.enabled;
  return {
    data: response,
    loadError: null,
    enabled: set,
    shown: { key: setKey(set), set, waterfall: response.waterfall },
    changeError: null,
  };
}

const EMPTY: ShowcaseState = { data: null, loadError: null, enabled: [], shown: null, changeError: null };

export function ShowcaseProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ShowcaseState>(() => {
    const asked = freshHousehold();
    return asked ? readyState(asked) : EMPTY;
  });
  const [attempt, setAttempt] = useState(0);
  // Donabach is shown on the wealth screen once the button is pressed or the strategies are opened from the advisor-only
  // view; it is state, not the address, so a reload starts again with the advisor alone.
  const [revealed, setRevealed] = useState(false);
  const [scenarios, setScenarios] = useState<readonly ScenarioInfo[] | null>(null);
  const [scenariosError, setScenariosError] = useState<string | null>(null);
  const [scenarioStates, setScenarioStates] = useState<Readonly<Record<string, ScenarioState>>>({});
  const [scenarioAttempt, setScenarioAttempt] = useState(0);
  const scenariosRef = useRef<readonly ScenarioInfo[] | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Everything the API has answered, by the set it is for.
  const answers = useRef(new Map<string, ShowcaseWaterfall>());
  // The request for the latest change, if one is on its way. Only ever one: a newer change aborts the older request.
  const pending = useRef<AbortController | null>(null);
  // What the switches say right now (a second change in the same tick builds on the first), what is on screen, and
  // every strategy: read from event handlers and answers, never while rendering.
  const enabledNow = useRef<readonly string[]>([]);
  const shownNow = useRef<Shown | null>(null);
  const keysRef = useRef<readonly string[]>([]);

  // The household and its waterfall with every strategy on.
  useEffect(() => {
    let current = true;
    /** Make `response` what the switches and the answers start from. Returns the state the screens start in. */
    const begin = (response: ShowcaseResponse) => {
      const next = readyState(response);
      answers.current.clear();
      answers.current.set(next.shown.key, next.shown.waterfall);
      keysRef.current = next.shown.waterfall.bars.map((bar) => bar.key);
      enabledNow.current = next.shown.set;
      shownNow.current = next.shown;
      return next;
    };
    household().then(
      (response) => {
        if (!current) return;
        const next = begin(response);
        // A flow that opened with the household in hand already shows it: only the bookkeeping above was left to do.
        setState((s) => (s.data === response ? s : next));
      },
      (error: unknown) => {
        if (current) setState((s) => ({ ...s, loadError: errorMessage(error) }));
      },
    );
    return () => {
      current = false;
    };
  }, [attempt]);

  /** Ask for one event, marking it as on its way until the answer (or the refusal) arrives. */
  const loadScenario = useCallback((key: string) => {
    setScenarioStates((all) => ({ ...all, [key]: { status: "loading" } }));
    scenarioAnswer(key).then(
      (scenario) => {
        if (mounted.current) setScenarioStates((all) => ({ ...all, [key]: { status: "ready", scenario } }));
      },
      (error: unknown) => {
        if (mounted.current)
          setScenarioStates((all) => ({ ...all, [key]: { status: "failed", error: errorMessage(error) } }));
      },
    );
  }, []);

  // The events: the list, then each one, as soon as the flow opens.
  useEffect(() => {
    let current = true;
    scenarioList().then(
      (list) => {
        if (!current) return;
        scenariosRef.current = list;
        setScenarios(list);
        setScenariosError(null);
        for (const info of list) loadScenario(info.key);
      },
      (error: unknown) => {
        if (current) setScenariosError(errorMessage(error));
      },
    );
    return () => {
      current = false;
    };
  }, [scenarioAttempt, loadScenario]);

  // Nobody is waiting for an answer once the flow is left.
  useEffect(() => () => pending.current?.abort(), []);

  /** Make `next` the set that is switched on, and make sure the strategies screen gets the waterfall for it. */
  const apply = useCallback((next: readonly string[]) => {
    const key = setKey(next);
    pending.current?.abort();
    pending.current = null;
    enabledNow.current = next;
    const known = answers.current.get(key);
    if (known) {
      const shown: Shown = { key, set: next, waterfall: known };
      shownNow.current = shown;
      setState((s) => ({ ...s, enabled: next, shown, changeError: null }));
      return;
    }
    const controller = new AbortController();
    pending.current = controller;
    setState((s) => ({ ...s, enabled: next, changeError: null }));
    api.showcaseAnalysis(next, controller.signal).then(
      (waterfall) => {
        if (controller.signal.aborted) return;
        pending.current = null;
        answers.current.set(key, waterfall);
        const shown: Shown = { key, set: next, waterfall };
        shownNow.current = shown;
        setState((s) => ({ ...s, shown }));
      },
      (error: unknown) => {
        if (controller.signal.aborted) return;
        pending.current = null;
        // The switches go back to the set the numbers on screen are for.
        const back = shownNow.current?.set ?? next;
        enabledNow.current = back;
        setState((s) => ({ ...s, enabled: back, changeError: errorMessage(error) }));
      },
    );
  }, []);

  // A safety net for the one thing that must never last: switches and numbers that disagree with no answer on its way
  // (a request dropped by a hot reload, say). The screen then asks for the waterfall of the set that is switched on.
  const { shown, enabled } = state;
  useEffect(() => {
    if (shown && shown.key !== setKey(enabled) && pending.current === null) apply(enabled);
  }, [shown, enabled, apply]);

  const actions = useMemo<ShowcaseActions>(
    () => ({
      toggle: (key, on) => apply(keysRef.current.filter((k) => (k === key ? on : enabledNow.current.includes(k)))),
      setAll: (on) => apply(on ? keysRef.current : []),
      dismissError: () => setState((s) => ({ ...s, changeError: null })),
      reload: () => {
        setState((s) => ({ ...s, loadError: null }));
        setAttempt((n) => n + 1);
      },
      reveal: () => setRevealed(true),
      retryScenario: (key) => {
        if (scenariosRef.current === null) {
          setScenariosError(null);
          setScenarioAttempt((n) => n + 1);
        } else loadScenario(key);
      },
    }),
    [apply, loadScenario],
  );

  const value = useMemo<ShowcaseValue>(() => {
    const { data, loadError, enabled, shown, changeError } = state;
    return {
      status: shown && data ? "ready" : loadError ? "failed" : "loading",
      loadError,
      data,
      waterfall: shown?.waterfall ?? null,
      keys: data ? data.waterfall.bars.map((bar) => bar.key) : [],
      enabled,
      computing: !!shown && shown.key !== setKey(enabled),
      changeError,
      revealed,
      scenarios,
      scenariosError,
      scenarioStates,
      actions,
    };
  }, [state, actions, revealed, scenarios, scenariosError, scenarioStates]);

  return <ShowcaseContext.Provider value={value}>{children}</ShowcaseContext.Provider>;
}

export function useShowcase(): ShowcaseValue {
  const value = useContext(ShowcaseContext);
  if (!value) throw new Error("useShowcase must be used inside the showcase layout");
  return value;
}
