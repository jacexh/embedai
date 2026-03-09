export function QualityBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    score >= 0.6 ? "bg-green-100 text-green-800" :
    score >= 0.3 ? "bg-yellow-100 text-yellow-800" :
                   "bg-red-100 text-red-800";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {pct}%
    </span>
  );
}
