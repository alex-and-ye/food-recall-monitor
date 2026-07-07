import { getRiskBadgeClassName } from "@/lib/alertStyles";
import {
  detailLabelClassName,
  detailMetaClassName,
  detailValueClassName,
  mutedTextClassName,
  sourceLinkClassName,
} from "@/lib/ui";
import type { FoodRecallAlert } from "@/types/alert";

const formatText = (value?: string | null) =>
  value && value.trim() ? value : "Not available";

const formatTextArray = (value?: string[] | null) =>
  value && value.length > 0 ? value.join(", ") : "Not available";

export default function FoodRecallAlertDetails({
  alert,
}: {
  alert: FoodRecallAlert;
}) {
  const hasSourceUrl = Boolean(alert.source_url && alert.source_url.trim());

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-2xl font-semibold text-slate-950">
          {formatText(alert.product_name)}
        </h2>
        <time
          className={`mt-1 block ${detailMetaClassName}`}
          dateTime={formatText(alert.recall_date)}
        >
          {formatText(alert.recall_date)}
        </time>
      </div>

      <div>
        <span className={detailLabelClassName}>Country Source:</span>
        <p className={detailValueClassName}>
          {formatText(alert.country_source)}
        </p>
      </div>

      <div>
        <span className={detailLabelClassName}>Product Category:</span>
        <p className={detailValueClassName}>{formatText(alert.product_category)}</p>
      </div>

      <div>
        <span className={`block ${detailLabelClassName}`}>Risk Level:</span>
        <span
          className={`mt-1 inline-block rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${getRiskBadgeClassName(alert.risk_level)}`}
        >
          {formatText(alert.risk_level)}
        </span>
      </div>

      <div>
        <span className={detailLabelClassName}>Recall Reason:</span>
        <p className={detailValueClassName}>{formatText(alert.recall_reason)}</p>
      </div>

      <div>
        <span className={detailLabelClassName}>Hazard Type:</span>
        <p className={detailValueClassName}>{formatText(alert.hazard_type)}</p>
      </div>

      <div>
        <span className={detailLabelClassName}>Description:</span>
        <p className={detailValueClassName}>{formatText(alert.summary)}</p>
      </div>

      <div>
        <span className={detailLabelClassName}>Consumer Action:</span>
        <p className={detailValueClassName}>{formatText(alert.consumer_action)}</p>
      </div>

      <div>
        <span className={detailLabelClassName}>Affected Regions:</span>
        <p className={detailValueClassName}>
          {formatTextArray(alert.affected_regions)}
        </p>
      </div>

      {hasSourceUrl ? (
        <a
          href={alert.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className={sourceLinkClassName}
        >
          View Official Source
        </a>
      ) : (
        <p className={`mt-2 ${mutedTextClassName}`}>Official source not provided.</p>
      )}
    </div>
  );
}
