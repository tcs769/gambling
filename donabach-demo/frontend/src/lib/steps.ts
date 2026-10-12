export interface Step {
  key: string;
  label: string;
  href: string;
}

/** The seven steps of the demo, in order. Each is its own route. */
export const STEPS: Step[] = [
  { key: "upload", label: "Upload", href: "/" },
  { key: "review", label: "Review", href: "/review" },
  { key: "questions", label: "Questions", href: "/questions" },
  { key: "profile", label: "Profile", href: "/profile" },
  { key: "forecast", label: "Forecast", href: "/forecast" },
  { key: "plan", label: "Plan", href: "/plan" },
  { key: "compare", label: "Compare", href: "/compare" },
];

export function stepIndex(pathname: string): number {
  const i = STEPS.findIndex((s) => (s.href === "/" ? pathname === "/" : pathname.startsWith(s.href)));
  return i < 0 ? 0 : i;
}

export function nextStep(pathname: string): Step | undefined {
  return STEPS[stepIndex(pathname) + 1];
}

/**
 * The showcase flow: a separate four-step walk under /showcase. Wealth comes before the strategies because the flow shows the
 * advisor's wealth first (alone), then the strategies, then the wealth of both again: that screen is one step, "Wealth".
 */
export const SHOWCASE_STEPS: Step[] = [
  { key: "household", label: "Household", href: "/showcase" },
  { key: "wealth", label: "Wealth", href: "/showcase/wealth" },
  { key: "strategies", label: "Strategies", href: "/showcase/strategies" },
  { key: "whatif", label: "What if", href: "/showcase/whatif" },
];

/** True on /showcase and every page under it (not on a path that merely starts with the same letters). */
export function inShowcase(pathname: string): boolean {
  return pathname === "/showcase" || pathname.startsWith("/showcase/");
}

export function showcaseStepIndex(pathname: string): number {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const i = SHOWCASE_STEPS.findIndex((s) => path === s.href);
  return i < 0 ? 0 : i;
}
