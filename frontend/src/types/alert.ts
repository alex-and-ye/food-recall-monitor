export type RiskLevel = "High" | "Medium" | "Low" | "Unknown";

export type CountrySource = "UK" | "Germany" | "France";

export type SortBy = "latest" | "oldest";

export type WebSourceKey = "uk" | "germany" | "france";

export const RISK_LEVELS = [
  "High",
  "Medium",
  "Low",
  "Unknown",
] as const satisfies readonly RiskLevel[];

export const COUNTRY_SOURCES = [
  "UK",
  "Germany",
  "France",
] as const satisfies readonly CountrySource[];

export const SORT_BY_LATEST = "latest" as const satisfies SortBy;
export const SORT_BY_OLDEST = "oldest" as const satisfies SortBy;
export const SORT_BY_OPTIONS = [
  SORT_BY_LATEST,
  SORT_BY_OLDEST,
] as const satisfies readonly SortBy[];

export const WEB_SOURCE_UK = "uk" as const satisfies WebSourceKey;
export const WEB_SOURCE_GERMANY = "germany" as const satisfies WebSourceKey;
export const WEB_SOURCE_FRANCE = "france" as const satisfies WebSourceKey;

export const WEB_SOURCE_TO_COUNTRY_SOURCE = {
  [WEB_SOURCE_UK]: "UK",
  [WEB_SOURCE_GERMANY]: "Germany",
  [WEB_SOURCE_FRANCE]: "France",
} as const satisfies Record<WebSourceKey, CountrySource>;

export const WEB_SOURCE_KEYS = [
  WEB_SOURCE_UK,
  WEB_SOURCE_GERMANY,
  WEB_SOURCE_FRANCE,
] as const satisfies readonly WebSourceKey[];

export function isRiskLevel(value: string | null | undefined): value is RiskLevel {
  return RISK_LEVELS.includes(value as RiskLevel);
}

export function isCountrySource(
  value: string | null | undefined,
): value is CountrySource {
  return COUNTRY_SOURCES.includes(value as CountrySource);
}

export function isSortBy(value: string | null | undefined): value is SortBy {
  return SORT_BY_OPTIONS.includes(value as SortBy);
}

export interface FoodRecallAlert {
  alert_id: string;
  web_source: string;
  country_source: CountrySource;
  product_name: string;
  product_category: string;
  risk_level: RiskLevel;
  recall_reason: string;
  hazard_type: string;
  summary: string;
  consumer_action: string;
  batch_id: string;
  affected_regions: string[];
  recall_date: string;
  source_url: string;
  latitude: number;
  longitude: number;
}

export interface FoodRecallAlertStats {
  total_alerts: number;
  top_5_hazard_types: [string, number][];
  top_5_product_categories: [string, number][];
  top_5_affected_regions: [string, number][];
  alerts_last_7_days: number;
  alerts_last_30_days: number;
}

export interface FoodRecallAlertsVersion {
  count: number;
  fingerprint: string;
}
