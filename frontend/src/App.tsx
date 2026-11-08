import { useCallback, useEffect, useState } from "react";

import { Chat } from "./components/Chat";
import { UploadPanel } from "./components/UploadPanel";
import { ApiError, listDocuments } from "./lib/api";
import type { DocumentSummary } from "./lib/types";

export default function App() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDocuments(await listDocuments());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load documents.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="flex h-dvh flex-col">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-6 py-3">
          <svg viewBox="0 0 32 32" className="h-7 w-7 text-accent-700" aria-hidden="true">
            <circle cx="14" cy="14" r="9" fill="none" stroke="currentColor" strokeWidth="3" />
            <path d="M21 21l7 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
          </svg>
          <div>
            <h1 className="text-base font-bold leading-tight tracking-tight text-stone-900">RoleLens</h1>
            <p className="text-xs text-stone-500">See your resume through the lens of any role.</p>
          </div>
        </div>
      </header>

      {error && (
        <div role="alert" className="border-b border-red-200 bg-red-50">
          <p className="mx-auto max-w-7xl px-6 py-2 text-sm text-red-800">
            {error}{" "}
            <button type="button" onClick={() => void refresh()} className="font-medium underline">
              Retry
            </button>
          </p>
        </div>
      )}

      <main className="mx-auto grid w-full max-w-7xl flex-1 grid-cols-1 gap-6 overflow-hidden px-6 py-6 lg:grid-cols-[340px_1fr]">
        <aside className="overflow-y-auto pr-1" aria-label="Documents">
          <UploadPanel documents={documents} loading={loading} onChanged={refresh} />
        </aside>
        <section className="flex min-h-0 flex-col" aria-label="Chat">
          <Chat documents={documents} />
        </section>
      </main>
    </div>
  );
}
