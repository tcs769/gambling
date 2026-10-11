"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Panel, PanelTitle } from "@/components/ui";
import { DocumentList } from "@/components/upload/DocumentList";
import { DropZone } from "@/components/upload/DropZone";
import { preloadPdfjs } from "@/components/review/pdfjs";
import { useApp } from "@/lib/state";
import styles from "@/components/upload/Upload.module.css";

// Demo mode preloads the sample documents the first time Upload opens with nothing on it. Taking
// the documents away afterwards is a choice, so it does not bring them back.
let seeded = false;

export default function UploadPage() {
  const { state, actions } = useApp();
  const router = useRouter();
  const { docs, demoMode } = state;
  // How many times the sample documents have been asked for (so an old error is not blamed on them).
  const [sampleRuns, setSampleRuns] = useState(0);
  const loadSamples = () => void actions.loadSamples().then(() => setSampleRuns((n) => n + 1));

  useEffect(() => {
    if (!demoMode || docs.length > 0 || seeded) return;
    // Wait a beat: the empty drop zone is worth seeing, and the saved demo-mode setting is
    // applied just after the first render (a change in between cancels this).
    const timer = window.setTimeout(() => {
      seeded = true;
      void actions.loadSamples().then(() => setSampleRuns((n) => n + 1));
    }, 450);
    return () => window.clearTimeout(timer);
  }, [demoMode, docs.length, actions]);

  useEffect(() => {
    preloadPdfjs();
    router.prefetch("/review");
  }, [router]);

  const busy = docs.some((d) => d.status === "uploading" || d.status === "reading");
  const usable = docs.filter((d) => d.status === "ready" && d.info.kind !== "unknown");
  const canContinue = usable.length > 0 && !busy;

  let hint = "Add at least one document to continue.";
  if (busy) hint = "Reading your documents…";
  else if (canContinue) hint = usable.length === 1 ? "1 document ready" : `${usable.length} documents ready`;
  else if (docs.length > 0) hint = "None of these could be read. Try the sample documents.";

  const sampleError =
    sampleRuns > 0 && docs.length === 0 && state.error
      ? `We could not load the sample documents (${state.error}). Check that the API is running, then try again.`
      : null;

  return (
    <div className={styles.page}>
      <DropZone
        hasDocs={docs.length > 0}
        loadingSamples={state.loading.docs && docs.length === 0}
        error={sampleError}
        onFiles={(files) => void actions.uploadFiles(files)}
        onSamples={loadSamples}
      />

      <Panel aria-labelledby="documents-title">
        <PanelTitle aside={docs.length > 0 ? `${docs.length} ${docs.length === 1 ? "file" : "files"}` : undefined}>
          <span id="documents-title">Your documents</span>
        </PanelTitle>
        <div className={styles.body}>
          <DocumentList docs={docs} onRemove={actions.removeDoc} />
        </div>
        <div className={styles.footer}>
          <p className={styles.hint} role="status">
            {hint}
          </p>
          <Button arrow disabled={!canContinue} onClick={() => router.push("/review")}>
            Review extracted numbers
          </Button>
        </div>
      </Panel>
    </div>
  );
}
