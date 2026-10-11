import { count, dollars } from "@/lib/format";
import type { PlanResponse, PlanSettings } from "@/lib/types";

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

/**
 * What a certainty equivalent is, in the words the Comparison screen uses: the guaranteed amount that would feel as good
 * as the uncertain outcome, with the risk aversion and the floor behind it.
 */
export function scoreDefinition(settings: Pick<PlanSettings, "risk_aversion" | "wealth_floor">): string {
  return `the guaranteed amount that would feel as good as the uncertain outcome; risk aversion ${settings.risk_aversion}, with a ${dollars(settings.wealth_floor)} floor`;
}

/**
 * What a score is, in the words the Comparison screen uses wherever one appears (the ranked table): certainty-equivalent
 * wealth at the horizon, with its definition.
 */
export function scoreWords(settings: Pick<PlanSettings, "horizon_age" | "risk_aversion" | "wealth_floor">): string {
  return `certainty-equivalent wealth at ${settings.horizon_age} (${scoreDefinition(settings)})`;
}
