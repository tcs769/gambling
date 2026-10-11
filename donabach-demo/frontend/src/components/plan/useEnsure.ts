"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useApp } from "@/lib/state";

export type EnsureStatus = "loading" | "ready" | "failed";

/**
 * Makes sure the forecast or the plan exists when a screen opens (in demo mode that bootstraps the
 * sample documents, the household and the result). If there is nothing to build from, the user is
 * sent back to the first screen; if the API itself failed, the screen shows the error instead.
 */
export function useEnsure(kind: "forecast" | "plan"): {
  status: EnsureStatus;
  error?: string;
  retry: () => void;
} {
  const { state, actions } = useApp();
  const router = useRouter();
  const have = kind === "plan" ? !!state.plan : !!state.forecast;
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (have) return;
    let live = true;
    const ensure = kind === "plan" ? actions.ensurePlan : actions.ensureForecast;
    ensure().then((ok) => {
      if (live && !ok) setFailed(true);
    });
    return () => {
      live = false;
    };
  }, [have, kind, actions, attempt]);

  const error = state.error;
  useEffect(() => {
    if (failed && !error && !have) router.replace("/");
  }, [failed, error, have, router]);

  return {
    status: have ? "ready" : failed ? "failed" : "loading",
    error,
    retry: () => {
      setFailed(false);
      setAttempt((n) => n + 1);
    },
  };
}
