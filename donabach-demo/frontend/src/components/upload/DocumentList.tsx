"use client";

import { Icon } from "@/components/ui";
import type { DocState } from "@/lib/state";
import { KIND_LABEL, UNRECOGNISED_NOTE, formatBytes, pageCount } from "./docKinds";
import styles from "./DocumentList.module.css";

type Tone = "busy" | "good" | "warn" | "bad";

/** What to show for one document: its stage, in words and an icon, plus the line under its name. */
function describe(doc: DocState): { label: string; tone: Tone; bar: string; meta: string; metaTone?: "warn" | "bad" } {
  const { info } = doc;
  const size = `${formatBytes(info.size_bytes)}${info.pages > 0 ? ` · ${pageCount(info.pages)}` : ""}`;
  switch (doc.status) {
    case "uploading":
      return { label: "Uploading", tone: "busy", bar: "uploading", meta: size };
    case "reading":
      return { label: "Reading", tone: "busy", bar: "reading", meta: size };
    case "error":
      return {
        label: "Could not read",
        tone: "bad",
        bar: "error",
        meta: doc.error ?? "Something went wrong.",
        metaTone: "bad",
      };
    case "ready":
      if (info.kind === "unknown") {
        return {
          label: "Not recognised",
          tone: "warn",
          bar: "warn",
          meta: `${UNRECOGNISED_NOTE} · ${size}`,
          metaTone: "warn",
        };
      }
      return {
        label: "Ready",
        tone: "good",
        bar: "ready",
        meta: `${info.kind ? KIND_LABEL[info.kind] : "Document"} · ${size}`,
      };
  }
}

export function DocumentList({ docs, onRemove }: { docs: DocState[]; onRemove: (id: string) => void }) {
  if (docs.length === 0) {
    return (
      <div className={styles.empty}>
        <p>Documents you add appear here, with each step of reading them.</p>
      </div>
    );
  }
  return (
    <ul className={styles.list} aria-label="Your documents">
      {docs.map((doc) => {
        const d = describe(doc);
        return (
          <li key={doc.info.id} className={styles.row}>
            <span className={styles.fileIcon} aria-hidden="true">
              <Icon name="file" size={24} />
            </span>
            <div className={styles.text}>
              <div className={styles.name} title={doc.info.name}>
                {doc.info.name}
              </div>
              <div className={styles.meta} data-tone={d.metaTone}>
                {d.metaTone && <Icon name="alert" size={16} />}
                <span>{d.meta}</span>
              </div>
            </div>
            <span className={styles.state} data-tone={d.tone} role="status">
              {d.tone === "busy" && <span className={styles.spinner} aria-hidden="true" />}
              {d.tone === "good" && <Icon name="check" size={18} strokeWidth={2.6} />}
              {d.tone === "warn" && <Icon name="alert" size={18} />}
              {d.tone === "bad" && <Icon name="cross" size={18} strokeWidth={2.6} />}
              {d.label}
              {d.tone === "busy" && "…"}
            </span>
            <button
              type="button"
              className={styles.remove}
              aria-label={`Remove ${doc.info.name}`}
              onClick={() => onRemove(doc.info.id)}
            >
              <Icon name="close" size={18} />
            </button>
            <span className={styles.bar} data-status={d.bar} aria-hidden="true" />
          </li>
        );
      })}
    </ul>
  );
}
