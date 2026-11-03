"use client";

import type { ReactNode } from "react";
import { Btn } from "./Btn";
import styles from "./Screen.module.css";

interface Props {
  /** The h1; leave it out when the screen draws its own heading row (Invest). */
  title?: string;
  children: ReactNode;
  /** The line under the title. */
  lede?: string;
  back?: { onClick: () => void; label?: string };
  next?: { label?: string; onClick: () => void; disabled?: boolean; busy?: boolean };
  /** Extra line at the bottom (the one disclaimer on Invest and Compare). */
  footer?: ReactNode;
  /** A narrower column for the actions row (Compare is 960px wide, like its cards). */
  actionsWidth?: number;
}

/** One screen of the flow: a title, the content, and Back / Next at the bottom. */
export function Screen({ title, lede, children, back, next, footer, actionsWidth }: Props) {
  return (
    <div className={styles.screen}>
      {title !== undefined && <h1 className={styles.title}>{title}</h1>}
      {title !== undefined &&
        (lede ? <p className={`lede ${styles.lede}`}>{lede}</p> : <div className={styles.lede} />)}
      <div className={styles.body}>{children}</div>
      {(back || next) && (
        <div className={styles.actions} style={actionsWidth ? { maxWidth: actionsWidth } : undefined}>
          {back ? (
            <Btn variant="secondary" onClick={back.onClick}>
              {back.label ?? "Back"}
            </Btn>
          ) : (
            <span />
          )}
          {next && (
            <Btn onClick={next.onClick} disabled={next.disabled} busy={next.busy}>
              {next.label ?? "Next"}
            </Btn>
          )}
        </div>
      )}
      {footer}
    </div>
  );
}
