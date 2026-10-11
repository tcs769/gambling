"use client";

import { useEffect, useState } from "react";

/**
 * The width of an element, kept up to date as the window or its container changes (0 until it has been measured).
 * Used where a layout depends on the room a piece has rather than on the window: whether a label fits inside a bar,
 * how many ticks an axis can carry, whether a chart has room for the labels at the ends of its lines.
 *
 * It hands back a callback ref: an element that goes away and comes back (a chart that is swapped for its table and
 * back) is measured again.
 */
export function useElementWidth<T extends HTMLElement>(): [(node: T | null) => void, number] {
  const [node, setNode] = useState<T | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(node);
    return () => observer.disconnect();
  }, [node]);
  return [setNode, width];
}
