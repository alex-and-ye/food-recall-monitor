import Link from "next/link";
import IncidentConfidence from "@/components/IncidentConfidence";
import IncidentStatusBadge from "@/components/IncidentStatusBadge";
import { bodySecondaryClassName, cardClassName } from "@/lib/ui";
import {
  INCIDENT_SOURCE_KIND_LABELS,
  INCIDENT_TYPE_LABELS,
  isIncidentSourceKind,
  type EarlyWarningIncident,
} from "@/types/incident";

function formatDate(value?: string | null): string {
  if (!value) return "Date not reported";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

function incidentTitle(incident: EarlyWarningIncident): string {
  return (
    incident.product_name?.trim() ||
    incident.company_name?.trim() ||
    incident.product_category?.trim() ||
    INCIDENT_TYPE_LABELS[incident.incident_type]
  );
}

export default function EarlyWarningIncidentCard({
  incident,
}: {
  incident: EarlyWarningIncident;
}) {
  const sourceLabel = isIncidentSourceKind(incident.source_kind)
    ? INCIDENT_SOURCE_KIND_LABELS[incident.source_kind]
    : incident.source_kind;
  const evidenceCount = incident.evidence?.length ?? 0;

  return (
    <Link
      href={`/incidents/${encodeURIComponent(incident.incident_id)}`}
      className={`block w-full ${cardClassName} p-5 text-left transition-colors hover:border-slate-400 hover:bg-slate-50`}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="mb-1 text-xs font-semibold tracking-wide text-slate-500 uppercase">
            {INCIDENT_TYPE_LABELS[incident.incident_type]}
          </p>
          <h2 className="text-lg font-semibold text-slate-950">
            {incidentTitle(incident)}
          </h2>
          {incident.summary && incident.summary !== incidentTitle(incident) ? (
            <p className={`mt-2 ${bodySecondaryClassName}`}>
              {incident.summary}
            </p>
          ) : null}
        </div>
        <IncidentStatusBadge status={incident.verification_status} />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-slate-200 pt-4">
        <IncidentConfidence score={incident.confidence_score} compact />
        <span className={`text-sm ${bodySecondaryClassName}`}>
          {evidenceCount} {evidenceCount === 1 ? "evidence source" : "evidence sources"}
        </span>
        <span className={`text-sm ${bodySecondaryClassName}`}>
          {sourceLabel}
        </span>
        {incident.country ? (
          <span className={`text-sm ${bodySecondaryClassName}`}>
            {incident.country}
          </span>
        ) : null}
        <time
          className={`text-sm sm:ml-auto ${bodySecondaryClassName}`}
          dateTime={incident.publication_date ?? incident.first_discovered_at}
        >
          {formatDate(incident.publication_date ?? incident.first_discovered_at)}
        </time>
      </div>
    </Link>
  );
}
