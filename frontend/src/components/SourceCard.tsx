import { sectionName } from "../lib/text";
import type { RetrievedChunk } from "../lib/types";

export function SourceCard({ source, onClose }: { source: RetrievedChunk; onClose?: () => void }) {
  const { chunk } = source;
  return (
    <figure className="rounded-lg border border-accent-200 bg-accent-50/60 p-3 text-sm">
      <figcaption className="mb-1.5 flex items-start justify-between gap-2">
        <span className="text-xs text-stone-600">
          <span className="mr-1.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-accent-700 px-1 text-[11px] font-semibold text-white">
            {source.n}
          </span>
          <span className="font-medium text-stone-900">{chunk.doc_label}</span>
          {" · "}
          {sectionName(chunk.section)}
          {chunk.entry && <> · {chunk.entry}</>}
        </span>
        {onClose && (
          <button type="button" onClick={onClose} className="text-xs text-stone-500 hover:text-stone-800" aria-label="Close source">
            Close
          </button>
        )}
      </figcaption>
      <blockquote className="max-h-56 overflow-y-auto whitespace-pre-wrap border-l-2 border-accent-500 pl-3 text-[13px] leading-relaxed text-stone-700">
        {chunk.text}
      </blockquote>
    </figure>
  );
}
