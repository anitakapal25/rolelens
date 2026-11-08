import { useEffect, useRef, useState } from "react";

import { ApiError, deleteDocument, renameDocument, uploadDocument } from "../lib/api";
import type { DocType, DocumentSummary } from "../lib/types";
import { DocumentCard } from "./DocumentCard";
import { Dropzone } from "./Dropzone";

interface Pending {
  id: string;
  name: string;
  docType: DocType;
  status: "queued" | "uploading" | "error";
  error?: string;
  startedAt?: number;
}

interface Props {
  documents: DocumentSummary[];
  loading: boolean;
  onChanged: () => Promise<void>;
  readOnly?: boolean;
}

export function UploadPanel({ documents, loading, onChanged, readOnly = false }: Props) {
  const [pending, setPending] = useState<Pending[]>([]);
  // Uploads run one at a time, in drop order, even across separate drops.
  const queue = useRef<Promise<void>>(Promise.resolve());

  const resume = documents.find((d) => d.doc_type === "resume");
  const jobs = documents.filter((d) => d.doc_type === "job");
  const update = (id: string, patch: Partial<Pending>) =>
    setPending((list) => list.map((p) => (p.id === id ? { ...p, ...patch } : p)));

  const enqueue = (files: File[], docType: DocType) => {
    for (const file of files) {
      const id = crypto.randomUUID();
      setPending((list) => [...list, { id, name: file.name, docType, status: "queued" }]);
      queue.current = queue.current.then(async () => {
        update(id, { status: "uploading", startedAt: Date.now() });
        try {
          await uploadDocument(file, docType);
          setPending((list) => list.filter((p) => p.id !== id));
          await onChanged();
        } catch (err) {
          update(id, { status: "error", error: err instanceof ApiError ? err.message : "Upload failed." });
        }
      });
    }
  };

  const rename = async (doc: DocumentSummary, label: string) => {
    await renameDocument(doc.doc_id, label);
    await onChanged();
  };
  const remove = async (doc: DocumentSummary) => {
    await deleteDocument(doc.doc_id);
    await onChanged();
  };

  const pendingOf = (t: DocType) => pending.filter((p) => p.docType === t);

  return (
    <div className="space-y-6">
      <section aria-labelledby="resume-heading">
        <h2 id="resume-heading" className="mb-2 text-xs font-semibold uppercase tracking-wider text-stone-500">
          Your resume
        </h2>
        {loading ? (
          <div className="h-20 animate-shimmer rounded-xl bg-stone-200" />
        ) : (
          <ul className="space-y-2">
            {resume && (
              <DocumentCard doc={resume} readOnly={readOnly} onRename={(l) => rename(resume, l)} onDelete={() => remove(resume)} />
            )}
            {pendingOf("resume").map((p) => (
              <PendingRow key={p.id} item={p} onDismiss={() => setPending((l) => l.filter((x) => x.id !== p.id))} />
            ))}
          </ul>
        )}
        <div className={readOnly ? "hidden" : "mt-2"}>
          <Dropzone
            title={resume ? "Replace resume" : "Drop your resume"}
            hint="PDF, DOCX or TXT · up to 5 MB"
            onFiles={(f) => enqueue(f, "resume")}
          />
        </div>
      </section>

      <section aria-labelledby="jobs-heading">
        <h2 id="jobs-heading" className="mb-2 text-xs font-semibold uppercase tracking-wider text-stone-500">
          Job descriptions {jobs.length > 0 && <span className="text-stone-400">({jobs.length})</span>}
        </h2>
        {loading ? (
          <div className="space-y-2">
            <div className="h-20 animate-shimmer rounded-xl bg-stone-200" />
            <div className="h-20 animate-shimmer rounded-xl bg-stone-200" />
          </div>
        ) : (
          <ul className="space-y-2">
            {jobs.map((job) => (
              <DocumentCard key={job.doc_id} doc={job} readOnly={readOnly} onRename={(l) => rename(job, l)} onDelete={() => remove(job)} />
            ))}
            {pendingOf("job").map((p) => (
              <PendingRow key={p.id} item={p} onDismiss={() => setPending((l) => l.filter((x) => x.id !== p.id))} />
            ))}
          </ul>
        )}
        <div className={readOnly ? "hidden" : "mt-2"}>
          <Dropzone
            title="Add job descriptions"
            hint="Drop one or more · paste the posting into a .txt file"
            multiple
            onFiles={(f) => enqueue(f, "job")}
          />
        </div>
      </section>
    </div>
  );
}

function PendingRow({ item, onDismiss }: { item: Pending; onDismiss: () => void }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (item.status !== "uploading") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [item.status]);
  const seconds = item.startedAt ? Math.max(0, Math.round((now - item.startedAt) / 1000)) : 0;

  if (item.status === "error") {
    return (
      <li className="rounded-xl border border-red-200 bg-red-50 p-3" role="alert">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-red-900">{item.name}</p>
            <p className="mt-0.5 text-xs text-red-700">{item.error}</p>
          </div>
          <button type="button" onClick={onDismiss} className="text-xs font-medium text-red-700 hover:underline">
            Dismiss
          </button>
        </div>
      </li>
    );
  }
  return (
    <li className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm" aria-live="polite">
      <p className="truncate text-sm font-medium text-stone-700">{item.name}</p>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-stone-100">
        <div
          className={`h-full rounded-full ${item.status === "uploading" ? "w-2/3 animate-shimmer bg-accent-500" : "w-0"}`}
        />
      </div>
      <p className="mt-1.5 text-xs text-stone-500">
        {item.status === "queued" ? "Waiting…" : `Reading, extracting skills and indexing… ${seconds}s`}
      </p>
    </li>
  );
}
