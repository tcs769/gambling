"use client";

// The showcase flow's shared state (/showcase, /showcase/strategies, /showcase/wealth). It lives in the layout of
// /showcase, so the wealth screen shows what was chosen on the strategies screen: the household the API describes,
// which strategies are switched on, and the analysis (waterfall, headline, wealth lines) for that set. Nothing here
// invents a number: it stores what the API returned.
//
// How a change flows. A toggle changes `enabled` at once (the switch moves), and the analysis for the new set is
// asked of the API (POST /showcase/analysis). Until it arrives the screens keep showing the analysis they have, dimmed
// (`computing`). Answers are remembered by the set they are for, so switching a strategy back is instant; a change
// made while an answer is on its way drops that answer (its request is aborted and, should it arrive anyway, it is
// ignored). If the API refuses, the switches go back to the set the numbers on screen are for and the API's message
// is kept in `changeError`, so what the switches say and what the numbers show never disagree for long.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, api } from "./api";
import type { ShowcaseAnalysis, ShowcaseResponse } from "./types";

export type ShowcaseStatus = "loading" | "ready" | "failed";

interface Shown {
  /** `setKey` of the set this analysis is for (what was asked, whatever order or spelling the API answered in). */
  key: string;
  set: readonly string[];
  analysis: ShowcaseAnalysis;
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
}

export interface ShowcaseValue {
  status: ShowcaseStatus;
  /** Why the household could not be loaded, in the API's words. */
  loadError: string | null;
  /** The household, its card and the analysis with every strategy on. */
  data: ShowcaseResponse | null;
  /** The analysis on screen. It is for the set in `analysis.enabled`, which is a step behind `enabled` while `computing`. */
  analysis: ShowcaseAnalysis | null;
  /** Every strategy, in the order they are switched on (the waterfall's order). */
  keys: readonly string[];
  /** The strategies the person has switched on: what the switches show. */
  enabled: readonly string[];
  /** The analysis for `enabled` is on its way: what is on screen is for the previous set. */
  computing: boolean;
  /** The API's message when the last change could not be applied (the switches went back to what is on screen). */
  changeError: string | null;
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

export function ShowcaseProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ShowcaseState>({
    data: null,
    loadError: null,
    enabled: [],
    shown: null,
    changeError: null,
  });
  const [attempt, setAttempt] = useState(0);

  // Everything the API has answered, by the set it is for.
  const answers = useRef(new Map<string, ShowcaseAnalysis>());
  // The request for the latest change, if one is on its way. Only ever one: a newer change aborts the older request.
  const pending = useRef<AbortController | null>(null);
  // What the switches say right now (a second change in the same tick builds on the first), what is on screen, and
  // every strategy: read from event handlers and answers, never while rendering.
  const enabledNow = useRef<readonly string[]>([]);
  const shownNow = useRef<Shown | null>(null);
  const keysRef = useRef<readonly string[]>([]);

  // The household and its analysis with every strategy on.
  useEffect(() => {
    const controller = new AbortController();
    api.showcase(controller.signal).then(
      (response) => {
        const set = response.analysis.enabled;
        const key = setKey(set);
        answers.current.clear();
        answers.current.set(key, response.analysis);
        const shown: Shown = { key, set, analysis: response.analysis };
        keysRef.current = response.analysis.bars.map((bar) => bar.key);
        enabledNow.current = set;
        shownNow.current = shown;
        setState({ data: response, loadError: null, enabled: set, shown, changeError: null });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setState((s) => ({ ...s, loadError: errorMessage(error) }));
      },
    );
    return () => controller.abort();
  }, [attempt]);

  // Nobody is waiting for an answer once the flow is left.
  useEffect(() => () => pending.current?.abort(), []);

  /** Make `next` the set that is switched on, and make sure the screens get the analysis for it. */
  const apply = useCallback((next: readonly string[]) => {
    const key = setKey(next);
    pending.current?.abort();
    pending.current = null;
    enabledNow.current = next;
    const known = answers.current.get(key);
    if (known) {
      const shown: Shown = { key, set: next, analysis: known };
      shownNow.current = shown;
      setState((s) => ({ ...s, enabled: next, shown, changeError: null }));
      return;
    }
    const controller = new AbortController();
    pending.current = controller;
    setState((s) => ({ ...s, enabled: next, changeError: null }));
    api.showcaseAnalysis(next, controller.signal).then(
      (analysis) => {
        if (controller.signal.aborted) return;
        pending.current = null;
        answers.current.set(key, analysis);
        const shown: Shown = { key, set: next, analysis };
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

  const actions = useMemo<ShowcaseActions>(
    () => ({
      toggle: (key, on) => apply(keysRef.current.filter((k) => (k === key ? on : enabledNow.current.includes(k)))),
      setAll: (on) => apply(on ? keysRef.current : []),
      dismissError: () => setState((s) => ({ ...s, changeError: null })),
      reload: () => {
        setState((s) => ({ ...s, loadError: null }));
        setAttempt((n) => n + 1);
      },
    }),
    [apply],
  );

  const value = useMemo<ShowcaseValue>(() => {
    const { data, loadError, enabled, shown, changeError } = state;
    return {
      status: shown && data ? "ready" : loadError ? "failed" : "loading",
      loadError,
      data,
      analysis: shown?.analysis ?? null,
      keys: data ? data.analysis.bars.map((bar) => bar.key) : [],
      enabled,
      computing: !!shown && shown.key !== setKey(enabled),
      changeError,
      actions,
    };
  }, [state, actions]);

  return <ShowcaseContext.Provider value={value}>{children}</ShowcaseContext.Provider>;
}

export function useShowcase(): ShowcaseValue {
  const value = useContext(ShowcaseContext);
  if (!value) throw new Error("useShowcase must be used inside the showcase layout");
  return value;
}
