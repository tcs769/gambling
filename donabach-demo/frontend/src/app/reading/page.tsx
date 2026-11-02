"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui";
import { Screen } from "@/components/portal/Screen";
import { useGuard } from "@/components/portal/useGuard";
import { documentLabel } from "@/lib/portal-format";
import { usePortal } from "@/lib/portal-state";
import styles from "./Reading.module.css";

/** One document appears about every half second, so the reading shows as progress. */
const STEP_MS = 500;
/** A beat on the finished list before it moves on. */
const SETTLE_MS = 900;

export default function ReadingPage() {
  const { state, actions } = usePortal();
  const router = useRouter();
  const ready = useGuard("documents");
  const documents = state.docs?.documents ?? [];
  // Coming back to this screen after it has run shows the list as it was, and does not move on by itself.
  const replay = !state.readDone;
  const [shown, setShown] = useState(0);
  const count = replay ? shown : documents.length;
  const finished = documents.length > 0 && count >= documents.length;

  useEffect(() => {
    if (!ready || !replay || documents.length === 0) return;
    const timer = window.setTimeout(
      () => {
        if (shown < documents.length) setShown(shown + 1);
        else {
          actions.markRead();
          router.replace("/review");
        }
      },
      shown < documents.length ? STEP_MS : SETTLE_MS,
    );
    return () => window.clearTimeout(timer);
  }, [ready, replay, shown, documents.length, actions, router]);

  useEffect(() => {
    router.prefetch("/review");
  }, [router]);

  if (!ready) return null;

  return (
    <Screen
      title="Reading your documents"
      back={{ onClick: () => router.push("/") }}
      next={{ onClick: () => router.push("/review"), disabled: !finished }}
    >
      <div
        className={styles.progress}
        role="progressbar"
        aria-label="Reading"
        aria-valuemin={0}
        aria-valuemax={documents.length}
        aria-valuenow={count}
      >
        <span className={styles.bar} style={{ width: `${documents.length ? (count / documents.length) * 100 : 0}%` }} />
      </div>
      <p className={`${styles.count} num`} role="status">
        {finished ? "Done" : "Reading…"} {count} of {documents.length}
      </p>
      <ul className={styles.list} aria-label="Documents found" data-testid="read-list">
        {documents.slice(0, count).map((doc) => (
          <li key={`${doc.doc_kind}-${doc.first_page}`} className={styles.item} data-testid="read-item">
            <span className={styles.tick} aria-hidden="true">
              <Icon name="check" size={16} strokeWidth={2.6} />
            </span>
            <span className={styles.name}>{documentLabel(doc)}</span>
            <span className={`${styles.pages} num`}>
              {doc.first_page === doc.last_page ? `Page ${doc.first_page}` : `Pages ${doc.first_page}–${doc.last_page}`}
            </span>
          </li>
        ))}
      </ul>
    </Screen>
  );
}
