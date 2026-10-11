/** Smooth scrolling, unless the user has asked for less motion. Call it from an event handler or effect. */
export const scrollBehavior = (): ScrollBehavior =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
