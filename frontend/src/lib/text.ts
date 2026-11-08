// Small pure helpers for display.

/** Turn "[3]" citations into markdown links "[3](#cite-3)" so the renderer can swap in pills. */
export function linkCitations(markdown: string): string {
  return markdown.replace(/\[(\d{1,3})\](?!\()/g, "[$1](#cite-$1)");
}

export function citationNumber(href: string | undefined): number | null {
  const m = href?.match(/^#cite-(\d+)$/);
  return m?.[1] ? Number(m[1]) : null;
}

export function sectionName(section: string): string {
  return section.replace(/_/g, " ");
}

/** "Job #1 — Forward Deployed Engineer, HCLTech" -> "HCLTech" (text after the last comma). */
export function companyFromLabel(label: string): string | null {
  const afterDash = label.split(" — ")[1];
  if (!afterDash || !afterDash.includes(",")) return null;
  return afterDash.slice(afterDash.lastIndexOf(",") + 1).trim() || null;
}

export function suggestedQuestions(jobLabels: string[]): string[] {
  const company = jobLabels.map(companyFromLabel).find((c) => c);
  const interview = company
    ? `What should I prepare for the ${company} interview?`
    : "What should I prepare for the Job #1 interview?";
  return [
    "What skills am I missing?",
    "How do I compare across these roles?",
    "Which role fits me best?",
    interview,
  ];
}

/** The badge already says "Job 2" / "Resume": drop that prefix from the card title. */
export function displayLabel(label: string): string {
  const stripped = label.replace(/^(Job #\d+|Resume)\s+—\s+/, "");
  return stripped || label;
}
