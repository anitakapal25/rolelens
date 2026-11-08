export function SkeletonLines({ lines = 3 }: { lines?: number }) {
  const widths = ["w-11/12", "w-4/5", "w-2/3", "w-3/4", "w-1/2"];
  return (
    <div className="space-y-2" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className={`h-3 animate-shimmer rounded bg-stone-200 ${widths[i % widths.length]}`} />
      ))}
    </div>
  );
}
