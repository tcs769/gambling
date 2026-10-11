"use client";

import { useEffect, useRef, useState, type DragEvent } from "react";
import { Button, Icon } from "@/components/ui";
import { isPdf } from "./docKinds";
import styles from "./DropZone.module.css";

interface Props {
  hasDocs: boolean;
  /** The sample documents are being added. */
  loadingSamples: boolean;
  /** Shown when something went wrong that is not about one file (e.g. the samples did not load). */
  error?: string | null;
  onFiles: (files: File[]) => void;
  onSamples: () => void;
}

const carriesFiles = (transfer: DataTransfer | null | undefined) => Array.from(transfer?.types ?? []).includes("Files");
const hasFiles = (event: DragEvent) => carriesFiles(event.dataTransfer);

/** The big drop target: drag PDFs in, or choose them, or use the sample documents. */
export function DropZone({ hasDocs, loadingSamples, error, onFiles, onSamples }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const depth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // A PDF dropped outside the zone would make the browser open it and leave the app.
  useEffect(() => {
    const stop = (event: globalThis.DragEvent) => {
      if (carriesFiles(event.dataTransfer)) event.preventDefault();
    };
    window.addEventListener("dragover", stop);
    window.addEventListener("drop", stop);
    return () => {
      window.removeEventListener("dragover", stop);
      window.removeEventListener("drop", stop);
    };
  }, []);

  const take = (list: FileList | null) => {
    const files = Array.from(list ?? []);
    const pdfs = files.filter(isPdf);
    const skipped = files.filter((f) => !isPdf(f));
    setNotice(
      skipped.length > 0 ? `Only PDF files can be added. Skipped ${skipped.map((f) => f.name).join(", ")}.` : null,
    );
    if (pdfs.length > 0) onFiles(pdfs);
  };

  const onDragEnter = (event: DragEvent) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    depth.current += 1;
    setDragging(true);
  };
  const onDragOver = (event: DragEvent) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  };
  const onDragLeave = (event: DragEvent) => {
    if (!hasFiles(event)) return;
    depth.current = Math.max(0, depth.current - 1);
    if (depth.current === 0) setDragging(false);
  };
  const onDrop = (event: DragEvent) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    depth.current = 0;
    setDragging(false);
    take(event.dataTransfer.files);
  };

  const message = error ?? notice;

  return (
    <div
      className={styles.zone}
      data-dragging={dragging}
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      onClick={(event) => {
        // Anywhere in the zone opens the file picker, except on its own buttons.
        if ((event.target as HTMLElement).closest("button, a, input")) return;
        inputRef.current?.click();
      }}
    >
      <input
        ref={inputRef}
        className={styles.input}
        type="file"
        accept="application/pdf,.pdf"
        multiple
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          take(event.target.files);
          event.target.value = ""; // so choosing the same file again still counts
        }}
      />
      <span className={styles.icon} aria-hidden="true">
        <Icon name="upload" size={32} />
      </span>
      <h1 className={styles.title}>{"Add your household's documents."}</h1>
      <p className={styles.lede} data-tone={message ? "warn" : undefined} role="status">
        {message ??
          (dragging
            ? "Drop your PDFs to add them."
            : "Drag in PDFs of a tax return and account statements, or choose them from your computer.")}
      </p>
      <div className={styles.actions}>
        <Button variant="secondary" onClick={() => inputRef.current?.click()}>
          Choose files
        </Button>
        <Button
          className={styles.sample}
          variant={hasDocs ? "secondary" : "primary"}
          onClick={onSamples}
          busy={loadingSamples}
        >
          Use sample documents
        </Button>
      </div>
      <p className={styles.note}>
        <Icon name="info" size={18} />
        PDF only. This demo uses fictional data only.
      </p>
    </div>
  );
}
