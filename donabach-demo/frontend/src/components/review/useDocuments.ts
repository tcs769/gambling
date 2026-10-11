"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useApp, type DocState } from "@/lib/state";
import type { ParsedDocument } from "@/lib/types";

export type ReadyDoc = DocState & { parsed: ParsedDocument };
export type DocsPhase = "ready" | "loading" | "failed";

/**
 * The documents that have been read, for the screens that come after Upload. With none, demo mode
 * loads the sample documents (so any screen works when opened directly) and otherwise the user
 * is sent back to Upload.
 */
export function useReadyDocuments(): { phase: DocsPhase; docs: ReadyDoc[]; retry: () => void } {
  const { state, actions } = useApp();
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const [finished, setFinished] = useState(-1); // the last attempt that ran to the end

  const docs = state.docs.filter((d): d is ReadyDoc => d.status === "ready" && d.parsed !== undefined);
  const busy = state.loading.docs || state.docs.some((d) => d.status === "uploading" || d.status === "reading");

  useEffect(() => {
    if (docs.length > 0 || busy || finished === attempt) return;
    // A beat of delay: the saved demo-mode setting is applied just after the first render, and a
    // change in between should win.
    const timer = window.setTimeout(() => {
      if (!state.demoMode) {
        router.replace("/");
        return;
      }
      void actions.loadSamples({ animate: false }).then(() => setFinished(attempt));
    }, 80);
    return () => window.clearTimeout(timer);
  }, [docs.length, busy, finished, attempt, state.demoMode, actions, router]);

  const phase: DocsPhase = docs.length > 0 ? "ready" : finished === attempt && !busy ? "failed" : "loading";
  return { phase, docs, retry: () => setAttempt((n) => n + 1) };
}
