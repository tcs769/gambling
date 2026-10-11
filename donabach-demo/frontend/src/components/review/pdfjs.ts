// pdf.js is large and only works in the browser, so it is imported on demand, once, and its worker
// is served from /pdf.worker.min.mjs (copied into public/ by `npm install`).

type PdfjsModule = typeof import("pdfjs-dist");

type Upsert = { getOrInsertComputed?: (key: unknown, compute: (key: unknown) => unknown) => unknown };

/**
 * pdf.js 6 calls Map/WeakMap.prototype.getOrInsertComputed, which browsers only gained in 2026
 * (Chrome 145). Older ones, including the Chromium used to check this app, would fail to draw a
 * page, so add the method when it is missing. (The worker does not need it for these documents.)
 */
function addUpsertMethods(): void {
  for (const proto of [Map.prototype, WeakMap.prototype] as unknown as (Upsert & Map<unknown, unknown>)[]) {
    if (typeof proto.getOrInsertComputed === "function") continue;
    Object.defineProperty(proto, "getOrInsertComputed", {
      configurable: true,
      writable: true,
      value(this: Map<unknown, unknown>, key: unknown, compute: (key: unknown) => unknown) {
        if (this.has(key)) return this.get(key);
        const value = compute(key);
        this.set(key, value);
        return value;
      },
    });
  }
}

let loading: Promise<PdfjsModule> | null = null;

export function loadPdfjs(): Promise<PdfjsModule> {
  loading ??= (async () => {
    addUpsertMethods();
    const pdfjs = await import("pdfjs-dist");
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
