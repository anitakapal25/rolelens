import { useState } from "react";

import { displayLabel, sectionName } from "../lib/text";
import type { DocumentSummary } from "../lib/types";

interface Props {
  doc: DocumentSummary;
  readOnly?: boolean;
  onRename: (label: string) => Promise<void>;
  onDelete: () => Promise<void>;
}

export function DocumentCard({ doc, readOnly = false, onRename, onDelete }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(doc.label);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    const label = draft.trim();
    setEditing(false);
    if (!label || label === doc.label) return setDraft(doc.label);
    setBusy(true);
    try {
      await onRename(label);
    } catch {
      setDraft(doc.label);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Remove "${doc.label}"?`)) return;
    setBusy(true);
    try {
      await onDelete();
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className={`rounded-xl border border-stone-200 bg-white p-3 shadow-sm ${busy ? "opacity-60" : ""}`}>
      <div className="flex items-start gap-2">
        <span
          className={`mt-0.5 shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide
            ${doc.doc_type === "resume" ? "bg-accent-100 text-accent-800" : "bg-stone-100 text-stone-600"}`}
        >
          {doc.doc_type === "resume" ? "Resume" : `Job ${doc.job_number}`}
        </span>
        <div className="min-w-0 flex-1">
          {editing ? (
            <input
              autoFocus
              value={draft}
              maxLength={80}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={save}
              onKeyDown={(e) => {
                if (e.key === "Enter") void save();
                if (e.key === "Escape") {
                  setDraft(doc.label);
                  setEditing(false);
                }
              }}
              className="w-full rounded-md border border-accent-500 px-1.5 py-0.5 text-sm outline-none ring-2 ring-accent-100"
              aria-label="Document name"
            />
          ) : (
            <button
              type="button"
              onClick={() => !readOnly && setEditing(true)}
              title={readOnly ? doc.label : `${doc.label} (click to rename)`}
              className={`block w-full truncate text-left text-sm font-medium text-stone-900 ${readOnly ? "cursor-default" : "hover:text-accent-700"}`}
            >
              {displayLabel(doc.label)}
            </button>
          )}
          <p className="mt-0.5 truncate text-xs text-stone-500">
            {doc.filename} · {doc.chunk_count} chunks
          </p>
        </div>
        {!readOnly && <button
          type="button"
          onClick={remove}
          disabled={busy}
          className="rounded-md p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700"
          aria-label={`Remove ${doc.label}`}
          title="Remove"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor" aria-hidden="true">
            <path d="M6.3 5.3a1 1 0 0 1 1.4 0L10 7.6l2.3-2.3a1 1 0 1 1 1.4 1.4L11.4 9l2.3 2.3a1 1 0 0 1-1.4 1.4L10 10.4l-2.3 2.3a1 1 0 0 1-1.4-1.4L8.6 9 6.3 6.7a1 1 0 0 1 0-1.4Z" />
          </svg>
        </button>}
      </div>
      {doc.warnings.length > 0 && (
        <div role="note" className="mt-2 flex gap-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs text-amber-900">
          <svg viewBox="0 0 16 16" className="mt-0.5 h-3.5 w-3.5 shrink-0" fill="currentColor" aria-hidden="true">
            <path d="M8 1.5l7 12.5H1L8 1.5zm0 4.5a.75.75 0 0 0-.75.75v3a.75.75 0 0 0 1.5 0v-3A.75.75 0 0 0 8 6zm0 6.25a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8z" />
          </svg>
          <div>
            <p className="font-medium">Contains text addressed to AI tools</p>
            <p className="mt-0.5 text-amber-800">
              RoleLens treats it as ordinary document text and never follows it.
            </p>
            <p className="mt-1 italic text-amber-800" title={doc.warnings.join("\n")}>“{doc.warnings[0]}”</p>
          </div>
        </div>
      )}
      <ul className="mt-2 flex flex-wrap gap-1" aria-label="Detected sections">
        {doc.sections.map((s) => (
          <li key={s.name} className="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] text-stone-600">
            {sectionName(s.name)}
            {s.chunk_count > 1 && <span className="text-stone-400"> ×{s.chunk_count}</span>}
          </li>
        ))}
      </ul>
    </li>
  );
}
