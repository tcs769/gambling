// pdf.js is large and only works in the browser, so it is imported on demand, once, and its worker
// is served from /pdf.worker.min.mjs (the legacy worker, copied into public/ by `npm install`).
//
// The legacy build is used for both the library and the worker: pdf.js 6 calls newer JavaScript
// methods (for example Map.prototype.getOrInsertComputed, Chrome 145 and later) and the legacy build
// bundles the polyfills, so the viewer also works in browsers that are a little behind.

type PdfjsModule = typeof import("pdfjs-dist");

let loading: Promise<PdfjsModule> | null = null;

export function loadPdfjs(): Promise<PdfjsModule> {
  loading ??= (async () => {
    const pdfjs = (await import("pdfjs-dist/legacy/build/pdf.mjs")) as PdfjsModule;
    pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
    return pdfjs;
  })();
  return loading;
}

/** Start fetching pdf.js early (e.g. from the Upload screen) so Review opens with the PDF ready. */
export function preloadPdfjs(): void {
  loadPdfjs().catch(() => {
    loading = null; // try again when a viewer actually needs it
  });
}
