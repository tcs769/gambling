"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { BundleViewer, type BundleDoc, type ViewerHighlight } from "@/components/portal/BundleViewer";
import { ReviewRow } from "@/components/portal/ReviewRow";
import { Screen } from "@/components/portal/Screen";
import { useGuard } from "@/components/portal/useGuard";
import { groupFields } from "@/components/review/fieldLogic";
import { documentLabel, sameValue } from "@/lib/portal-format";
import { usePortal } from "@/lib/portal-state";
import type { ParsedField } from "@/lib/portal-types";
import styles from "./Review.module.css";

export default function ReviewPage() {
  const { state, actions } = usePortal();
  const router = useRouter();
  const ready = useGuard("review");
  const [picked, setPicked] = useState<{ key: string; nonce: number } | null>(null);

  const documents = state.docs?.documents;
  const { overrides, confirmed } = state;

  const fields = useMemo(() => (documents ?? []).flatMap((d) => d.fields), [documents]);
  const fieldByKey = useMemo(() => new Map(fields.map((f) => [f.key, f])), [fields]);
  const docOfField = useMemo(() => {
    const map = new Map<string, string>();
    (documents ?? []).forEach((d) => d.fields.forEach((f) => map.set(f.key, `${d.doc_kind}-${d.first_page}`)));
    return map;
  }, [documents]);

  const isResolved = (f: ParsedField) =>
    f.key in overrides && !sameValue(overrides[f.key], f.value) ? true : f.value !== null && confirmed.includes(f.key);
  const waiting = fields.filter((f) => f.confidence !== "high" && !isResolved(f));

  // The viewer opens on the number that needs a look, so its source is already on the page.
  const firstFlagged = useMemo(() => fields.find((f) => f.confidence !== "high")?.key ?? null, [fields]);
  const selected = picked ?? (firstFlagged ? { key: firstFlagged, nonce: 1 } : null);

  useEffect(() => {
    router.prefetch("/goals");
  }, [router]);

  const select = (key: string) =>
    setPicked((prev) => (prev?.key === key ? prev : { key, nonce: (prev?.nonce ?? 0) + 1 }));

  const selectedField = selected ? fieldByKey.get(selected.key) : undefined;
  const highlights = useMemo<ViewerHighlight[]>(
    () => (selectedField?.bbox && selectedField.page ? [{ page: selectedField.page, bbox: selectedField.bbox }] : []),
    [selectedField],
  );

  const viewerDocs = useMemo<BundleDoc[]>(
    () =>
      (documents ?? []).map((d) => ({
        key: `${d.doc_kind}-${d.first_page}`,
        label: documentLabel(d),
        firstPage: d.first_page ?? 1,
      })),
    [documents],
  );
  const [tab, setTab] = useState<string | null>(null);
  const activeKey = (selected && docOfField.get(selected.key)) || tab || viewerDocs[0]?.key || "";

  if (!ready || !state.docs || !documents) return null;
  const pageSizes = documents.reduce<[number, number][]>(
    (best, d) => (d.page_sizes.length > best.length ? d.page_sizes : best),
    [],
  );

  return (
    <Screen
      title="Review"
      wide
      back={{ onClick: () => router.push("/") }}
      next={{ label: "Confirm and continue", onClick: () => router.push("/goals"), disabled: waiting.length > 0 }}
    >
      <div className={styles.split}>
        <div className={styles.fields}>
          {documents.map((doc) => (
            <section
              key={`${doc.doc_kind}-${doc.first_page}`}
              className={styles.doc}
              aria-labelledby={`doc-${doc.first_page}`}
            >
              <header className={styles.docHead}>
                <h2 id={`doc-${doc.first_page}`}>{documentLabel(doc)}</h2>
                <span className={`${styles.pageTag} num`}>
                  {doc.first_page === doc.last_page
                    ? `Page ${doc.first_page}`
                    : `Pages ${doc.first_page}–${doc.last_page}`}
                </span>
              </header>
              {groupFields(doc.fields).map((group) => (
                <div key={group.name} className={styles.group}>
                  <h3 className={styles.groupTitle}>{group.name}</h3>
                  <ul className={styles.list}>
                    {group.fields.map((field) => {
                      const override = overrides[field.key];
                      const edited = field.key in overrides && !sameValue(override, field.value);
                      const flagged = field.confidence !== "high";
                      return (
                        <ReviewRow
                          key={field.key}
                          field={field}
                          value={edited ? override : field.value}
                          edited={edited}
                          flagged={flagged}
                          resolved={isResolved(field)}
                          confirmed={confirmed.includes(field.key)}
                          selected={selected?.key === field.key}
                          onSelect={() => select(field.key)}
                          onEdit={(value) => {
                            if (sameValue(value, field.value)) {
                              actions.setOverride(field.key, null);
                              if (flagged) actions.confirm(field.key);
                            } else actions.setOverride(field.key, value);
                          }}
                          onReset={() => actions.setOverride(field.key, null)}
                          onConfirm={() => actions.confirm(field.key)}
                        />
                      );
                    })}
                  </ul>
                </div>
              ))}
            </section>
          ))}
        </div>

        <div className={styles.viewer}>
          <BundleViewer
            pdfId={state.docs.id}
            pageSizes={pageSizes}
            docs={viewerDocs}
            highlights={highlights}
            nonce={selected?.nonce ?? 0}
            activeKey={activeKey}
            onActiveChange={setTab}
          />
        </div>
      </div>
    </Screen>
  );
}
