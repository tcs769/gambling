"use client";

import { useEffect, useState, type RefObject } from "react";

/**
 * The width of an element, kept up to date as the window or its container changes (0 until it has been measured).
 * Used where a layout depends on the room a piece has rather than on the window: whether a label fits inside a bar,
 * whether a chart has room for the labels at the ends of its lines.
 */
export function useElementWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}
