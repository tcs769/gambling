"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Screen } from "@/components/portal/Screen";
import { useGuard } from "@/components/portal/useGuard";
import { documentLabel } from "@/lib/portal-format";
import { usePortal } from "@/lib/portal-state";
import styles from "./Reading.module.css";

/** The bar moves 5% every 110 ms (2.2 s from empty to full), then a beat on the finished list before Review. */
const TICK_PERCENT = 5;
const TICK_MS = 110;
const SETTLE_MS = 600;
/** The last document shows as found just before the bar is full. */
const LAST_AT = 95;

export default function ReadingPage() {
  const { state, actions } = usePortal();
  const router = useRouter();
  const ready = useGuard("documents");
  const documents = state.docs?.documents ?? [];
  // Coming back to this screen after it has run shows the finished list, and does not move on by itself.
  const replay = !state.readDone;
  const [shownPercent, setShownPercent] = useState(0);
  const percent = replay ? shownPercent : 100;

  useEffect(() => {
    if (!ready || !replay || documents.length === 0) return;
    const timer = window.setTimeout(
      () => {
        if (shownPercent < 100) setShownPercent(Math.min(100, shownPercent + TICK_PERCENT));
        else {
          actions.markRead();
          router.replace("/review");
        }
      },
      shownPercent < 100 ? TICK_MS : SETTLE_MS,
    );
    return () => window.clearTimeout(timer);
  }, [ready, replay, shownPercent, documents.length, actions, router]);

  useEffect(() => {
    router.prefetch("/review");
  }, [router]);

  if (!ready || !state.docs) return null;

  // The i-th of n documents is found a quarter of the way along for four, and so on: the last one just before the end.
  const foundAt = (i: number) => Math.min(LAST_AT, Math.round(((i + 1) / documents.length) * 100));

  return (
    <Screen
      title="Reading your documents"
      lede="This takes a few seconds."
      back={replay ? undefined : { onClick: () => router.push("/") }}
      next={replay ? undefined : { onClick: () => router.push("/review") }}
    >
      <div className={styles.filecard}>
        <div className={styles.fname}>
          <span>{state.docs.name}</span>
          <span className="num" data-testid="read-percent">
            {percent}%
          </span>
        </div>
        <div
          className={styles.bar}
          role="progressbar"
          aria-label="Reading"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
        >
          <i style={{ width: `${percent}%` }} />
        </div>
        <ul className={styles.found} aria-label="Documents found" data-testid="read-list" role="status">
          {documents.map((doc, i) => {
            const found = percent >= foundAt(i);
            return (
              <li
                key={`${doc.doc_kind}-${doc.first_page}`}
                className={found ? styles.ok : undefined}
                data-testid="read-item"
                data-found={found}
              >
                <span>{documentLabel(doc)}</span>
                <span>{found ? "Found" : "Waiting"}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </Screen>
  );
}
