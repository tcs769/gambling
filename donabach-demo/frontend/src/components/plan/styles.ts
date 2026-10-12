// The planning styles and the words for them. The API names the three families only by key; these are the app's words for
// them (the figures and the plans themselves are always the API's).
import type { PlanStyleView } from "@/lib/state";
import type { PlanningStyle } from "@/lib/types";

/** The three styles in the order the switch and the side-by-side view list them. */
export const STYLES: readonly PlanningStyle[] = ["equity_first", "balanced", "liability_matched"];

export const STYLE_NAME: Record<PlanningStyle, string> = {
  equity_first: "Equity-first",
  balanced: "Balanced",
  liability_matched: "Liability-matched",
};

/** What the switch offers: each style, then all of them next to each other. */
export const VIEW_NAME: Record<PlanStyleView, string> = { ...STYLE_NAME, all: "All three side by side" };
export const VIEWS: readonly PlanStyleView[] = [...STYLES, "all"];

/** One sentence on how the style plans (no figures: those come with the plan). */
export const STYLE_BLURB: Record<PlanningStyle, string> = {
  equity_first: "Bonds and private credit hold the next few years of spending, and everything else is in stocks.",
  balanced: "A share of the portfolio in stocks that glides down with age.",
  liability_matched:
    "Chosen under two limits: stocks are rarely sold in a falling year to pay for goals or spending, and running out of money is no more likely than with a good RIA.",
};

/** What the switch's current setting does, for the line under it. */
export const VIEW_BLURB: Record<PlanStyleView, string> = {
  ...STYLE_BLURB,
  all: "The same household planned in each of the three styles, on the same simulated futures, with the plans next to each other.",
};
