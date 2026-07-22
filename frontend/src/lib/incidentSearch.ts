import type { ReadonlyURLSearchParams } from "next/navigation";
import {
  isIncidentSortBy,
  isIncidentSourceKind,
  isIncidentStatus,
  isIncidentType,
  type IncidentSortBy,
  type IncidentSourceKind,
  type IncidentStatus,
  type IncidentType,
} from "@/types/incident";

export interface IncidentSearchFormState {
  search: string;
  status: IncidentStatus | "All";
  incidentType: IncidentType | "All";
  confidenceMin: string;
  country: string;
  sourceKind: IncidentSourceKind | "All";
  date: string;
  sortBy: IncidentSortBy | "";
}

export interface IncidentSearchPayload {
  search: string | null;
  verification_status: IncidentStatus | null;
  incident_type: IncidentType | null;
  minimum_confidence: number | null;
  country: string | null;
  source_kind: IncidentSourceKind | null;
  publication_date: string | null;
  sort_by: IncidentSortBy | null;
}

export const DEFAULT_INCIDENT_SEARCH_FORM_STATE: IncidentSearchFormState = {
  search: "",
  status: "All",
  incidentType: "All",
  confidenceMin: "",
  country: "",
  sourceKind: "All",
  date: "",
  sortBy: "",
};

function parseConfidence(value: string | null | undefined): string {
  if (!value?.trim()) {
    return "";
  }

  const numericValue = Number(value);
  if (!Number.isFinite(numericValue) || numericValue < 0 || numericValue > 100) {
    return "";
  }

  return String(numericValue);
}

export function buildIncidentSearchPayload(
  state: IncidentSearchFormState,
): IncidentSearchPayload {
  const confidence = parseConfidence(state.confidenceMin);

  return {
    search: state.search.trim() || null,
    verification_status: state.status === "All" ? null : state.status,
    incident_type: state.incidentType === "All" ? null : state.incidentType,
    minimum_confidence: confidence === "" ? null : Number(confidence),
    country: state.country.trim() || null,
    source_kind: state.sourceKind === "All" ? null : state.sourceKind,
    publication_date: state.date.trim() || null,
    sort_by: isIncidentSortBy(state.sortBy) ? state.sortBy : null,
  };
}

export function hasActiveIncidentFilters(
  state: IncidentSearchFormState,
): boolean {
  return (
    state.search.trim().length > 0 ||
    state.status !== "All" ||
    state.incidentType !== "All" ||
    state.confidenceMin !== "" ||
    state.country.trim().length > 0 ||
    state.sourceKind !== "All" ||
    state.date.trim().length > 0 ||
    state.sortBy !== ""
  );
}

export function incidentFormStateFromSearchParams(
  searchParams: ReadonlyURLSearchParams,
): IncidentSearchFormState {
  const status = searchParams.get("verification_status");
  const incidentType = searchParams.get("incident_type");
  const sourceKind = searchParams.get("source_kind");
  const sortBy = searchParams.get("sort_by");
  const date = searchParams.get("publication_date") ?? "";

  return {
    search: searchParams.get("search") ?? "",
    status: isIncidentStatus(status) ? status : "All",
    incidentType: isIncidentType(incidentType) ? incidentType : "All",
    confidenceMin: parseConfidence(searchParams.get("minimum_confidence")),
    country: searchParams.get("country") ?? "",
    sourceKind: isIncidentSourceKind(sourceKind) ? sourceKind : "All",
    date: /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : "",
    sortBy: isIncidentSortBy(sortBy) ? sortBy : "",
  };
}

export function incidentSearchParamsFromFormState(
  state: IncidentSearchFormState,
): URLSearchParams {
  const payload = buildIncidentSearchPayload(state);
  const params = new URLSearchParams();

  if (payload.search) params.set("search", payload.search);
  if (payload.verification_status) {
    params.set("verification_status", payload.verification_status);
  }
  if (payload.incident_type) params.set("incident_type", payload.incident_type);
  if (payload.minimum_confidence !== null) {
    params.set("minimum_confidence", String(payload.minimum_confidence));
  }
  if (payload.country) params.set("country", payload.country);
  if (payload.source_kind) params.set("source_kind", payload.source_kind);
  if (payload.publication_date) {
    params.set("publication_date", payload.publication_date);
  }
  if (payload.sort_by) params.set("sort_by", payload.sort_by);

  return params;
}

export function incidentFetchParamsFromSearchParams(
  searchParams: ReadonlyURLSearchParams,
): Record<string, string | undefined> {
  const payload = buildIncidentSearchPayload(
    incidentFormStateFromSearchParams(searchParams),
  );

  return {
    search: payload.search ?? undefined,
    verification_status: payload.verification_status ?? undefined,
    incident_type: payload.incident_type ?? undefined,
    minimum_confidence:
      payload.minimum_confidence === null
        ? undefined
        : String(payload.minimum_confidence),
    country: payload.country ?? undefined,
    source_kind: payload.source_kind ?? undefined,
    publication_date: payload.publication_date ?? undefined,
    sort_by: payload.sort_by ?? undefined,
  };
}

export function hasActiveIncidentUrlFilters(
  searchParams: ReadonlyURLSearchParams,
): boolean {
  return hasActiveIncidentFilters(
    incidentFormStateFromSearchParams(searchParams),
  );
}
