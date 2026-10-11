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

/** The showcase flow: a separate three-step walk (household, strategies, wealth) under /showcase. */
export const SHOWCASE_STEPS: Step[] = [
  { key: "household", label: "Household", href: "/showcase" },
  { key: "strategies", label: "Strategies", href: "/showcase/strategies" },
  { key: "wealth", label: "Wealth", href: "/showcase/wealth" },
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
