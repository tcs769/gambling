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
