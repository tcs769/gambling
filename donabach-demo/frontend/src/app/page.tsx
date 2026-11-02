"use client";

import { useEffect, useRef, useState, type DragEvent } from "react";
import { useRouter } from "next/navigation";
import { Btn } from "@/components/portal/Btn";
import { Icon } from "@/components/ui";
import { Screen } from "@/components/portal/Screen";
import { useGuard } from "@/components/portal/useGuard";
import { preloadPdfjs } from "@/components/review/pdfjs";
import { usePortal } from "@/lib/portal-state";
import styles from "./Documents.module.css";

const sizeText = (bytes: number) =>
  bytes < 1_000_000 ? `${Math.max(1, Math.round(bytes / 1000))} KB` : `${(bytes / 1_000_000).toFixed(1)} MB`;

export default function DocumentsPage() {
  const { state, actions } = usePortal();
  const router = useRouter();
  useGuard("documents", "none");
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState<"upload" | "sample" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    preloadPdfjs();
    router.prefetch("/reading");
    router.prefetch("/review");
  }, [router]);

  const send = async (run: () => Promise<unknown>, kind: "upload" | "sample") => {
    setBusy(kind);
    setError(null);
    try {
      await run();
      router.push("/reading");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setBusy(null);
    }
  };

  const take = (files: FileList | File[] | null | undefined) => {
    const file = files?.[0];
    if (!file) return;
    if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") {
      setError("Please choose a PDF.");
      return;
    }
    void send(() => actions.upload(file), "upload");
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setOver(false);
    take(event.dataTransfer.files);
  };

  const docs = state.docs;

  return (
    <Screen
      title="Documents"
      next={
        docs
          ? { onClick: () => router.push(state.readDone ? "/review" : "/reading"), disabled: busy !== null }
          : undefined
      }
    >
      <div
        className={styles.drop}
        data-over={over}
        data-busy={busy !== null}
        data-testid="drop-area"
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        <span className={styles.dropIcon} aria-hidden="true">
          <Icon name="upload" size={30} />
        </span>
        <p className={styles.dropTitle}>Drop your PDFs here</p>
        <button
          type="button"
          className={styles.choose}
          onClick={() => inputRef.current?.click()}
          disabled={busy !== null}
        >
          or click to choose files
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          aria-label="Choose a PDF"
          tabIndex={-1}
          data-testid="file-input"
          onChange={(e) => {
            take(e.target.files);
            e.target.value = "";
          }}
        />
        {busy === "upload" && (
          <p className={styles.status} role="status">
            Uploading…
          </p>
        )}
      </div>

      <p className={styles.sampleRow}>
        <Btn
          variant="link"
          onClick={() => void send(actions.useSample, "sample")}
          busy={busy === "sample"}
          disabled={busy !== null}
        >
          Use sample documents
        </Btn>
      </p>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {docs && (
        <section className={styles.loaded} aria-label="Your document" data-testid="loaded-file">
          <Icon name="file" size={22} />
          <span className={styles.fileName}>{docs.name}</span>
          <span className={`${styles.fileMeta} num`}>
            {docs.pages} {docs.pages === 1 ? "page" : "pages"}, {sizeText(docs.size_bytes)}
          </span>
        </section>
      )}
    </Screen>
  );
}
