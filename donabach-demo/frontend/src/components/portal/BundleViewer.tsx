"use client";

import { useEffect, useRef, useState } from "react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { Icon, Spinner } from "@/components/ui";
import { loadPdfjs } from "@/components/review/pdfjs";
import { scrollBehavior } from "@/components/review/motion";
import { portalApi } from "@/lib/portal-api";
import type { ParsedField } from "@/lib/portal-types";
import styles from "./BundleViewer.module.css";

type Box = NonNullable<ParsedField["bbox"]>;

export interface BundleDoc {
  key: string;
  label: string;
  /** The absolute page the document starts on (1-based). */
  firstPage: number;
}

export interface ViewerHighlight {
  /** Absolute page of the one PDF (1-based). */
  page: number;
  /** PDF points, origin at the top-left of the page. */
  bbox: Box;
}

interface Props {
  pdfId: string;
  /** [width, height] of every page of the PDF, in points. */
  pageSizes: [number, number][];
  docs: BundleDoc[];
  highlights: ViewerHighlight[];
  /** Changes with every selection, so choosing the same number again replays the pulse and the scroll. */
  nonce: number;
  /** The document (key) the tab strip shows as current. */
  activeKey: string;
  onActiveChange: (key: string) => void;
}

const BOX_PADDING = 3;

/** The whole PDF, its pages drawn to canvases one under another, with a box on the numbers being shown. */
export function BundleViewer({ pdfId, pageSizes, docs, highlights, nonce, activeKey, onActiveChange }: Props) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const handledNonce = useRef(-1);
  const [width, setWidth] = useState(0);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(0, Math.floor(entry.contentRect.width))));
    observer.observe(scroller);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    let task: PDFDocumentLoadingTask | undefined;
    (async () => {
      const pdfjs = await loadPdfjs();
      if (cancelled) return;
      task = pdfjs.getDocument({ url: portalApi.documentUrl(pdfId), verbosity: pdfjs.VerbosityLevel.ERRORS });
      const loaded = await task.promise;
      if (!cancelled) setPdf(loaded);
    })().catch((e: unknown) => {
      if (!cancelled) setError(e instanceof Error ? e.message : "The file could not be opened.");
    });
    return () => {
      cancelled = true;
      void task?.destroy();
    };
  }, [pdfId]);

  // Bring the highlighted numbers into view, once per selection, and only if they are not already.
  useEffect(() => {
    if (highlights.length === 0 || handledNonce.current === nonce) return;
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const spans = highlights.flatMap((h) => {
      const page = scroller.querySelector<HTMLElement>(`[data-page="${h.page}"]`);
      if (!page) return [];
      const scale = page.clientWidth / Number(page.dataset.points);
      return [{ top: page.offsetTop + h.bbox.top * scale, bottom: page.offsetTop + h.bbox.bottom * scale }];
    });
    if (spans.length === 0) return;
    handledNonce.current = nonce;
    const top = Math.min(...spans.map((s) => s.top));
    const bottom = Math.max(...spans.map((s) => s.bottom));
    const margin = 48;
    const seen = top - margin >= scroller.scrollTop && bottom + margin <= scroller.scrollTop + scroller.clientHeight;
    if (seen) return;
    const target = (top + bottom) / 2 - scroller.clientHeight / 2;
    scroller.scrollTo({ top: Math.max(0, target), behavior: scrollBehavior() });
  }, [highlights, nonce, width]);

  const goTo = (doc: BundleDoc) => {
    onActiveChange(doc.key);
    const scroller = scrollerRef.current;
    const page = scroller?.querySelector<HTMLElement>(`[data-page="${doc.firstPage}"]`);
    if (scroller && page) scroller.scrollTo({ top: Math.max(0, page.offsetTop - 14), behavior: scrollBehavior() });
  };

  return (
    <section className={styles.viewer} aria-label="Document pages">
      <div className={styles.tabs} role="group" aria-label="Documents">
        {docs.map((doc) => (
          <button
            key={doc.key}
            type="button"
            className={styles.tab}
            aria-current={doc.key === activeKey ? "true" : undefined}
            onClick={() => goTo(doc)}
          >
            {doc.label}
          </button>
        ))}
      </div>
      <div className={styles.scroller} ref={scrollerRef} tabIndex={0} role="region" aria-label="Pages">
        {error ? (
          <div className={styles.error} role="alert">
            <Icon name="alert" size={20} />
            <p>The document could not be shown. {error}</p>
          </div>
        ) : (
          width > 0 &&
          pageSizes.map((size, i) => (
            <PdfPage
              key={i}
              pdf={pdf}
              label={`Page ${i + 1}`}
              pageNumber={i + 1}
              size={size}
              cssWidth={width}
              highlights={highlights.filter((h) => h.page === i + 1)}
              nonce={nonce}
            />
          ))
        )}
      </div>
    </section>
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
  const scale = cssWidth / widthPoints;

  useEffect(() => {
    if (!pdf || cssWidth <= 0) return;
    let cancelled = false;
    let task: RenderTask | undefined;
    (async () => {
      const page = await pdf.getPage(pageNumber);
      if (cancelled) return;
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
          {failure ? <p>This page could not be drawn.</p> : <Spinner size={22} label="Loading" />}
        </div>
      )}
      {highlights.map((h, i) => (
        <div
          key={`${nonce}-${i}`}
          className={styles.highlight}
          data-testid="highlight"
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
