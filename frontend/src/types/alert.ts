/**
 * Domain types, constants, and type guards for official food recall alerts.
 */

export type RiskLevel = "High" | "Medium" | "Low" | "Unknown";

export type CountrySource = "UK" | "Germany" | "France";

export type SortBy = "latest" | "oldest";

export type WebSourceKey = "uk" | "germany" | "france";

/** Canonical risk level values accepted by the API and UI. */
export const RISK_LEVELS = [
  "High",
  "Medium",
  "Low",
  "Unknown",
] as const satisfies readonly RiskLevel[];

/** Supported official recall country sources. */
export const COUNTRY_SOURCES = [
  "UK",
  "Germany",
  "France",
] as const satisfies readonly CountrySource[];

/** Sort option: newest recalls first. */
export const SORT_BY_LATEST = "latest" as const satisfies SortBy;

/** Sort option: oldest recalls first. */
export const SORT_BY_OLDEST = "oldest" as const satisfies SortBy;

/** All valid alert sort-by values. */
export const SORT_BY_OPTIONS = [
  SORT_BY_LATEST,
  SORT_BY_OLDEST,
] as const satisfies readonly SortBy[];

/** Web scraper key for UK sources. */
export const WEB_SOURCE_UK = "uk" as const satisfies WebSourceKey;

/** Web scraper key for German sources. */
export const WEB_SOURCE_GERMANY = "germany" as const satisfies WebSourceKey;

/** Web scraper key for French sources. */
export const WEB_SOURCE_FRANCE = "france" as const satisfies WebSourceKey;

/** Maps lowercase web-source keys to display country sources. */
export const WEB_SOURCE_TO_COUNTRY_SOURCE = {
  [WEB_SOURCE_UK]: "UK",
  [WEB_SOURCE_GERMANY]: "Germany",
  [WEB_SOURCE_FRANCE]: "France",
} as const satisfies Record<WebSourceKey, CountrySource>;

/** Ordered list of known web-source keys. */
export const WEB_SOURCE_KEYS = [
  WEB_SOURCE_UK,
  WEB_SOURCE_GERMANY,
  WEB_SOURCE_FRANCE,
] as const satisfies readonly WebSourceKey[];

/**
 * Type guard for {@link RiskLevel} string values.
 *
 * @param value - Candidate string from URL or API input.
 * @returns `true` if `value` is a known risk level.
 */
export function isRiskLevel(value: string | null | undefined): value is RiskLevel {
  return RISK_LEVELS.includes(value as RiskLevel);
}

/**
 * Type guard for {@link CountrySource} string values.
 *
 * @param value - Candidate string from URL or API input.
 * @returns `true` if `value` is a known country source.
 */
export function isCountrySource(
  value: string | null | undefined,
): value is CountrySource {
  return COUNTRY_SOURCES.includes(value as CountrySource);
}

/**
 * Type guard for {@link SortBy} string values.
 *
 * @param value - Candidate string from URL or API input.
 * @returns `true` if `value` is a known sort option.
 */
export function isSortBy(value: string | null | undefined): value is SortBy {
  return SORT_BY_OPTIONS.includes(value as SortBy);
}

/** Official food recall alert data structure. */
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

/** Statistics for food recall alerts. */
export interface FoodRecallAlertStats {
  total_alerts: number;
  top_5_hazard_types: [string, number][];
  top_5_product_categories: [string, number][];
  top_5_affected_regions: [string, number][];
  alerts_last_7_days: number;
  alerts_last_30_days: number;
}

/** Version information for food recall alerts. */
export interface FoodRecallAlertsVersion {
  count: number;
  fingerprint: string;
}
