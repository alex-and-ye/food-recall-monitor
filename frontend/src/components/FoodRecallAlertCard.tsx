import type { FoodRecallAlert, RiskLevel } from "@/types/alert";

interface FoodRecallAlertCardProps {
  alert: FoodRecallAlert;
}

const RISK_STYLES: Record<
  RiskLevel,
  { badge: string }
> = {
  High: {
    badge: "bg-red-700 text-white",
  },
  Medium: {
    badge: "bg-amber-500 text-black",
  },
  Low: {
    badge: "bg-emerald-700 text-white",
  },
};

const formatText = (value?: string | null) =>
  value && value.trim() ? value : "Not available";

const formatTextArray = (value?: string[] | null) =>
  value && value.length > 0 ? value.join(", ") : "Not available";

export default function FoodRecallAlertCard({ alert }: FoodRecallAlertCardProps) {
  const styles = RISK_STYLES[alert.risk_level] ?? {
    badge: "bg-slate-200 text-slate-800",
  };

  const hasSourceUrl = Boolean(alert.source_url && alert.source_url.trim());

  return (
    <article className="w-full rounded-xl border border-slate-300 bg-white p-6 shadow-sm">
      <div className="space-y-3">
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-2xl font-semibold text-slate-950">
            {formatText(alert.product_name)}
          </h1>
          <time
            className="shrink-0 text-sm font-medium text-slate-700"
            dateTime={formatText(alert.recall_date)}
          >
            {formatText(alert.recall_date)}
          </time>
        </div>

        <div>
          <span className="text-base font-medium text-slate-900">Product Category:</span>
          <p className="mt-1 text-base text-slate-900">{formatText(alert.product_category)}</p>
        </div>

        <div>
          <span className="block text-base font-medium text-slate-900">Risk Level:</span>
          <span
            className={`mt-1 inline-block rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${styles.badge}`}
          >
            {formatText(alert.risk_level)}
          </span>
        </div>

        <div>
          <span className="text-base font-medium text-slate-900">Recall Reason:</span>
          <p className="mt-1 text-base text-slate-900">{formatText(alert.recall_reason)}</p>
        </div>

        <div>
          <span className="text-base font-medium text-slate-900">Hazard Type:</span>
          <p className="mt-1 text-base text-slate-900">{formatText(alert.hazard_type)}</p>
        </div>

        <div>
          <span className="text-base font-medium text-slate-900">Description:</span>
          <p className="mt-1 text-base text-slate-900">{formatText(alert.summary)}</p>
        </div>

        <div>
          <span className="text-base font-medium text-slate-900">Consumer Action:</span>
          <p className="mt-1 text-base text-slate-900">{formatText(alert.consumer_action)}</p>
        </div>

        <div>
          <span className="text-base font-medium text-slate-900">Affected Regions:</span>
          <p className="mt-1 text-base text-slate-900">{formatTextArray(alert.affected_regions)}</p>
        </div>

        {hasSourceUrl ? (
          <a
            href={alert.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-block rounded-lg border border-slate-900 bg-white px-4 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-900 hover:text-white"
          >
            View Official Source
          </a>
        ) : (
          <p className="mt-2 text-sm text-slate-500">Official source not provided.</p>
        )}
      </div>
    </article>
  );
}
