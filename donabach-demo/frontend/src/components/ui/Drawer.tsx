"use client";

import { useEffect, useId, useLayoutEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";
import styles from "./Drawer.module.css";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  /** Small line above the title. */
  eyebrow?: ReactNode;
  /** Extra header controls, placed before the close button (e.g. previous and next). */
  actions?: ReactNode;
  children: ReactNode;
  width?: number;
  /** Where focus goes when the drawer closes. Defaults to whatever had focus when it opened. */
  restoreFocus?: () => HTMLElement | null;
}

/**
 * A side panel that slides in from the right, under the app header. It is not modal: the page
 * stays visible and usable beside it (the selected row stays highlighted, other rows can be
 * clicked). Focus moves into it when it opens and back out when it closes, and Escape closes it.
 */
export function Drawer({ open, onClose, title, eyebrow, actions, children, width = 480, restoreFocus }: DrawerProps) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  // The latest callbacks, read from effects that must not re-run when their identity changes.
  const latest = useRef({ onClose, restoreFocus });
  useEffect(() => {
    latest.current = { onClose, restoreFocus };
  });

  // Sit just under the sticky app header, wherever it ends.
  useLayoutEffect(() => {
    if (!open || !panel.current) return;
    const header = Array.from(document.querySelectorAll("header")).find((h) => !h.closest("[role=dialog]"));
    panel.current.style.top = `${Math.max(0, header?.getBoundingClientRect().bottom ?? 0)}px`;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panel.current?.focus({ preventScroll: true });
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        latest.current.onClose();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      const target = latest.current.restoreFocus?.() ?? opener;
      if (target?.isConnected) target.focus({ preventScroll: true });
    };
  }, [open]);

  if (!open) return null;
  return createPortal(
    <div
      ref={panel}
      className={styles.drawer}
      style={{ width }}
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      tabIndex={-1}
    >
      <header className={styles.header}>
        <div className={styles.heading}>
          {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
          <h2 id={titleId}>{title}</h2>
        </div>
        <div className={styles.controls}>
          {actions}
          <button type="button" className={styles.close} onClick={onClose} aria-label="Close">
            <Icon name="close" size={20} />
          </button>
        </div>
      </header>
      <div className={styles.body}>{children}</div>
    </div>,
    document.body,
  );
}
