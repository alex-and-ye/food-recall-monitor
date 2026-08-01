/**
 * Colored badge displaying an early-warning incident verification status.
 */

import {
  INCIDENT_STATUS_LABELS,
  type IncidentStatus,
} from "@/types/incident";

/** Border/background/text classes keyed by verification status. */
const statusClassNames: Record<IncidentStatus, string> = {
  pending: "border-amber-300 bg-amber-50 text-amber-900",
  corroborated: "border-sky-300 bg-sky-50 text-sky-900",
  officially_confirmed: "border-emerald-300 bg-emerald-50 text-emerald-900",
  dismissed: "border-slate-300 bg-slate-100 text-slate-700",
  superseded: "border-violet-300 bg-violet-50 text-violet-900",
};

/**
 * Renders a pill badge for an incident verification status.
 *
 * @param props.status - Verification status to display.
 * @returns Status badge element.
 */
export default function IncidentStatusBadge({
  status,
}: {
  status: IncidentStatus;
}) {
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClassNames[status]}`}
    >
      {INCIDENT_STATUS_LABELS[status]}
    </span>
  );
}
