// Mirrors backend/app/models.py. Keep in sync when the API changes.

export type DocType = "resume" | "job";

export interface SectionSummary {
  name: string;
  chunk_count: number;
}

export interface DocumentSummary {
  doc_id: string;
  doc_type: DocType;
  label: string;
  filename: string;
  job_number: number | null;
  page_count: number;
  char_count: number;
  chunk_count: number;
  sections: SectionSummary[];
  created_at: string;
}

export interface Chunk {
  chunk_id: string;
  doc_id: string;
  doc_type: DocType;
  doc_label: string;
  section: string;
  index: number;
  text: string;
  company?: string | null;
  role?: string | null;
  entry?: string | null;
}

export interface RetrievedChunk {
  n: number;
  chunk: Chunk;
  distance: number;
}

export interface RouteResult {
  doc_ids: string[];
  scope: "resume_only" | "specific_jobs" | "all_jobs" | null;
  method: "keyword" | "llm" | "fallback" | "empty";
  reason: string;
}

export interface Usage {
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface DoneEvent {
  citations: number[];
  stop_reason: string | null;
  usage: Usage;
  latency_ms: number;
}

export type ChatStreamEvent =
  | { event: "route"; data: RouteResult }
  | { event: "sources"; data: { sources: RetrievedChunk[] } }
  | { event: "token"; data: { text: string } }
  | { event: "done"; data: DoneEvent }
  | { event: "error"; data: { detail: string; retryable: boolean } };
