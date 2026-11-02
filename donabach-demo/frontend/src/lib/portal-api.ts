// Client for the portal API (proxied at /api, see next.config.ts).
import type {
  InvestRequest,
  Overrides,
  Plan,
  PortalAnswers,
  PortalDocuments,
  PortalHouseholdResponse,
} from "./portal-types";

const BASE = "/api";

export class PortalApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function messageOf(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const text = detail
      .map((d: { msg?: string }) => d.msg)
      .filter(Boolean)
      .join("; ");
    if (text) return text;
  }
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  return `Request failed (${status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new PortalApiError(0, "Could not reach the server.");
  }
  if (!response.ok) {
    let detail: unknown = undefined;
    try {
      detail = (await response.json()).detail;
    } catch {
      /* not JSON */
    }
    throw new PortalApiError(response.status, messageOf(detail, response.status));
  }
  return (await response.json()) as T;
}

const postJson = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const portalApi = {
  sampleDocuments: () => request<PortalDocuments>("/portal/documents/sample", { method: "POST" }),
  uploadDocuments: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<PortalDocuments>("/portal/documents/upload", { method: "POST", body: form });
  },
  /** URL of the PDF itself, for the viewer. */
  documentUrl: (id: string) => `${BASE}/portal/documents/${encodeURIComponent(id)}/file`,
  defaults: () => request<PortalAnswers>("/portal/defaults"),
  household: (documentId: string, overrides: Overrides, answers: PortalAnswers) =>
    postJson<PortalHouseholdResponse>("/portal/household", { document_id: documentId, overrides, answers }),
  invest: (body: InvestRequest) => postJson<Plan>("/portal/invest", body),
};
