function clampConfidence(score: number): number {
  if (!Number.isFinite(score)) {
    return 0;
  }
  return Math.min(100, Math.max(0, Math.round(score)));
}

function confidenceLabel(score: number): string {
  if (score >= 85) return "Very high";
  if (score >= 70) return "High";
  if (score >= 50) return "Moderate";
  return "Low";
}

function confidenceColor(score: number): string {
  if (score >= 85) return "bg-emerald-600";
  if (score >= 70) return "bg-sky-600";
  if (score >= 50) return "bg-amber-500";
  return "bg-slate-500";
}

export default function IncidentConfidence({
  score,
  compact = false,
}: {
  score: number;
  compact?: boolean;
}) {
  const value = clampConfidence(score);

  if (compact) {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-700">
        <span
          className={`h-2 w-2 rounded-full ${confidenceColor(value)}`}
          aria-hidden="true"
        />
        {value}% confidence
      </span>
    );
  }

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-4">
        <span className="text-sm font-medium text-slate-700">
          {confidenceLabel(value)} confidence
        </span>
        <span className="text-sm font-semibold text-slate-950">{value}%</span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-slate-200"
        role="progressbar"
        aria-label="Incident confidence"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
      >
        <div
          className={`h-full rounded-full ${confidenceColor(value)}`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}
