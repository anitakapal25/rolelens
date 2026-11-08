import { useEffect, useState } from "react";

import { ApiError, listFits } from "../lib/api";
import { displayLabel } from "../lib/text";
import type { DocumentSummary, FitReport, MatchStatus, SkillFit, Verdict } from "../lib/types";
import { SkeletonLines } from "./Skeleton";

const VERDICT_LABEL: Record<Verdict, string> = {
  strong: "Strong fit",
  good: "Good fit with gaps",
  stretch: "Stretch",
  weak: "Weak fit",
};

export function FitDashboard({ documents }: { documents: DocumentSummary[] }) {
  const [fits, setFits] = useState<FitReport[] | null>(null);
  const [error, setError] = useState<{ message: string; status: number } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  // Re-fetch whenever the set of documents (or a label) changes.
  const docsKey = documents.map((d) => `${d.doc_id}:${d.label}`).join("|");
  const hasJobs = documents.some((d) => d.doc_type === "job");

  useEffect(() => {
    if (!hasJobs) return;
    let cancelled = false;
    setFits(null);
    setError(null);
    listFits()
      .then((data) => {
        if (cancelled) return;
        setFits(data);
        const best = [...data].sort((a, b) => b.score - a.score)[0];
        setSelected((cur) => (cur && data.some((f) => f.job_id === cur) ? cur : (best?.job_id ?? null)));
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? { message: err.message, status: err.status } : { message: "Could not load fit scores.", status: 0 });
      });
    return () => {
      cancelled = true;
    };
  }, [docsKey, hasJobs]);

  if (!hasJobs) {
    return <EmptyState title="No jobs yet" body="Add a job description on the left to see how your resume fits it." />;
  }
  if (error?.status === 409) {
    return <EmptyState title="Add your resume" body={error.message} />;
  }
  if (error) {
    return <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error.message}</p>;
  }
  if (!fits) return <DashboardSkeleton />;

  const current = fits.find((f) => f.job_id === selected) ?? fits[0];
  return (
    <div className="space-y-6 overflow-y-auto pb-6 pr-1">
      {fits.length > 1 && <Comparison fits={fits} selected={current?.job_id ?? null} onSelect={setSelected} />}
      {current && <JobFit fit={current} />}
    </div>
  );
}

// ---------- multi-job comparison: ranked horizontal bars, one hue ----------

function Comparison({ fits, selected, onSelect }: { fits: FitReport[]; selected: string | null; onSelect: (id: string) => void }) {
  const [hover, setHover] = useState<string | null>(null);
  const ranked = [...fits].sort((a, b) => b.score - a.score);
  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm" aria-labelledby="compare-heading">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 id="compare-heading" className="text-sm font-semibold text-stone-900">Fit score by role</h2>
        <span className="text-xs text-stone-500">0–100 · click a role for details</span>
      </div>
      <ul className="space-y-2.5">
        {ranked.map((f) => (
          <li key={f.job_id} className="relative">
            <button
              type="button"
              onClick={() => onSelect(f.job_id)}
              onMouseEnter={() => setHover(f.job_id)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(f.job_id)}
              onBlur={() => setHover(null)}
              aria-pressed={selected === f.job_id}
              className={`grid w-full grid-cols-[minmax(0,14rem)_1fr_2.5rem] items-center gap-3 rounded-lg px-2 py-1.5 text-left transition
                ${selected === f.job_id ? "bg-accent-50" : "hover:bg-stone-50"}`}
            >
              <span className="truncate text-sm text-stone-700" title={f.job_label}>
                <span className="font-medium text-stone-900">Job {f.job_number}</span> · {displayLabel(f.job_label)}
              </span>
              <span className="relative h-3 rounded-r bg-transparent">
                <span className="absolute inset-y-0 left-0 border-l border-stone-300" aria-hidden="true" />
                <span
                  className={`absolute inset-y-0 left-0 rounded-r ${selected === f.job_id ? "bg-accent-700" : "bg-accent-500"}`}
                  style={{ width: `${Math.max(f.score, 1)}%` }}
                />
              </span>
              <span className="text-right text-sm font-semibold tabular-nums text-stone-900">{f.score}</span>
            </button>
            {hover === f.job_id && (
              <div role="tooltip" className="pointer-events-none absolute left-1/3 top-full z-10 mt-1 w-72 rounded-lg border border-stone-200 bg-white p-3 text-xs shadow-lg">
                <p className="font-semibold text-stone-900">{f.job_label}</p>
                <p className="mt-1 text-stone-600">{f.verdict_text}</p>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

// ---------- one job in detail ----------

function JobFit({ fit }: { fit: FitReport }) {
  const c = fit.counts;
  const exp = fit.experience;
  const subtitle = [fit.title, fit.company, fit.seniority !== "unspecified" ? fit.seniority.replace(/_/g, " ") : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <section className="space-y-5" aria-labelledby="job-fit-heading">
      <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wider text-stone-500">Job {fit.job_number}</p>
        <h2 id="job-fit-heading" className="mt-0.5 text-lg font-semibold text-stone-900">{displayLabel(fit.job_label)}</h2>
        {subtitle && <p className="text-sm capitalize text-stone-500">{subtitle}</p>}

        <div className="mt-5 grid gap-6 md:grid-cols-[auto_1fr] md:items-center">
          <div>
            <p className="flex items-baseline gap-1">
              <span className="text-5xl font-bold tabular-nums tracking-tight text-stone-900">{fit.score}</span>
              <span className="text-sm text-stone-500">/ 100</span>
            </p>
            <p className="mt-1 text-sm font-semibold text-accent-800">{VERDICT_LABEL[fit.verdict]}</p>
          </div>
          <div>
            <div
              className="h-2 w-full overflow-hidden rounded-full bg-accent-100"
              role="meter"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={fit.score}
              aria-label="Fit score"
            >
              <div className="h-full rounded-full bg-accent-700" style={{ width: `${fit.score}%` }} />
            </div>
            <p className="mt-3 text-sm text-stone-700">{fit.verdict_text}</p>
          </div>
        </div>

        <dl className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Stat label="Required skills matched" value={`${c.required_matched} / ${c.required_total}`}
                sub={c.required_partial ? `+${c.required_partial} partly` : undefined} />
          <Stat label="Preferred skills matched" value={`${c.preferred_matched} / ${c.preferred_total}`}
                sub={c.preferred_partial ? `+${c.preferred_partial} partly` : undefined} />
          <Stat
            label="Experience"
            value={exp.candidate_years != null ? `${exp.candidate_years} yrs` : "—"}
            sub={exp.required_years != null
              ? `role asks ${exp.required_years}+ · ${exp.met === null ? "can't compare" : exp.met ? "met" : "below"}`
              : "no requirement stated"}
          />
        </dl>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <SkillList title="Missing" hint="Ranked by how prominent they are in the job" status="missing" skills={fit.missing} />
        <SkillList title="Partial" hint="Related but weaker evidence" status="partial" skills={fit.partial} />
        <SkillList title="Matched" hint="With the resume evidence that backs them" status="match" skills={fit.matched} />
      </div>

      <details className="rounded-xl border border-stone-200 bg-white p-4 text-sm text-stone-600">
        <summary className="cursor-pointer font-medium text-stone-800">How is the score calculated?</summary>
        <p className="mt-2">
          Each requirement has a weight: core 3, supporting 2, minor 1, halved for preferred items. A match earns
          the full weight, a partial match half, a missing one nothing. Years of experience count as one more
          requirement (weight 2) when both numbers are known. Score = earned ÷ total × 100.
        </p>
        <p className="mt-2">
          Skills are extracted from each document once, and an AI model judges match / partial / missing per
          requirement. The arithmetic above is plain code, so the same judgements always give the same score.
        </p>
      </details>
    </section>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl bg-stone-50 px-4 py-3">
      <dt className="text-xs text-stone-500">{label}</dt>
      <dd className="mt-0.5 text-xl font-semibold tabular-nums text-stone-900">{value}</dd>
      {sub && <dd className="text-xs text-stone-500">{sub}</dd>}
    </div>
  );
}

function StatusIcon({ status }: { status: MatchStatus }) {
  const common = { viewBox: "0 0 16 16", className: "h-3.5 w-3.5", "aria-hidden": true } as const;
  if (status === "match")
    return <svg {...common} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M3.5 8.5l3 3 6-7" /></svg>;
  if (status === "partial")
    return <svg {...common}><circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.8" /><path d="M8 2.5a5.5 5.5 0 0 1 0 11z" fill="currentColor" /></svg>;
  return <svg {...common} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7" /></svg>;
}

const STATUS_STYLE: Record<MatchStatus, { label: string; tone: string }> = {
  match: { label: "Matched", tone: "bg-accent-100 text-accent-800" },
  partial: { label: "Partial", tone: "bg-amber-100 text-amber-800" },
  missing: { label: "Missing", tone: "bg-rose-100 text-rose-800" },
};

function SkillList({ title, hint, status, skills }: { title: string; hint: string; status: MatchStatus; skills: SkillFit[] }) {
  const style = STATUS_STYLE[status];
  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm" aria-label={title}>
      <header className="mb-3 flex items-center gap-2">
        <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full ${style.tone}`} aria-hidden="true">
          <StatusIcon status={status} />
        </span>
        <h3 className="text-sm font-semibold text-stone-900">
          {title} <span className="font-normal text-stone-400">({skills.length})</span>
        </h3>
      </header>
      <p className="-mt-2 mb-3 text-xs text-stone-500">{hint}</p>
      {skills.length === 0 ? (
        <p className="text-sm text-stone-400">None</p>
      ) : (
        <ul className="divide-y divide-stone-100">
          {skills.map((s) => <SkillRow key={s.name} skill={s} statusLabel={style.label} />)}
        </ul>
      )}
    </section>
  );
}

function SkillRow({ skill, statusLabel }: { skill: SkillFit; statusLabel: string }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="py-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={`${skill.name}, ${statusLabel}, ${skill.importance}`}
        className="flex w-full items-start gap-2 text-left"
      >
        <span className="flex-1 text-sm text-stone-800">{skill.name}</span>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide
          ${skill.importance === "required" ? "bg-stone-800 text-white" : "bg-stone-100 text-stone-600"}`}>
          {skill.importance}
        </span>
        {skill.emphasis === "core" && (
          <span className="shrink-0 rounded bg-stone-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-stone-600">
            core
          </span>
        )}
      </button>
      {open && (
        <div className="mt-2 space-y-2 rounded-lg bg-stone-50 p-3 text-xs text-stone-600">
          <p>{skill.note}</p>
          <p><span className="font-medium text-stone-800">Job says: </span>“{skill.job_evidence}”</p>
          {skill.resume_evidence.map((quote, i) => (
            <p key={i}>
              <span className="font-medium text-stone-800">Your resume ({skill.resume_skills[i]}): </span>“{quote}”
            </p>
          ))}
        </div>
      )}
    </li>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="mx-auto max-w-md pt-16 text-center">
      <h2 className="text-lg font-semibold text-stone-900">{title}</h2>
      <p className="mt-1 text-sm text-stone-500">{body}</p>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading fit scores">
      <div className="rounded-2xl border border-stone-200 bg-white p-5">
        <p className="mb-3 text-xs text-stone-500">Matching each job's requirements against your resume…</p>
        <SkeletonLines lines={3} />
      </div>
      <div className="rounded-2xl border border-stone-200 bg-white p-5">
        <div className="mb-4 h-10 w-24 animate-shimmer rounded bg-stone-200" />
        <SkeletonLines lines={4} />
      </div>
    </div>
  );
}
