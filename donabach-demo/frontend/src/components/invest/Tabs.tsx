"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";
import styles from "./Tabs.module.css";

export interface TabSpec<K extends string> {
  key: K;
  label: string;
}

interface Props<K extends string> {
  /** The name of the tab list for a screen reader. */
  label: string;
  /** Prefix for the element ids (unique on the page). */
  idPrefix: string;
  tabs: TabSpec<K>[];
  value: K;
  onChange: (key: K) => void;
  /** "line": underlined page tabs. "pill": a smaller row inside a tab. */
  variant?: "line" | "pill";
  children: ReactNode;
}

/** A tab list with the keyboard pattern: arrows, Home and End move and select; only the selected tab is in the Tab order. */
export function Tabs<K extends string>({
  label,
  idPrefix,
  tabs,
  value,
  onChange,
  variant = "line",
  children,
}: Props<K>) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const move = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next = -1;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    if (next < 0) return;
    event.preventDefault();
    const key = tabs[next].key;
    onChange(key);
    refs.current[key]?.focus();
  };

  return (
    <div>
      <div role="tablist" aria-label={label} className={`${styles.list} ${styles[variant]}`}>
        {tabs.map((tab, index) => {
          const selected = tab.key === value;
          return (
            <button
              key={tab.key}
              ref={(el) => {
                refs.current[tab.key] = el;
              }}
              type="button"
              role="tab"
              id={`${idPrefix}-tab-${tab.key}`}
              aria-selected={selected}
              aria-controls={`${idPrefix}-panel-${tab.key}`}
              tabIndex={selected ? 0 : -1}
              className={styles.tab}
              onClick={() => onChange(tab.key)}
              onKeyDown={(event) => move(event, index)}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={`${idPrefix}-panel-${value}`}
        aria-labelledby={`${idPrefix}-tab-${value}`}
        className={styles.panel}
      >
        {children}
      </div>
    </div>
  );
}
