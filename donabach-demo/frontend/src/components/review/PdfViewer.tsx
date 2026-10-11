"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { Icon, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { ParsedField } from "@/lib/types";
import { scrollBehavior } from "./motion";
import { loadPdfjs } from "./pdfjs";
import styles from "./PdfViewer.module.css";

type Box = NonNullable<ParsedField["bbox"]>;

export interface ViewerDoc {
  id: string;
  /** Short name for the tab. */
  label: string;
  /** [width, height] of each page in PDF points, from the parser. */
  pageSizes: [number, number][];
  /** Something in this document still needs the user's look. */
  needsLook: boolean;
}

export interface ViewerHighlight {
  /** 1-based. */
  page: number;
  /** PDF points, origin at the top-left of the page (the parser's convention). */
  bbox: Box;
}

export interface ViewerFocus {
  docId: string;
  highlights: ViewerHighlight[];
  /** Changes on every selection, so choosing the same number again replays the pulse and the scroll. */
  nonce: number;
}

interface Props {
  docs: ViewerDoc[];
  activeId: string;
  onActiveChange: (id: string) => void;
  focus: ViewerFocus | null;
  /** The line under the pages: what is being shown, or how to show something. */
  caption: ReactNode;
}

const NO_HIGHLIGHTS: ViewerHighlight[] = [];
const BOX_PADDING = 3; // px of air around a number, so the outline does not touch its digits

/** A tab strip over the documents, and their pages drawn to canvases, with boxes on the numbers. */
export function PdfViewer({ docs, activeId, onActiveChange, focus, caption }: Props) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const handledNonce = useRef(-1);
  const [width, setWidth] = useState(0);
  // A document is fetched and drawn the first time its tab is shown, then kept.
  const [visited, setVisited] = useState<string[]>([activeId]);
  if (!visited.includes(activeId)) setVisited([...visited, activeId]);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.observe(scroller);
    return () => observer.disconnect();
  }, []);

  // A document opens at its top (the scroller is shared by all of them).
  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: 0 });
  }, [activeId]);

  // Bring the highlighted numbers into view, once per selection, and only if they are not already.
  useEffect(() => {
    if (!focus || focus.highlights.length === 0 || handledNonce.current === focus.nonce) return;
    handledNonce.current = focus.nonce;
    const scroller = scrollerRef.current;
    if (!scroller) return;
    // Where each box sits in the scroller, in px from the top of its content.
    const spans = focus.highlights.flatMap((h) => {
      const page = scroller.querySelector<HTMLElement>(
        `[data-doc="${CSS.escape(focus.docId)}"] [data-page="${h.page}"]`,
      );
      if (!page) return [];
      const scale = page.clientWidth / Number(page.dataset.points);
      return [{ top: page.offsetTop + h.bbox.top * scale, bottom: page.offsetTop + h.bbox.bottom * scale }];
    });
    if (spans.length === 0) return;
    const top = Math.min(...spans.map((s) => s.top));
    const bottom = Math.max(...spans.map((s) => s.bottom));
    const margin = 48;
    const seen = top - margin >= scroller.scrollTop && bottom + margin <= scroller.scrollTop + scroller.clientHeight;
    if (seen) return;
    // A group that fits is centred; a taller one starts near the top of the view.
    const fits = bottom - top < scroller.clientHeight * 0.7;
    const target = fits ? (top + bottom) / 2 - scroller.clientHeight / 2 : top - scroller.clientHeight * 0.2;
    scroller.scrollTo({ top: Math.max(0, target), behavior: scrollBehavior() });
  }, [focus]);

  const onTabKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = docs.findIndex((d) => d.id === activeId);
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % docs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + docs.length) % docs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = docs.length - 1;
    else return;
    event.preventDefault();
    onActiveChange(docs[next].id);
    document.getElementById(`tab-${docs[next].id}`)?.focus();
  };

  return (
    <section className={styles.viewer} aria-label="Document viewer">
      <div className={styles.tabs} role="tablist" aria-label="Documents" onKeyDown={onTabKeyDown}>
        {docs.map((doc) => (
          <button
            key={doc.id}
            type="button"
            role="tab"
            id={`tab-${doc.id}`}
            aria-selected={doc.id === activeId}
            aria-controls={`panel-${doc.id}`}
            tabIndex={doc.id === activeId ? 0 : -1}
            className={styles.tab}
            onClick={() => onActiveChange(doc.id)}
          >
            {doc.label}
            {doc.needsLook && (
              <>
                <Icon name="alert" size={16} className={styles.alert} />
                <span className="sr-only">(needs a look)</span>
              </>
            )}
          </button>
        ))}
      </div>

      <div className={styles.scroller} ref={scrollerRef} tabIndex={0} role="region" aria-label="Document pages">
        {docs.map(
          (doc) =>
            visited.includes(doc.id) && (
              <div
                key={doc.id}
                className={styles.pages}
                role="tabpanel"
                id={`panel-${doc.id}`}
                aria-labelledby={`tab-${doc.id}`}
                hidden={doc.id !== activeId}
                data-doc={doc.id}
              >
                <DocPages
                  doc={doc}
                  pageWidth={width}
                  highlights={focus?.docId === doc.id ? focus.highlights : NO_HIGHLIGHTS}
                  nonce={focus?.nonce ?? 0}
                />
              </div>
            ),
        )}
      </div>

      <p className={styles.caption} role="status">
        {caption}
      </p>
    </section>
  );
}

function DocPages({
  doc,
  pageWidth,
  highlights,
  nonce,
}: {
  doc: ViewerDoc;
  pageWidth: number;
  highlights: ViewerHighlight[];
  nonce: number;
}) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let task: PDFDocumentLoadingTask | undefined;
    (async () => {
      const pdfjs = await loadPdfjs();
      if (cancelled) return;
      task = pdfjs.getDocument({ url: api.documentUrl(doc.id), verbosity: pdfjs.VerbosityLevel.ERRORS });
      const loaded = await task.promise;
      if (!cancelled) setPdf(loaded); // a cancelled load is torn down by the cleanup below
    })().catch((e: unknown) => {
      if (!cancelled) setError(e instanceof Error ? e.message : "The file could not be opened.");
    });
    return () => {
      cancelled = true;
      void task?.destroy();
    };
  }, [doc.id]);

  if (error || doc.pageSizes.length === 0) {
    return (
      <div className={styles.error} role="alert">
        <Icon name="alert" size={20} />
        <p>We could not show this document. {error}</p>
      </div>
    );
  }
  if (pageWidth <= 0) return null;

  return (
    <>
      {doc.pageSizes.map((size, i) => (
        <div key={i} className={styles.sheet}>
          {doc.pageSizes.length > 1 && (
            <span className={styles.pageNumber}>
              Page {i + 1} of {doc.pageSizes.length}
            </span>
          )}
          <PdfPage
            pdf={pdf}
            label={`${doc.label}, page ${i + 1}`}
            pageNumber={i + 1}
            size={size}
            cssWidth={pageWidth}
            highlights={highlights.filter((h) => h.page === i + 1)}
            nonce={nonce}
          />
        </div>
      ))}
    </>
  );
}

function PdfPage({
  pdf,
  label,
  pageNumber,
  size,
  cssWidth,
  highlights,
  nonce,
}: {
  pdf: PDFDocumentProxy | null;
  /** Names the page for screen readers: "Brokerage statement, page 1". */
  label: string;
  pageNumber: number;
  size: [number, number];
  cssWidth: number;
  highlights: ViewerHighlight[];
  nonce: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [drawn, setDrawn] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [widthPoints, heightPoints] = size;
  const cssHeight = (cssWidth * heightPoints) / widthPoints;
  // PDF points to screen pixels: how a parser box becomes a box on the page.
  const scale = cssWidth / widthPoints;

  useEffect(() => {
    if (!pdf || cssWidth <= 0) return;
    let cancelled = false;
    let task: RenderTask | undefined;
    (async () => {
      const page = await pdf.getPage(pageNumber);
      if (cancelled) return;
      // Draw at the screen's pixel density so the digits stay sharp.
      const density = Math.min(window.devicePixelRatio || 1, 3);
      const viewport = page.getViewport({ scale: (cssWidth / page.getViewport({ scale: 1 }).width) * density });
      // Draw off screen and copy over, so a resize never shows a blank page in between.
      const buffer = document.createElement("canvas");
      buffer.width = Math.ceil(viewport.width);
      buffer.height = Math.ceil(viewport.height);
      task = page.render({ canvas: buffer, viewport });
      await task.promise;
      const canvas = canvasRef.current;
      if (cancelled || !canvas) return;
      canvas.width = buffer.width;
      canvas.height = buffer.height;
      canvas.getContext("2d")?.drawImage(buffer, 0, 0);
      setDrawn(true);
    })().catch((e: unknown) => {
      if (cancelled || (e as { name?: string })?.name === "RenderingCancelledException") return;
      setFailure(e instanceof Error ? e.message : "Unknown error");
    });
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [pdf, pageNumber, cssWidth]);

  return (
    <div
      className={styles.page}
      style={{ width: cssWidth, height: cssHeight }}
      data-page={pageNumber}
      data-points={widthPoints}
    >
      <canvas ref={canvasRef} className={styles.canvas} data-drawn={drawn} aria-label={label} role="img" />
      {!drawn && (
        <div className={styles.loading}>
          {failure ? <p>This page could not be drawn: {failure}</p> : <Spinner size={22} label="Loading document" />}
        </div>
      )}
      {highlights.map((h, i) => (
        <div
          key={`${nonce}-${i}`}
          className={styles.highlight}
          aria-hidden="true"
          style={{
            left: h.bbox.x0 * scale - BOX_PADDING,
            top: h.bbox.top * scale - BOX_PADDING,
            width: (h.bbox.x1 - h.bbox.x0) * scale + BOX_PADDING * 2,
            height: (h.bbox.bottom - h.bbox.top) * scale + BOX_PADDING * 2,
          }}
        />
      ))}
    </div>
  );
}
