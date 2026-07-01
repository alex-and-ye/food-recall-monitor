import type { CountrySource, FoodRecallAlert, RiskLevel } from "@/types/alert";

export type RiskLevelFilter = RiskLevel | "All";

export type CountrySourceFilter = CountrySource | "All";

export interface AlertSearchFormState {
  search: string;
  riskLevel: RiskLevelFilter;
  countrySource: CountrySourceFilter;
}

export interface AlertSearchPayload {
  search: string;
  risk_level: RiskLevel | null;
  country_source: CountrySource | null;
}

export const DEFAULT_ALERT_SEARCH_FORM_STATE: AlertSearchFormState = {
  search: "",
  riskLevel: "All",
  countrySource: "All",
};

export function buildAlertSearchPayload(
  state: AlertSearchFormState,
): AlertSearchPayload {
  return {
    search: state.search,
    risk_level: state.riskLevel === "All" ? null : state.riskLevel,
    country_source: state.countrySource === "All" ? null : state.countrySource,
  };
}

export function hasActiveFilters(state: AlertSearchFormState): boolean {
  return (
    state.search.trim().length > 0 ||
    state.riskLevel !== "All" ||
    state.countrySource !== "All"
  );
}

export function filterAlerts(
  alerts: FoodRecallAlert[],
  payload: AlertSearchPayload,
): FoodRecallAlert[] {
  const searchTerm = payload.search.trim().toLowerCase();

  return alerts.filter((alert) => {
    if (payload.risk_level && alert.risk_level !== payload.risk_level) {
      return false;
    }

    if (
      payload.country_source &&
      alert.country_source !== payload.country_source
    ) {
      return false;
    }

    if (!searchTerm) {
      return true;
    }

    const searchableText = [
      alert.product_name,
      alert.product_category,
      alert.recall_reason,
      alert.hazard_type,
      alert.summary,
      alert.consumer_action,
      alert.batch_id,
      ...alert.affected_regions,
    ]
      .join(" ")
      .toLowerCase();

    return searchableText.includes(searchTerm);
  });
}

export function formatResultsCount(count: number): string {
  if (count === 1) {
    return "Showing 1 result";
  }

  return `Showing ${count} results`;
}
