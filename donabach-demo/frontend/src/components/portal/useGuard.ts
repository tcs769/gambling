"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { usePortal, type StepKey } from "@/lib/portal-state";

/**
 * Marks a step as visited and sends the customer back when what the screen needs is not there (a reload on a screen opened
 * directly, with nothing saved). Returns true when the screen can show its content.
 */
export function useGuard(step: StepKey, needs: "docs" | "plan" | "none" = "docs"): boolean {
  const { state, hydrated, actions } = usePortal();
  const router = useRouter();
  const ok = needs === "none" || (needs === "docs" ? state.docs !== null : state.plan !== null);
  const { visit } = actions;

  useEffect(() => {
    if (!hydrated) return;
    if (!ok) {
      router.replace(
        needs === "plan" && state.docs && state.answers ? "/goals" : needs === "plan" && state.docs ? "/review" : "/",
      );
      return;
    }
    visit(step);
  }, [hydrated, ok, needs, step, visit, router, state.docs, state.answers]);

  return hydrated && ok;
}
