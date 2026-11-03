"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { BundleViewer, type BundleDoc, type ViewerHighlight } from "@/components/portal/BundleViewer";
import { ReviewRow } from "@/components/portal/ReviewRow";
import { Screen } from "@/components/portal/Screen";
import { useGuard } from "@/components/portal/useGuard";
import { groupFields } from "@/components/review/fieldLogic";
import { customerLabel, documentLabel, sameValue } from "@/lib/portal-format";
import { usePortal } from "@/lib/portal-state";
import type { ParsedField } from "@/lib/portal-types";
import styles from "./Review.module.css";

/** The rows the customer is shown first, in this order, with the names the mockup uses. */
const CURATED: { title: string; rows: [key: string, label: string][] }[] = [
  {
    title: "Tax return",
    rows: [
      ["w2_wages_taxpayer", "Wages, after 401(k)"],
      ["filing_status", "Filing status"],
      ["qualified_dividends_3a", "Qualified dividends"],
    ],
  },
  {
    title: "Accounts",
    rows: [
      ["brokerage_total_value", "Brokerage"],
      ["brokerage_cost_basis", "Brokerage cost basis"],
      ["k401_total_balance", "401(k) and IRA"],
      ["k401_contrib_taxpayer", "401(k) contributions this year"],
      ["roth_total_balance", "Roth IRA"],
      ["brokerage_cash", "Cash"],
    ],
  },
];

export default function ReviewPage() {
  const { state, actions } = usePortal();
  const router = useRouter();
  const ready = useGuard("review");
  const [picked, setPicked] = useState<{ key: string; nonce: number } | null>(null);

  const documents = state.docs?.documents;
  const { overrides, confirmed } = state;

  const fields = useMemo(() => (documents ?? []).flatMap((d) => d.fields), [documents]);
  const fieldByKey = useMemo(() => new Map(fields.map((f) => [f.key, f])), [fields]);
  const docKindOf = useMemo(
    () => new Map((documents ?? []).flatMap((d) => d.fields.map((f) => [f.key, d.doc_kind] as const))),
    [documents],
  );
  const docOfField = useMemo(() => {
    const map = new Map<string, string>();
    (documents ?? []).forEach((d) => d.fields.forEach((f) => map.set(f.key, `${d.doc_kind}-${d.first_page}`)));
    return map;
  }, [documents]);

  // A field that needs a look is always in the first list, even when it is not one of the friendly rows.
  const shownFirst = useMemo(() => {
    const curatedKeys = new Set(CURATED.flatMap((g) => g.rows.map(([key]) => key)));
    const extra = fields.filter((f) => f.confidence !== "high" && !curatedKeys.has(f.key));
    return CURATED.map((group, i) => ({
      title: group.title,
      rows: [
        ...group.rows.flatMap(([key, label]) => {
          const field = fieldByKey.get(key);
          return field ? [{ field, label }] : [];
        }),
        ...extra
          .filter((f) => (i === 0) === (docKindOf.get(f.key) === "form_1040"))
          .map((field) => ({ field, label: customerLabel(field.label) })),
      ],
    })).filter((g) => g.rows.length > 0);
  }, [fields, fieldByKey, docKindOf]);
  const shownKeys = useMemo(() => new Set(shownFirst.flatMap((g) => g.rows.map((r) => r.field.key))), [shownFirst]);

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

  const renderRow = (field: ParsedField, label?: string) => {
    const override = overrides[field.key];
    const edited = field.key in overrides && !sameValue(override, field.value);
    const flagged = field.confidence !== "high";
    return (
      <ReviewRow
        key={field.key}
        field={field}
        label={label}
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
  };

  return (
    <Screen
      title="Check what we found"
      lede="Select any number to see where it came from."
      back={{ onClick: () => router.push("/") }}
      next={{ label: "Confirm and continue", onClick: () => router.push("/goals"), disabled: waiting.length > 0 }}
    >
      <div className={styles.review}>
        <div className={styles.fields}>
          {shownFirst.map((group) => (
            <section key={group.title} className={styles.group} aria-labelledby={`group-${group.title}`}>
              <h2 id={`group-${group.title}`}>{group.title}</h2>
              <ul className={styles.list}>{group.rows.map((r) => renderRow(r.field, r.label))}</ul>
            </section>
          ))}

          <details className={styles.all}>
            <summary>Show all fields</summary>
            {documents.map((doc) => {
              const rest = doc.fields.filter((f) => !shownKeys.has(f.key));
              if (rest.length === 0) return null;
              return (
                <section key={`${doc.doc_kind}-${doc.first_page}`} className={styles.group}>
                  <h3 className={styles.docTitle}>{documentLabel(doc)}</h3>
                  {groupFields(rest).map((group) => (
                    <div key={group.name}>
                      <h4 className={styles.groupTitle}>{group.name}</h4>
                      <ul className={styles.list}>{group.fields.map((field) => renderRow(field))}</ul>
                    </div>
                  ))}
                </section>
              );
            })}
          </details>
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
