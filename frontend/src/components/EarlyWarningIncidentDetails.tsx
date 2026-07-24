import Link from "next/link";
import IncidentConfidence from "@/components/IncidentConfidence";
import IncidentStatusBadge from "@/components/IncidentStatusBadge";
import {
  detailLabelClassName,
  detailMetaClassName,
  detailValueClassName,
  mutedTextClassName,
  sourceLinkClassName,
} from "@/lib/ui";
import {
  INCIDENT_SOURCE_KIND_LABELS,
  INCIDENT_TYPE_LABELS,
  isIncidentSourceKind,
  type EarlyWarningIncident,
  type IncidentEvidence,
} from "@/types/incident";

function formatText(value?: string | null): string {
  return value?.trim() || "Not available";
}

function formatDate(value?: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: value.includes("T") ? "short" : undefined,
  }).format(date);
}

function sourceKindLabel(value?: string | null): string {
  return value && isIncidentSourceKind(value)
    ? INCIDENT_SOURCE_KIND_LABELS[value]
    : formatText(value);
}

function EvidenceItem({
  evidence,
  index,
}: {
  evidence: IncidentEvidence;
  index: number;
}) {
  const hasUrl = Boolean(evidence.url?.trim());

  return (
    <li className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="font-medium text-slate-950">
          {formatText(evidence.title) === "Not available"
            ? `Evidence source ${index + 1}`
            : evidence.title}
        </p>
        <span className={mutedTextClassName}>
          {sourceKindLabel(evidence.source_kind)}
        </span>
      </div>
      <p className={`mt-1 ${detailMetaClassName}`}>
        {[evidence.publisher, evidence.domain].filter(Boolean).join(" · ") ||
          "Publisher not available"}
        {evidence.publication_date
          ? ` · ${formatDate(evidence.publication_date)}`
          : ""}
      </p>
      {hasUrl ? (
        <a
          href={evidence.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-block text-sm font-medium text-emerald-700 underline-offset-2 hover:underline"
        >
          Open evidence
        </a>
      ) : null}
    </li>
  );
}

export default function EarlyWarningIncidentDetails({
  incident,
}: {
  incident: EarlyWarningIncident;
}) {
  const hasReportedSource = Boolean(incident.primary_source_url?.trim());
  const confidenceReasons = incident.confidence_reasons ?? [];
  const evidence = incident.evidence ?? [];
  const linkedOfficialAlerts = incident.linked_official_alert_ids ?? [];

  return (
    <div className="space-y-8">
      <div>
        <p className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
          {INCIDENT_TYPE_LABELS[incident.incident_type]}
        </p>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-slate-950">
              {formatText(
                incident.product_name ||
                  incident.company_name ||
                  incident.product_category ||
                  INCIDENT_TYPE_LABELS[incident.incident_type],
              )}
            </h2>
            <p className={`mt-1 ${detailMetaClassName}`}>
              First discovered {formatDate(incident.first_discovered_at)}
            </p>
          </div>
          <IncidentStatusBadge status={incident.verification_status} />
        </div>
      </div>

      <section
        className="rounded-xl border border-slate-200 bg-slate-50 p-4"
        aria-labelledby="incident-confidence-heading"
      >
        <h3
          id="incident-confidence-heading"
          className="mb-3 font-semibold text-slate-950"
        >
          Confidence assessment
        </h3>
        <IncidentConfidence score={incident.confidence_score} />
        {confidenceReasons.length ? (
          <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {confidenceReasons.map((reason, index) => (
              <li key={`${index}-${reason}`}>{reason}</li>
            ))}
          </ul>
        ) : (
          <p className={`mt-3 ${mutedTextClassName}`}>
            No confidence reasons were provided.
          </p>
        )}
      </section>

      <dl className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
        <div>
          <dt className={detailLabelClassName}>Company</dt>
          <dd className={detailValueClassName}>
            {formatText(incident.company_name)}
          </dd>
        </div>
        <div>
          <dt className={detailLabelClassName}>Product category</dt>
          <dd className={detailValueClassName}>
            {formatText(incident.product_category)}
          </dd>
        </div>
        <div>
          <dt className={detailLabelClassName}>Hazard</dt>
          <dd className={detailValueClassName}>
            {formatText(incident.hazard_type)}
          </dd>
        </div>
        <div>
          <dt className={detailLabelClassName}>Country / regions</dt>
          <dd className={detailValueClassName}>
            {[incident.country, ...(incident.affected_regions ?? [])]
              .filter(Boolean)
              .join(", ") || "Not available"}
          </dd>
        </div>
        <div>
          <dt className={detailLabelClassName}>Publication date</dt>
          <dd className={detailValueClassName}>
            {formatDate(incident.publication_date)}
          </dd>
        </div>
        <div>
          <dt className={detailLabelClassName}>Last discovered</dt>
          <dd className={detailValueClassName}>
            {formatDate(incident.last_discovered_at)}
          </dd>
        </div>
        <div>
          <dt className={detailLabelClassName}>Source kind</dt>
          <dd className={detailValueClassName}>
            {sourceKindLabel(incident.source_kind)}
          </dd>
        </div>
        <div>
          <dt className={detailLabelClassName}>Publisher</dt>
          <dd className={detailValueClassName}>
            {formatText(
              incident.primary_publisher ||
                incident.primary_source_domain,
            )}
          </dd>
        </div>
      </dl>

      <section aria-labelledby="incident-summary-heading">
        <h3
          id="incident-summary-heading"
          className={detailLabelClassName}
        >
          Summary
        </h3>
        <p className={detailValueClassName}>{formatText(incident.summary)}</p>
      </section>

      <section aria-labelledby="incident-reason-heading">
        <h3 id="incident-reason-heading" className={detailLabelClassName}>
          Incident reason
        </h3>
        <p className={detailValueClassName}>
          {formatText(incident.incident_reason)}
        </p>
      </section>

      <section aria-labelledby="incident-guidance-heading">
        <h3 id="incident-guidance-heading" className={detailLabelClassName}>
          Consumer guidance
        </h3>
        <p className={detailValueClassName}>
          {formatText(incident.consumer_guidance)}
        </p>
      </section>

      <div>
        {hasReportedSource ? (
          <a
            href={incident.primary_source_url}
            target="_blank"
            rel="noopener noreferrer"
            className={sourceLinkClassName}
          >
            Reported source
          </a>
        ) : (
          <p className={mutedTextClassName}>Reported source not provided.</p>
        )}
      </div>

      <section aria-labelledby="incident-evidence-heading">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h3
            id="incident-evidence-heading"
            className="text-lg font-semibold text-slate-950"
          >
            Evidence
          </h3>
          <span className={mutedTextClassName}>
            {evidence.length} {evidence.length === 1 ? "source" : "sources"}
          </span>
        </div>
        {evidence.length ? (
          <ul className="space-y-3">
            {evidence.map((item, index) => (
              <EvidenceItem
                key={`${item.url}-${index}`}
                evidence={item}
                index={index}
              />
            ))}
          </ul>
        ) : (
          <p className={mutedTextClassName}>No evidence records provided.</p>
        )}
      </section>

      {linkedOfficialAlerts.length ? (
        <section aria-labelledby="linked-recalls-heading">
          <h3
            id="linked-recalls-heading"
            className="mb-3 text-lg font-semibold text-slate-950"
          >
            Linked official recalls
          </h3>
          <ul className="flex flex-wrap gap-2">
            {linkedOfficialAlerts.map((alertId) => (
              <li key={alertId}>
                <Link
                  href={`/alerts/${encodeURIComponent(alertId)}`}
                  className="inline-flex rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-900 hover:bg-emerald-100"
                >
                  View official recall {alertId}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {incident.processing_errors?.length ? (
        <section
          className="rounded-lg border border-amber-300 bg-amber-50 p-4"
          aria-labelledby="processing-notes-heading"
        >
          <h3
            id="processing-notes-heading"
            className="font-semibold text-amber-950"
          >
            Processing notes
          </h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-950">
            {incident.processing_errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
