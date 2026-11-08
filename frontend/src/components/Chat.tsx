import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, streamChat } from "../lib/api";
import { suggestedQuestions } from "../lib/text";
import type { ChatStreamEvent, DocumentSummary } from "../lib/types";
import { Answer, type Turn } from "./Answer";

export function Chat({ documents }: { documents: DocumentSummary[] }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const busy = turns.some((t) => t.status === "retrieving" || t.status === "streaming");
  const hasResume = documents.some((d) => d.doc_type === "resume");
  const jobLabels = documents.filter((d) => d.doc_type === "job").map((d) => d.label);
  const ready = documents.length > 0;

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const patch = (id: string, fn: (t: Turn) => Turn) => setTurns((list) => list.map((t) => (t.id === id ? fn(t) : t)));

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    const id = crypto.randomUUID();
    setDraft("");
    setTurns((list) => [...list, { id, question: q, status: "retrieving", sources: [], answer: "" }]);

    const onEvent = (e: ChatStreamEvent) => {
      switch (e.event) {
        case "route":
          return patch(id, (t) => ({ ...t, route: e.data }));
        case "sources":
          return patch(id, (t) => ({ ...t, sources: e.data.sources, status: "streaming" }));
        case "token":
          return patch(id, (t) => ({ ...t, answer: t.answer + e.data.text }));
        case "done":
          return patch(id, (t) => ({ ...t, done: e.data, status: "done" }));
        case "error":
          return patch(id, (t) => ({ ...t, status: "error", error: e.data.detail }));
      }
    };
    try {
      await streamChat(q, onEvent);
      // A stream that ends without done/error was cut off.
      patch(id, (t) => (t.status === "done" || t.status === "error"
        ? t : { ...t, status: "error", error: "The answer was interrupted. Try again." }));
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Something went wrong. Try again.";
      patch(id, (t) => ({ ...t, status: "error", error: message }));
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void ask(draft);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-6 overflow-y-auto px-1 pb-4">
        {turns.length === 0 && (
          <div className="mx-auto max-w-xl pt-10 text-center">
            <h2 className="text-lg font-semibold text-stone-900">
              {ready ? "Ask about your fit" : "Start by adding your documents"}
            </h2>
            <p className="mt-1 text-sm text-stone-500">
              {ready
                ? "Answers come only from your resume and job descriptions, with numbered sources you can open."
                : "Upload your resume and at least one job description on the left."}
            </p>
            {ready && !hasResume && (
              <p className="mt-2 text-xs text-amber-700">Tip: add your resume so answers can compare it with the jobs.</p>
            )}
            {ready && (
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {suggestedQuestions(jobLabels).map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => void ask(q)}
                    className="rounded-full border border-stone-200 bg-white px-3 py-1.5 text-sm text-stone-700 shadow-sm transition hover:border-accent-500 hover:text-accent-800"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {turns.map((turn) => (
          <article key={turn.id} className="space-y-3">
            <div className="flex justify-end">
              <p className="max-w-[85%] rounded-2xl rounded-br-md bg-stone-900 px-4 py-2 text-[15px] text-white">
                {turn.question}
              </p>
            </div>
            <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
              <Answer turn={turn} />
            </div>
          </article>
        ))}
        <div ref={bottom} />
      </div>

      <form onSubmit={submit} className="border-t border-stone-200 bg-stone-50 pt-3">
        <div className="flex items-end gap-2 rounded-2xl border border-stone-300 bg-white p-2 shadow-sm focus-within:border-accent-500 focus-within:ring-2 focus-within:ring-accent-100">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void ask(draft);
              }
            }}
            rows={1}
            maxLength={2000}
            disabled={!ready}
            placeholder={ready ? "Ask about your fit, gaps, or interview prep…" : "Upload documents to start"}
            aria-label="Your question"
            className="max-h-40 min-h-[2.5rem] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-stone-400 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!ready || busy || !draft.trim()}
            className="rounded-xl bg-accent-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent-800 disabled:cursor-not-allowed disabled:bg-stone-300"
          >
            {busy ? "Thinking…" : "Ask"}
          </button>
        </div>
        <p className="mt-1.5 px-1 text-[11px] text-stone-400">Enter to send · Shift+Enter for a new line</p>
      </form>
    </div>
  );
}
