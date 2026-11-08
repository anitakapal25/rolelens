import { useEffect, useRef, useState } from "react";
import Markdown, { type Components } from "react-markdown";

import { citationNumber, linkCitations, sectionName } from "../lib/text";
import type { DoneEvent, RetrievedChunk, RouteResult } from "../lib/types";
import { SkeletonLines } from "./Skeleton";
import { SourceCard } from "./SourceCard";

export interface Turn {
  id: string;
  question: string;
  status: "retrieving" | "streaming" | "done" | "error";
  route?: RouteResult;
  sources: RetrievedChunk[];
  answer: string;
  done?: DoneEvent;
  error?: string;
}

export function Answer({ turn }: { turn: Turn }) {
  const [selected, setSelected] = useState<number | null>(null);
  const sourceRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (selected !== null) sourceRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [selected]);
  const byNumber = new Map(turn.sources.map((s) => [s.n, s]));
  const toggle = (n: number) => setSelected((cur) => (cur === n ? null : n));

  const components: Components = {
    a: ({ href, children }) => {
      const n = citationNumber(href);
      if (n === null || !byNumber.has(n)) return <span>{children}</span>;
      return (
        <button
          type="button"
          onClick={() => toggle(n)}
          aria-pressed={selected === n}
          aria-label={`Show source ${n}`}
          className={`mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded-full px-1 align-middle text-[10.5px] font-semibold transition
            ${selected === n ? "bg-accent-700 text-white" : "bg-accent-100 text-accent-800 hover:bg-accent-200"}`}
        >
          {n}
        </button>
      );
    },
  };

  const cited = (turn.done?.citations ?? []).map((n) => byNumber.get(n)).filter((s) => s !== undefined);
  const selectedSource = selected !== null ? byNumber.get(selected) : undefined;

  return (
    <div className="space-y-3">
      {turn.status === "retrieving" && (
        <div>
          <p className="mb-2 text-xs text-stone-500">Finding relevant parts of your documents…</p>
          <SkeletonLines lines={4} />
        </div>
      )}

      {turn.status !== "retrieving" && turn.route && (
        <p className="text-xs text-stone-500">
          Searched {turn.route.doc_ids.length} document{turn.route.doc_ids.length === 1 ? "" : "s"} ·{" "}
          {turn.sources.length} excerpts
        </p>
      )}

      {turn.status === "streaming" && !turn.answer && <SkeletonLines lines={3} />}

      {turn.answer && (
        <div className="prose-answer text-[15px] text-stone-800">
          <Markdown components={components}>{linkCitations(turn.answer)}</Markdown>
          {turn.status === "streaming" && (
            <span className="ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-shimmer bg-accent-500" aria-hidden="true" />
          )}
        </div>
      )}

      {turn.status === "error" && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {turn.error}
        </p>
      )}

      {selectedSource && (
        <div ref={sourceRef}>
          <SourceCard source={selectedSource} onClose={() => setSelected(null)} />
        </div>
      )}

      {turn.status === "done" && cited.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-stone-100 pt-2">
          <span className="text-xs text-stone-500">Sources</span>
          {cited.map((s) => (
            <button
              key={s.n}
              type="button"
              onClick={() => toggle(s.n)}
              className={`max-w-[16rem] truncate rounded-full border px-2 py-0.5 text-[11px] transition
                ${selected === s.n ? "border-accent-700 bg-accent-700 text-white" : "border-stone-200 bg-white text-stone-600 hover:border-accent-500"}`}
              title={`${s.chunk.doc_label} · ${sectionName(s.chunk.section)}`}
            >
              {s.n} · {s.chunk.doc_label.split(" — ")[0]} · {sectionName(s.chunk.section)}
            </button>
          ))}
          {turn.done && (
            <span className="ml-auto text-[11px] text-stone-400">
              {(turn.done.latency_ms / 1000).toFixed(1)}s · ${turn.done.usage.cost_usd.toFixed(4)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
