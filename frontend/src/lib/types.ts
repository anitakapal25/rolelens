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
  warnings: string[];
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

export type MatchStatus = "match" | "partial" | "missing";
export type Verdict = "strong" | "good" | "stretch" | "weak";

export interface SkillFit {
  name: string;
  category: string;
  importance: "required" | "preferred";
  emphasis: "core" | "supporting" | "minor";
  status: MatchStatus;
  weight: number;
  job_evidence: string;
  resume_skills: string[];
  resume_evidence: string[];
  note: string;
}

export interface FitReport {
  job_id: string;
  job_label: string;
  job_number: number | null;
  title: string | null;
  company: string | null;
  seniority: string;
  score: number;
  verdict: Verdict;
  verdict_text: string;
  experience: { required_years: number | null; candidate_years: number | null; met: boolean | null };
  counts: {
    required_total: number;
    required_matched: number;
    required_partial: number;
    preferred_total: number;
    preferred_matched: number;
    preferred_partial: number;
  };
  matched: SkillFit[];
  partial: SkillFit[];
  missing: SkillFit[];
}
