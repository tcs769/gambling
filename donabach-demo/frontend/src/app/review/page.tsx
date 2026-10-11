"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Icon, PageHeader, Panel } from "@/components/ui";
import { DocSection } from "@/components/review/DocSection";
import { MissingValues, type MissingItem } from "@/components/review/MissingValues";
import { PdfViewer, type ViewerDoc, type ViewerFocus } from "@/components/review/PdfViewer";
import { ReviewSkeleton } from "@/components/review/ReviewSkeleton";
import { ReviewSummary } from "@/components/review/ReviewSummary";
import { describeMissing, fieldStatus, sameValue } from "@/components/review/fields";
import { scrollBehavior } from "@/components/review/motion";
import { useReadyDocuments, type ReadyDoc } from "@/components/review/useDocuments";
import styles from "@/components/review/Review.module.css";
import { SHORT_KIND_LABEL } from "@/components/upload/docKinds";
import { useApp } from "@/lib/state";
import type { CrossCheck, ParsedField } from "@/lib/types";

interface Selection {
  docId: string;
  keys: string[];
  /** Counts up with every selection, so choosing the same number again replays the highlight. */
  nonce: number;
  /** What is being shown: a number's label, or the name of a check. */
  title: string;
  isCheck: boolean;
}

export default function ReviewPage() {
  const { phase, docs, retry } = useReadyDocuments();
  const { state } = useApp();
  if (phase === "loading") return <ReviewSkeleton />;
  if (phase === "failed") {
    return (
      <>
        <PageHeader title="Review extracted numbers" />
        <Panel className={styles.failed} role="alert">
          <h2>We could not load the documents</h2>
          <p>
            {state.error ?? "Something went wrong while reading them."} Check that the API is running, then try again.
          </p>
          <Button onClick={retry}>Try again</Button>
        </Panel>
      </>
    );
  }
  return <ReviewContent docs={docs} />;
}

function ReviewContent({ docs }: { docs: ReadyDoc[] }) {
  const { state, actions } = useApp();
  const router = useRouter();
  const listRef = useRef<HTMLDivElement>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [editing, setEditing] = useState<string[]>([]);
  const { overrides, acknowledged } = state;

  useEffect(() => {
    router.prefetch("/questions");
  }, [router]);

  // --- what still needs a look
  const waiting: { doc: ReadyDoc; field: ParsedField }[] = [];
  let total = 0;
  let flagged = 0;
  for (const doc of docs) {
    for (const field of doc.parsed.fields) {
      if (field.value !== null) total += 1;
      const status = fieldStatus(field, overrides, acknowledged);
      if (!status.needsLook) continue;
      flagged += 1;
      if (!status.resolved) waiting.push({ doc, field });
    }
  }
  const fieldByKey = new Map(docs.flatMap((d) => d.parsed.fields.map((f) => [f.key, f] as const)));
  // Numbers the household could not be built without, still unfilled. One that has since been
  // read from a document that was added, or typed in, no longer counts.
  const missingItems: MissingItem[] = state.missing
    .filter((m) => !(m.key in overrides) && (fieldByKey.get(m.key)?.value ?? null) === null)
    .map((m) => ({ key: m.key, ...describeMissing(m.key, m.label), inList: fieldByKey.has(m.key) }));
  const typedMissing = missingItems.filter((m) => !m.inList).length;
  const remaining = waiting.length + typedMissing;
  // Documents that gave nothing, and nothing typed in their place: there is nothing to confirm.
  const nothingRead = total === 0 && Object.keys(overrides).length === 0;

  // --- selection and the viewer
  const select = (doc: ReadyDoc, keys: string[], title: string, isCheck: boolean) => {
    setActiveId(doc.info.id);
    setSelection((prev) => ({ docId: doc.info.id, keys, nonce: (prev?.nonce ?? 0) + 1, title, isCheck }));
  };
  const selectedDoc = selection ? docs.find((d) => d.info.id === selection.docId) : undefined;
  const highlights =
    selection && selectedDoc
      ? selection.keys.flatMap((key) => {
          const field = selectedDoc.parsed.fields.find((f) => f.key === key);
          return field?.bbox && field.page ? [{ page: field.page, bbox: field.bbox }] : [];
        })
      : [];
  const focus: ViewerFocus | null = selection ? { docId: selection.docId, highlights, nonce: selection.nonce } : null;

  const viewerDocs: ViewerDoc[] = docs.map((doc) => ({
    id: doc.info.id,
    label: doc.parsed.doc_kind === "unknown" ? doc.info.name : SHORT_KIND_LABEL[doc.parsed.doc_kind],
    pageSizes: doc.parsed.page_sizes,
    needsLook: waiting.some((w) => w.doc.info.id === doc.info.id),
  }));
  const activeDoc = docs.find((d) => d.info.id === activeId) ?? docs[0];

  let caption = <>Choose a number on the left to see where it came from.</>;
  if (selection && selectedDoc) {
    if (selection.isCheck) {
      caption = (
        <>
          <strong>{selection.title}:</strong> {highlights.length} {highlights.length === 1 ? "number" : "numbers"} used
        </>
      );
    } else if (highlights.length > 0) {
      caption = (
        <>
          <strong>{selection.title}</strong> on page {highlights[0].page}
        </>
      );
    } else {
      caption = (
        <>
          <strong>{selection.title}</strong> was not found on this document
        </>
      );
    }
  }

  // --- changes
  const stopEditing = (key: string) => setEditing((keys) => keys.filter((k) => k !== key));
  // When that was the last number to deal with, go back up to the button that moves on.
  const afterChange = (key: string) => {
    stopEditing(key);
    if (remaining === 1 && waiting.some((w) => w.field.key === key))
      window.scrollTo({ top: 0, behavior: scrollBehavior() });
  };
  const keepAsRead = (field: ParsedField) => {
    if (field.key in overrides) actions.clearOverride(field.key);
    actions.acknowledge(field.key);
    afterChange(field.key);
  };
  const saveValue = (field: ParsedField, value: number | string) => {
    // Typing back what was read is the same as keeping it.
    if (sameValue(value, field.value)) keepAsRead(field);
    else {
      actions.setOverride(field.key, value);
      afterChange(field.key);
    }
  };
  const editField = (key: string) => setEditing((keys) => (keys.includes(key) ? keys : [...keys, key]));

  // Scroll the list to a row, and (for the flagged one) put the cursor in its box.
  const reveal = (doc: ReadyDoc, field: ParsedField) => {
    select(doc, [field.key], field.label, false);
    const row = listRef.current?.querySelector<HTMLElement>(`[data-field-key="${CSS.escape(field.key)}"]`);
    row?.scrollIntoView({ behavior: scrollBehavior(), block: "center" });
    const box = row?.querySelector<HTMLInputElement>("input");
    box?.focus({ preventScroll: true });
    box?.select(); // so typing replaces the number rather than adding to it
  };
  const showFirstWaiting = () => {
    const first = waiting[0];
    if (first) reveal(first.doc, first.field);
    else document.querySelector<HTMLElement>("[data-missing-values] input")?.focus();
  };

  // A single number on show can be corrected from the line under the document, unless its editor is open.
  const selectedField =
    selection && !selection.isCheck && selectedDoc
      ? selectedDoc.parsed.fields.find((f) => f.key === selection.keys[0])
      : undefined;
  const selectedStatus = selectedField && fieldStatus(selectedField, overrides, acknowledged);
  const editable =
    selectedField &&
    selectedStatus &&
    selectedField.value !== null &&
    !editing.includes(selectedField.key) &&
    !(selectedStatus.needsLook && !selectedStatus.resolved)
      ? selectedField
      : undefined;
  const startEditing = (field: ParsedField) => {
    editField(field.key);
    const row = listRef.current?.querySelector<HTMLElement>(`[data-field-key="${CSS.escape(field.key)}"]`);
    row?.scrollIntoView({ behavior: scrollBehavior(), block: "center" });
  };

  const hint =
    remaining > 0 ? (
      <button type="button" className={styles.hint} onClick={showFirstWaiting}>
        <Icon name="alert" size={18} />
        {remaining} {remaining === 1 ? "field needs" : "fields need"} a look
      </button>
    ) : nothingRead ? (
      <span className={styles.hint}>
        <Icon name="alert" size={18} />
        No numbers were read
      </span>
    ) : (
      <span className={styles.hint} data-done="true">
        <Icon name="check" size={18} strokeWidth={2.6} />
        All numbers confirmed
      </span>
    );

  return (
    <>
      <PageHeader
        title="Review extracted numbers"
        subtitle="Check what we read from your documents. Choose any number to see where it came from."
        actions={
          <div className={styles.actions}>
            <span role="status">{hint}</span>
            <Button arrow disabled={remaining > 0 || nothingRead} onClick={() => router.push("/questions")}>
              Confirm and continue
            </Button>
          </div>
        }
      />

      {missingItems.length > 0 && (
        <div data-missing-values>
          <MissingValues items={missingItems} onSet={(key, value) => actions.setOverride(key, value)} />
        </div>
      )}

      <div className={styles.split}>
        <div className={styles.fields} ref={listRef}>
          <ReviewSummary
            total={total}
            documents={docs.length}
            flagged={flagged}
            unresolved={remaining}
            onShow={showFirstWaiting}
          />
          {docs.map((doc) => (
            <DocSection
              key={doc.info.id}
              doc={doc}
              overrides={overrides}
              acknowledged={acknowledged}
              selectedKeys={selection?.docId === doc.info.id ? selection.keys : []}
              editing={editing}
              onSelect={(d, field) => select(d, [field.key], field.label, false)}
              onShowCheck={(d: ReadyDoc, check: CrossCheck) => select(d, check.keys, check.name, true)}
              onEdit={editField}
              onCancelEdit={stopEditing}
              onSave={saveValue}
              onKeep={keepAsRead}
            />
          ))}
        </div>

        <div className={styles.viewerColumn}>
          <PdfViewer
            docs={viewerDocs}
            activeId={activeDoc.info.id}
            onActiveChange={setActiveId}
            focus={focus}
            caption={
              <>
                <Icon name="info" size={18} />
                <span className={styles.captionText}>{caption}</span>
                {editable && (
                  <button type="button" className={styles.captionAction} onClick={() => startEditing(editable)}>
                    Edit this number
                  </button>
                )}
              </>
            }
          />
        </div>
      </div>
    </>
  );
}
