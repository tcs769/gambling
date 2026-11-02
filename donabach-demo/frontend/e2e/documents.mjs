// Documents (/): the drop area, the sample link, drag-and-drop and click-to-choose of fixtures/smith_documents.pdf, and that every way
// of loading the PDF gives the same documents and the same Review.
import { isMain, runAlone, newPage, apiPost, docLabel, PDF_BYTES, reviewRows } from "./portal.mjs";

/** Drop the PDF on the drop area the way a browser does (a DataTransfer carrying a File). */
async function dropPdf(page, name = "smith_documents.pdf", type = "application/pdf", bytes = PDF_BYTES) {
  const data = await page.evaluateHandle(
    ({ bytes, name, type }) => {
      const dt = new DataTransfer();
      dt.items.add(new File([new Uint8Array(bytes)], name, { type }));
      return dt;
    },
    { bytes: [...bytes], name, type },
  );
  await page.dispatchEvent('[data-testid="drop-area"]', "dragover", { dataTransfer: data });
  await page.dispatchEvent('[data-testid="drop-area"]', "drop", { dataTransfer: data });
}

async function readList(page) {
  await page.waitForURL("**/review", { timeout: 20_000 });
  await page.locator("[data-field-key]").first().waitFor();
  return reviewRows(page);
}

export async function runDocuments({ browser, base, check }) {
  const sample = await apiPost(base, "/portal/documents/sample", undefined).catch(() => null);

  // --- the screen
  {
    const { context, page, issues } = await newPage(browser);
    await page.goto(`${base}/`, { waitUntil: "networkidle" });
    check((await page.title()) === "Waramoug", "the tab title is Waramoug");
    check(
      await page.getByText("Drop your PDFs here", { exact: true }).isVisible(),
      "the drop area says 'Drop your PDFs here'",
    );
    check(
      await page.getByText("or click to choose files", { exact: true }).isVisible(),
      "'or click to choose files' sits under it",
    );
    const link = page.getByRole("button", { name: "Use sample documents" });
    check(await link.isVisible(), "a small 'Use sample documents' link is below the drop area");
    const dropBox = await page.locator('[data-testid="drop-area"]').boundingBox();
    const linkBox = await link.boundingBox();
    check(linkBox.y > dropBox.y + dropBox.height, "the sample link is below the drop area");
    check(
      dropBox.height >= 240 && dropBox.width >= 600,
      `the drop area is large (${Math.round(dropBox.width)}x${Math.round(dropBox.height)})`,
    );
    check(
      (await page.locator('input[type="file"]').getAttribute("accept"))?.includes("pdf"),
      "the file chooser accepts PDFs",
    );
    check(issues.length === 0, `no console errors on Documents (${issues.join(" | ")})`);

    // a file that is not a PDF is refused with a line of text, and nothing moves on
    await dropPdf(page, "notes.txt", "text/plain", Buffer.from("hello"));
    check(
      await page.getByRole("alert").getByText("Please choose a PDF.").isVisible(),
      "a dropped text file is refused",
    );
    check(new URL(page.url()).pathname === "/", "the screen stays on Documents after a refused file");
    await context.close();
  }

  // --- three ways in: sample link, drop, click to choose
  const runs = {};
  const uploads = {};
  for (const way of ["sample", "drop", "choose"]) {
    const { context, page } = await newPage(browser);
    const requests = [];
    page.on("request", (r) => r.method() === "POST" && r.url().includes("/api/portal/documents/") && requests.push(r));
    // Playwright cannot read a multipart body made of a file, so the page's own fetch is watched for the form's field names.
    await page.addInitScript(() => {
      const send = window.fetch;
      window.__forms = [];
      window.fetch = (input, init) => {
        if (init?.body instanceof FormData)
          window.__forms.push([...init.body.entries()].map(([k, v]) => [k, v instanceof File ? v.name : String(v)]));
        return send(input, init);
      };
    });
    await page.goto(`${base}/`, { waitUntil: "networkidle" });
    if (way === "sample") await page.getByRole("button", { name: "Use sample documents" }).click();
    else if (way === "drop") await dropPdf(page);
    else
      await page.setInputFiles('[data-testid="file-input"]', {
        name: "smith_documents.pdf",
        mimeType: "application/pdf",
        buffer: PDF_BYTES,
      });
    await page.waitForURL("**/reading", { timeout: 10_000 });
    const items = await page.locator('[data-testid="read-item"]').allInnerTexts();
    runs[way] = { rows: await readList(page) };
    const fields = await page.evaluate(() => window.__forms ?? []);
    uploads[way] = requests.map((r, i) => ({
      url: new URL(r.url()).pathname,
      type: r.headers()["content-type"] ?? "",
      body: JSON.stringify(fields[i] ?? null),
    }));
    void items;
    await context.close();
  }
  check(
    uploads.sample.length === 1 && uploads.sample[0].url.endsWith("/portal/documents/sample"),
    "Use sample documents posts to /portal/documents/sample",
  );
  for (const way of ["drop", "choose"]) {
    const u = uploads[way];
    check(
      u.length === 1 &&
        u[0].url.endsWith("/portal/documents/upload") &&
        u[0].type.startsWith("multipart/form-data") &&
        u[0].body === '[["file","smith_documents.pdf"]]',
      `${way}: the PDF goes to /portal/documents/upload as multipart field "file" (once)`,
    );
  }
  check(runs.sample.rows.length > 30, `Review lists ${runs.sample.rows.length} fields`);
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  check(same(runs.sample.rows, runs.drop.rows), "dropping the PDF and the sample link give identical Review lists");
  check(same(runs.sample.rows, runs.choose.rows), "choosing the PDF and the sample link give identical Review lists");

  // the list is the API's: same field keys in the same order
  if (sample) {
    const keys = sample.documents.flatMap((d) => d.fields.map((f) => f.key));
    check(
      same(
        keys,
        runs.sample.rows.map((r) => r[0]),
      ),
      `Review shows exactly the API's ${keys.length} fields, in order`,
    );
  }

  // --- the loaded file stays on Documents
  {
    const { context, page } = await newPage(browser);
    await page.goto(`${base}/`, { waitUntil: "networkidle" });
    await dropPdf(page);
    await readList(page);
    await page.getByRole("link", { name: "Documents" }).click();
    await page.waitForURL(`${base}/`);
    const card = page.locator('[data-testid="loaded-file"]');
    check((await card.innerText()).includes("smith_documents.pdf"), "back on Documents the loaded file is shown");
    check(await page.getByRole("button", { name: "Next" }).isEnabled(), "Next is available with the file loaded");
    await context.close();
  }
  void docLabel;
}

if (isMain(import.meta.url)) await runAlone(runDocuments, "documents");
