import type { FoodRecallAlert, FoodRecallAlertStats, FoodRecallAlertsVersion } from "@/types/alert";
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
  return `${API_BASE_URL}/alerts/events`;
}

// TODO: Remove this before final project delivery
export function isMockDataMode(): boolean {
  return process.env.NEXT_PUBLIC_USE_MOCK_DATA === "true";
}

// TODO: Remove this before final project delivery
function useMockData(): boolean {
  return isMockDataMode();
}

interface AlertsResponse {
  alerts: FoodRecallAlert[];
}

export interface GetAlertsParams {
  search?: string;
  risk_level?: string;
  country_source?: string;
  recall_date?: string;
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
  if (useMockData()) {
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
  if (useMockData()) {
    return fetchMockStats();
  }

  return apiFetch<FoodRecallAlertStats>("/alerts/stats");
}

export async function getAlertsVersion(): Promise<FoodRecallAlertsVersion> {
  // TODO: Remove this before final project delivery
  if (useMockData()) {
    return fetchMockAlertsVersion();
  }

  return apiFetch<FoodRecallAlertsVersion>("/alerts/version");
}

export async function getAlertById(id: string): Promise<FoodRecallAlert> {
  // TODO: Remove this before final project delivery
  if (useMockData()) {
    return fetchMockAlertById(id);
  }

  return apiFetch<FoodRecallAlert>(`/alerts/${encodeURIComponent(id)}`);
}
