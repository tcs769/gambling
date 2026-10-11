// The PDF viewer runs pdf.js in a web worker. Copy the (legacy, polyfilled) worker next to the app so it
// is served from /pdf.worker.min.mjs (same origin) regardless of how the bundler handles worker URLs.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(root, "node_modules/pdfjs-dist/legacy/build/pdf.worker.min.mjs");
if (existsSync(source)) {
  mkdirSync(resolve(root, "public"), { recursive: true });
  copyFileSync(source, resolve(root, "public/pdf.worker.min.mjs"));
  console.log("Copied pdf.worker.min.mjs to public/");
}
