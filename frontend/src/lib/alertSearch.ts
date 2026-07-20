import type { ReadonlyURLSearchParams } from "next/navigation";
import type { CountrySource, FoodRecallAlert, RiskLevel, SortBy } from "@/types/alert";
import {
  isCountrySource,
  isRiskLevel,
  isSortBy,
  SORT_BY_LATEST,
  SORT_BY_OLDEST,
} from "@/types/alert";

export type RiskLevelFilter = RiskLevel | "All";

export type CountrySourceFilter = CountrySource | "All";

export type SortByFilter = "" | SortBy;

export interface AlertSearchFormState {
  search: string;
  riskLevel: RiskLevelFilter;
  countrySource: CountrySourceFilter;
  sortBy: SortByFilter;
  recallDate: string;
}

export interface AlertSearchPayload {
  search: string;
  risk_level: RiskLevel | null;
  country_source: CountrySource | null;
  recall_date: string | null;
  sort_by: SortBy | null;
}

export const DEFAULT_ALERT_SEARCH_FORM_STATE: AlertSearchFormState = {
  search: "",
  riskLevel: "All",
  countrySource: "All",
  sortBy: "",
  recallDate: "",
};

export function buildAlertSearchPayload(
  state: AlertSearchFormState,
): AlertSearchPayload {
  return {
    search: state.search,
    risk_level: state.riskLevel === "All" ? null : state.riskLevel,
    country_source: state.countrySource === "All" ? null : state.countrySource,
    recall_date: state.recallDate.trim() || null,
    sort_by: isSortBy(state.sortBy) ? state.sortBy : null,
  };
}

export function hasActiveFilters(state: AlertSearchFormState): boolean {
  return (
    state.search.trim().length > 0 ||
    state.riskLevel !== "All" ||
    state.countrySource !== "All" ||
    state.sortBy !== "" ||
    state.recallDate.trim().length > 0
  );
}

export function formStateFromSearchParams(
  searchParams: ReadonlyURLSearchParams,
): AlertSearchFormState {
  const riskLevel = searchParams.get("risk_level");
  const countrySource = searchParams.get("country_source");
  const sortBy = searchParams.get("sort_by");
  const recallDate = searchParams.get("recall_date") ?? "";

  return {
    search: searchParams.get("search") ?? "",
    riskLevel: isRiskLevel(riskLevel) ? riskLevel : "All",
    countrySource: isCountrySource(countrySource) ? countrySource : "All",
    sortBy: isSortBy(sortBy) ? sortBy : "",
    recallDate: /^\d{4}-\d{2}-\d{2}$/.test(recallDate) ? recallDate : "",
  };
}

export function searchParamsFromFormState(
  state: AlertSearchFormState,
): URLSearchParams {
  const params = new URLSearchParams();

  const search = state.search.trim();
  if (search) {
    params.set("search", search);
  }
  if (state.riskLevel !== "All") {
    params.set("risk_level", state.riskLevel);
  }
  if (state.countrySource !== "All") {
    params.set("country_source", state.countrySource);
  }
  if (state.sortBy !== "") {
    params.set("sort_by", state.sortBy);
  }
  if (state.recallDate.trim()) {
    params.set("recall_date", state.recallDate.trim());
  }

  return params;
}

export function hasActiveUrlFilters(
  searchParams: ReadonlyURLSearchParams,
): boolean {
  return hasActiveFilters(formStateFromSearchParams(searchParams));
}

export function alertFetchParamsFromSearchParams(
  searchParams: ReadonlyURLSearchParams,
): {
  search?: string;
  risk_level?: string;
  country_source?: string;
  recall_date?: string;
  sort_by?: string;
} {
  const formState = formStateFromSearchParams(searchParams);
  const payload = buildAlertSearchPayload(formState);

  return {
    search: payload.search.trim() || undefined,
    risk_level: payload.risk_level ?? undefined,
    country_source: payload.country_source ?? undefined,
    recall_date: payload.recall_date ?? undefined,
    sort_by: payload.sort_by ?? undefined,
  };
}

// TODO: Remove this before final project delivery
function compareRecallDates(
  left: FoodRecallAlert,
  right: FoodRecallAlert,
): number {
  return left.recall_date.localeCompare(right.recall_date);
}

// TODO: Remove this before final project delivery
export function filterAlerts(
  alerts: FoodRecallAlert[],
  payload: AlertSearchPayload,
): FoodRecallAlert[] {
  const searchTerm = payload.search.trim().toLowerCase();

  const filtered = alerts.filter((alert) => {
    if (payload.risk_level && alert.risk_level !== payload.risk_level) {
      return false;
    }

    if (
      payload.country_source &&
      alert.country_source !== payload.country_source
    ) {
      return false;
    }

    if (payload.recall_date && alert.recall_date !== payload.recall_date) {
      return false;
    }

    if (!searchTerm) {
      return true;
    }

    const searchableText = [
      alert.product_name,
      alert.product_category,
      alert.batch_id,
      alert.recall_reason,
      alert.hazard_type,
      alert.summary,
      alert.consumer_action,
      alert.web_source,
      ...alert.affected_regions,
    ]
      .join(" ")
      .toLowerCase();

    return searchableText.includes(searchTerm);
  });

  if (payload.sort_by === SORT_BY_OLDEST) {
    return [...filtered].sort(compareRecallDates);
  }

  if (payload.sort_by === SORT_BY_LATEST) {
    return [...filtered].sort((left, right) =>
      compareRecallDates(right, left),
    );
  }

  return filtered;
}

export function formatResultsCount(count: number): string {
  if (count === 1) {
    return "Showing 1 result";
  }

  return `Showing ${count} results`;
}
