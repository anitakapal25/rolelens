import { createSSEParser } from "./sse";
import type { ChatStreamEvent, DocType, DocumentSummary, FitReport } from "./types";

export const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError("Can't reach the RoleLens API. Is the backend running?", 0);
  }
  if (!res.ok) throw new ApiError(await errorDetail(res), res.status);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

async function errorDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) return "The request was invalid.";
    }
  } catch {
    /* non-JSON error body */
  }
  return `Request failed (${res.status}).`;
}

export const listDocuments = () => request<DocumentSummary[]>("/documents");

export const listFits = () => request<FitReport[]>("/fit");

export interface AppConfig {
  demo: boolean;
  demo_rate_per_ip_hour: number;
}

export const getConfig = () => request<AppConfig>("/config");

export function uploadDocument(file: File, docType: DocType): Promise<DocumentSummary> {
  const form = new FormData();
  form.append("file", file);
  form.append("doc_type", docType);
  return request<DocumentSummary>("/documents", { method: "POST", body: form });
}

export const renameDocument = (docId: string, label: string) =>
  request<DocumentSummary>(`/documents/${docId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });

export const deleteDocument = (docId: string) =>
  request<void>(`/documents/${docId}`, { method: "DELETE" });

/** POST /chat and call onEvent for each SSE event as it arrives. */
export async function streamChat(
  question: string,
  onEvent: (e: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError("Can't reach the RoleLens API. Is the backend running?", 0);
  }
  if (!res.ok || !res.body) throw new ApiError(await errorDetail(res), res.status);

  const feed = createSSEParser(({ event, data }) => {
    onEvent({ event, data: JSON.parse(data) } as ChatStreamEvent);
  });
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    feed(value);
  }
}
