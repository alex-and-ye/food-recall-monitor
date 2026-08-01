/**
 * Browser-facing HTTP client for Food Recall Monitor REST endpoints.
 *
 * Calls go through `NEXT_PUBLIC_API_URL` (typically `/api`), which Next.js
 * rewrites or proxies to the FastAPI backend.
 */

import type { FoodRecallAlert, FoodRecallAlertStats, FoodRecallAlertsVersion } from "@/types/alert";
import type {
  EarlyWarningIncident,
  IncidentsVersion,
  IncidentStatusCounts,
} from "@/types/incident";
import type { PipelineWarning, PipelineWarningsSummary } from "@/types/warning";
import { ApiError } from "@/services/api/errors";

export { ApiError } from "@/services/api/errors";

/** Browser API base path or absolute URL (defaults to `/api`). */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

/**
 * Returns the configured browser-facing API base URL.
 *
 * @returns Value of `NEXT_PUBLIC_API_URL`, or `/api`.
 */
export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

/**
 * Returns the SSE endpoint URL for official alert change events.
 *
 * @returns Absolute or root-relative URL for the alerts event stream.
 */
export function getAlertsEventsUrl(): string {
  return `${API_BASE_URL}/stream/alerts`;
}

/**
 * Returns the SSE endpoint URL for early-warning incident change events.
 *
 * @returns Absolute or root-relative URL for the incidents event stream.
 */
export function getIncidentsEventsUrl(): string {
  return `${API_BASE_URL}/stream/incidents`;
}

/** Response structure for official food recall alerts. */
interface AlertsResponse {
  alerts: FoodRecallAlert[];
}

/** Response structure for early-warning incidents. */
interface IncidentsResponse {
  incidents: EarlyWarningIncident[];
}

/** Parameters for fetching official food recall alerts. */
export interface GetAlertsParams {
  search?: string;
  risk_level?: string;
  country_source?: string;
  recall_date?: string;
  sort_by?: string;
}

/** Parameters for fetching early-warning incidents. */
export interface GetIncidentsParams {
  search?: string;
  verification_status?: string;
  incident_type?: string;
  minimum_confidence?: string;
  country?: string;
  source_kind?: string;
  publication_date?: string;
  sort_by?: string;
}

/**
 * Performs a JSON API request and throws {@link ApiError} on non-OK responses.
 *
 * @typeParam T - Expected JSON response body type.
 * @param path - Path under the API base, including a leading slash.
 * @param init - Optional `fetch` init (method, headers, body, etc.).
 * @returns Parsed JSON body.
 * @throws {ApiError} When the response status is not OK.
 */
async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // Response body is not JSON; keep statusText.
    }
    throw new ApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

/**
 * Builds a query string from optional string params, omitting empty values.
 *
 * @param params - Map of query keys to optional string values.
 * @returns `?key=value&...` or an empty string when nothing is set.
 */
function buildQueryString(
  params: Record<string, string | undefined>,
): string {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value.trim() !== "") {
      searchParams.set(key, value.trim());
    }
  }

  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

/**
 * Fetches official food recall alerts, optionally filtered and sorted.
 *
 * @param params - Optional list filters and sort.
 * @returns Array of alerts from the API.
 */
export async function getAlerts(
  params: GetAlertsParams = {},
): Promise<FoodRecallAlert[]> {
  const query = buildQueryString({
    search: params.search,
    risk_level: params.risk_level,
    country_source: params.country_source,
    recall_date: params.recall_date,
    sort_by: params.sort_by,
  });
  const data = await apiFetch<AlertsResponse>(`/alerts${query}`);
  return data.alerts;
}

/**
 * Fetches aggregate statistics for official food recall alerts.
 *
 * @returns Stats payload including totals and top-N breakdowns.
 */
export async function getAlertStats(): Promise<FoodRecallAlertStats> {
  return apiFetch<FoodRecallAlertStats>("/alerts/stats");
}

/**
 * Fetches a lightweight version fingerprint for the alerts collection.
 *
 * @returns Count and content fingerprint for change detection.
 */
export async function getAlertsVersion(): Promise<FoodRecallAlertsVersion> {
  return apiFetch<FoodRecallAlertsVersion>("/alerts/version");
}

/**
 * Fetches a single official food recall alert by ID.
 *
 * @param id - Alert identifier.
 * @returns The matching alert.
 */
export async function getAlertById(id: string): Promise<FoodRecallAlert> {
  return apiFetch<FoodRecallAlert>(`/alerts/${encodeURIComponent(id)}`);
}

/**
 * Fetches early-warning incidents, optionally filtered and sorted.
 *
 * @param params - Optional list filters and sort.
 * @returns Array of incidents (supports both wrapped and raw array responses).
 */
export async function getIncidents(
  params: GetIncidentsParams = {},
): Promise<EarlyWarningIncident[]> {
  const query = buildQueryString({
    search: params.search,
    verification_status: params.verification_status,
    incident_type: params.incident_type,
    minimum_confidence: params.minimum_confidence,
    country: params.country,
    source_kind: params.source_kind,
    publication_date: params.publication_date,
    sort_by: params.sort_by,
  });
  const data = await apiFetch<IncidentsResponse | EarlyWarningIncident[]>(
    `/incidents${query}`,
  );
  return Array.isArray(data) ? data : data.incidents;
}

/**
 * Fetches a single early-warning incident by ID.
 *
 * @param id - Incident identifier.
 * @returns The matching incident.
 */
export async function getIncidentById(
  id: string,
): Promise<EarlyWarningIncident> {
  return apiFetch<EarlyWarningIncident>(
    `/incidents/${encodeURIComponent(id)}`,
  );
}

/**
 * Fetches counts of incidents grouped by verification status.
 *
 * @returns Status count breakdown.
 */
export async function getIncidentStatusCounts(): Promise<IncidentStatusCounts> {
  return apiFetch<IncidentStatusCounts>("/incidents/stats");
}

/**
 * Fetches a lightweight version fingerprint for the incidents collection.
 *
 * @returns Count and content fingerprint for change detection.
 */
export async function getIncidentsVersion(): Promise<IncidentsVersion> {
  return apiFetch<IncidentsVersion>("/incidents/version");
}

/**
 * Fetches pipeline warning records.
 *
 * @param params - Optional filter for acknowledged state.
 * @returns Array of pipeline warnings.
 */
export async function getWarnings(
  params: { acknowledged?: boolean } = {},
): Promise<PipelineWarning[]> {
  const query = buildQueryString({
    acknowledged:
      params.acknowledged === undefined ? undefined : String(params.acknowledged),
  });
  return apiFetch<PipelineWarning[]>(`/warnings${query}`);
}

/**
 * Fetches a summary of unacknowledged pipeline warnings.
 *
 * @returns Object containing `unacknowledged_count`.
 */
export async function getWarningsSummary(): Promise<PipelineWarningsSummary> {
  return apiFetch<PipelineWarningsSummary>("/warnings/summary");
}

/**
 * Acknowledges a single pipeline warning.
 *
 * @param warningId - Warning identifier.
 * @returns Updated warning record.
 */
export async function acknowledgeWarning(
  warningId: string,
): Promise<PipelineWarning> {
  return apiFetch<PipelineWarning>(
    `/warnings/${encodeURIComponent(warningId)}/acknowledge`,
    { method: "POST" },
  );
}

/**
 * Acknowledges all currently unacknowledged pipeline warnings.
 *
 * @returns Object containing how many warnings were acknowledged.
 */
export async function acknowledgeAllWarnings(): Promise<{
  acknowledged_count: number;
}> {
  return apiFetch<{ acknowledged_count: number }>("/warnings/acknowledge-all", {
    method: "POST",
  });
}
