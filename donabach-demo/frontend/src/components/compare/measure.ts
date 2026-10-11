import { count } from "@/lib/format";
import type { PlanResponse } from "@/lib/types";

/**
 * How many futures the search screens the whole menu on before it scores the best few on all of them.
 * The API does not report it (`PlanSettings` has the menu size and the search's futures, not this), so it
 * is typed copy here: it mirrors SCREEN_PATHS in the backend's planner/search.py.
 */
export const SCREEN_FUTURES = 100;

/** The strategies the table lists, out of the whole menu: "Best 150 of 4,032 strategies", or all of them. */
export function menuSummary(plan: PlanResponse): { listed: number; menu: number; screened: boolean } {
  const listed = plan.searched.length;
  const menu = plan.settings.strategies_searched;
  return { listed, menu, screened: listed < menu };
}

/**
 * One sentence on what the ranked table holds. With the whole menu screened it says so ("Best 150 of 4,032
 * strategies: every strategy was screened on 100 futures and the best 150 were scored on all 400"); a short
 * menu (the model's candidates, or a small search) was scored on every future.
 */
export function searchedCaption(plan: PlanResponse): string {
  const { listed, menu, screened } = menuSummary(plan);
  const searchPaths = count(plan.settings.n_paths);
  if (screened) {
    return `Best ${count(listed)} of ${count(menu)} strategies: every strategy was screened on ${count(SCREEN_FUTURES)} futures and the best ${count(listed)} were scored on all ${searchPaths}.`;
  }
  return `${count(listed)} strategies, all scored on the same ${searchPaths} futures.`;
}
