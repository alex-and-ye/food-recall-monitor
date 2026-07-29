import type { FoodRecallAlert, FoodRecallAlertStats, FoodRecallAlertsVersion } from "@/types/alert";
import type {
  EarlyWarningIncident,
  IncidentsVersion,
  IncidentStatusCounts,
} from "@/types/incident";
import type { PipelineWarning, PipelineWarningsSummary } from "@/types/warning";
import { ApiError } from "@/services/api/errors";
// TODO: Remove this before final project delivery
import {
  fetchMockAlertById,
  fetchMockAlerts,
  fetchMockAlertsVersion,
  fetchMockStats,
} from "@/services/mockData";

export { ApiError } from "@/services/api/errors";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

export function getAlertsEventsUrl(): string {
  return `${API_BASE_URL}/stream/alerts`;
}

export function getIncidentsEventsUrl(): string {
  return `${API_BASE_URL}/stream/incidents`;
}

// TODO: Remove this before final project delivery
export function isMockDataMode(): boolean {
  return process.env.NEXT_PUBLIC_USE_MOCK_DATA === "true";
}

// TODO: Remove this before final project delivery
function shouldUseMockData(): boolean {
  return isMockDataMode();
}

interface AlertsResponse {
  alerts: FoodRecallAlert[];
}

interface IncidentsResponse {
  incidents: EarlyWarningIncident[];
}

export interface GetAlertsParams {
  search?: string;
  risk_level?: string;
  country_source?: string;
  recall_date?: string;
  sort_by?: string;
}

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

export async function getAlerts(
  params: GetAlertsParams = {},
): Promise<FoodRecallAlert[]> {
  // TODO: Remove this before final project delivery
  if (shouldUseMockData()) {
    return fetchMockAlerts(params);
  }

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

export async function getAlertStats(): Promise<FoodRecallAlertStats> {
  // TODO: Remove this before final project delivery
  if (shouldUseMockData()) {
    return fetchMockStats();
  }

  return apiFetch<FoodRecallAlertStats>("/alerts/stats");
}

export async function getAlertsVersion(): Promise<FoodRecallAlertsVersion> {
  // TODO: Remove this before final project delivery
  if (shouldUseMockData()) {
    return fetchMockAlertsVersion();
  }

  return apiFetch<FoodRecallAlertsVersion>("/alerts/version");
}

export async function getAlertById(id: string): Promise<FoodRecallAlert> {
  // TODO: Remove this before final project delivery
  if (shouldUseMockData()) {
    return fetchMockAlertById(id);
  }

  return apiFetch<FoodRecallAlert>(`/alerts/${encodeURIComponent(id)}`);
}

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

export async function getIncidentById(
  id: string,
): Promise<EarlyWarningIncident> {
  return apiFetch<EarlyWarningIncident>(
    `/incidents/${encodeURIComponent(id)}`,
  );
}

export async function getIncidentStatusCounts(): Promise<IncidentStatusCounts> {
  return apiFetch<IncidentStatusCounts>("/incidents/stats");
}

export async function getIncidentsVersion(): Promise<IncidentsVersion> {
  return apiFetch<IncidentsVersion>("/incidents/version");
}

export async function getWarnings(
  params: { acknowledged?: boolean } = {},
): Promise<PipelineWarning[]> {
  const query = buildQueryString({
    acknowledged:
      params.acknowledged === undefined ? undefined : String(params.acknowledged),
  });
  return apiFetch<PipelineWarning[]>(`/warnings${query}`);
}

export async function getWarningsSummary(): Promise<PipelineWarningsSummary> {
  return apiFetch<PipelineWarningsSummary>("/warnings/summary");
}

export async function acknowledgeWarning(
  warningId: string,
): Promise<PipelineWarning> {
  return apiFetch<PipelineWarning>(
    `/warnings/${encodeURIComponent(warningId)}/acknowledge`,
    { method: "POST" },
  );
}

export async function acknowledgeAllWarnings(): Promise<{
  acknowledged_count: number;
}> {
  return apiFetch<{ acknowledged_count: number }>("/warnings/acknowledge-all", {
    method: "POST",
  });
}
