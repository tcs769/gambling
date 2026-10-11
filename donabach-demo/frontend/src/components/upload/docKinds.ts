import type { DocumentInfo } from "@/lib/types";

export type DocKind = NonNullable<DocumentInfo["kind"]>;

/** What a recognised document is called on screen. */
export const KIND_LABEL: Record<DocKind, string> = {
  form_1040: "Form 1040 (2026 projection)",
  brokerage_statement: "Brokerage statement",
  retirement_401k: "401(k) statement",
  unknown: "Not recognised",
};

/** The same, short enough for a tab. */
export const SHORT_KIND_LABEL: Record<DocKind, string> = {
  form_1040: "Form 1040",
  brokerage_statement: "Brokerage statement",
  retirement_401k: "401(k) statement",
  unknown: "Other document",
};

export const UNRECOGNISED_NOTE = "Not recognised: the demo reads its three sample templates";

/** 7445 -> "7.3 KB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const pageCount = (pages: number): string => (pages === 1 ? "1 page" : `${pages} pages`);

export const isPdf = (file: File): boolean => file.type === "application/pdf" || /\.pdf$/i.test(file.name);
