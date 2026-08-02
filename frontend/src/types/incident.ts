/**
 * Domain types, constants, labels, and type guards for early-warning incidents.
 */

/** Canonical incident type values returned by the API. */
export const INCIDENT_TYPES = [
  "official_recall",
  "potential_recall",
  "foodborne_outbreak",
  "investigation",
  "company_withdrawal",
  "public_health_warning",
  "food_safety_advisory",
] as const;

export type IncidentType = (typeof INCIDENT_TYPES)[number];

/** Canonical verification status values returned by the API. */
export const INCIDENT_STATUSES = [
  "pending",
  "corroborated",
  "officially_confirmed",
  "dismissed",
  "superseded",
] as const;

export type IncidentStatus = (typeof INCIDENT_STATUSES)[number];

/** Canonical evidence / primary source kind values. */
export const INCIDENT_SOURCE_KINDS = [
  "official_recall",
  "government_investigation",
  "who_fao",
  "company_release",
  "major_news",
  "trade_publication",
  "unknown",
  "blog",
] as const;

/** Canonical evidence / primary source kind values. */
export type IncidentSourceKind = (typeof INCIDENT_SOURCE_KINDS)[number];

/** Canonical incident list sort options. */
export type IncidentSortBy =
  | "latest"
  | "oldest"
  | "confidence_high"
  | "confidence_low";

/** All valid incident list sort options. */
export const INCIDENT_SORT_OPTIONS = [
  "latest",
  "oldest",
  "confidence_high",
  "confidence_low",
] as const satisfies readonly IncidentSortBy[];

/** Human-readable labels for incident types. */
export const INCIDENT_TYPE_LABELS: Record<IncidentType, string> = {
  official_recall: "Official recall report",
  potential_recall: "Potential recall",
  foodborne_outbreak: "Foodborne outbreak",
  investigation: "Investigation",
  company_withdrawal: "Company withdrawal",
  public_health_warning: "Public health warning",
  food_safety_advisory: "Food safety advisory",
};

/** Human-readable labels for verification statuses. */
export const INCIDENT_STATUS_LABELS: Record<IncidentStatus, string> = {
  pending: "Pending verification",
  corroborated: "Corroborated",
  officially_confirmed: "Officially confirmed",
  dismissed: "Dismissed",
  superseded: "Superseded",
};

/** Human-readable labels for source kinds. */
export const INCIDENT_SOURCE_KIND_LABELS: Record<IncidentSourceKind, string> = {
  official_recall: "Official recall",
  government_investigation: "Government investigation",
  who_fao: "WHO / FAO",
  company_release: "Company release",
  major_news: "Major news",
  trade_publication: "Trade publication",
  unknown: "Unknown source",
  blog: "Blog",
};

/** Evidence / primary source data structure. */
export interface IncidentEvidence {
  url: string;
  title: string;
  publication_date: string | null;
  source_kind: IncidentSourceKind;
  content_hash: string;
  domain: string;
  publisher: string;
  redirected_url_aliases: string[];
}

/** Early-warning incident data structure. */
export interface EarlyWarningIncident {
  incident_id: string;
  incident_type: IncidentType;
  verification_status: IncidentStatus;
  confidence_score: number;
  confidence_reasons: string[];
  product_name: string;
  company_name: string;
  product_category: string;
  hazard_type: string;
  incident_reason: string;
  summary: string;
  consumer_guidance: string;
  country: string;
  affected_regions: string[];
  publication_date: string | null;
  first_discovered_at: string;
  last_discovered_at: string;
  primary_source_url: string;
  primary_source_domain: string;
  primary_publisher: string;
  source_kind: IncidentSourceKind;
  trust_tier: "official" | "high" | "medium" | "low" | "unknown";
  original_language: string;
  evidence: IncidentEvidence[];
  linked_official_alert_ids: string[];
  cluster_fingerprint: string;
  analyst_notes: string;
  status_updated_at: string | null;
  extraction_completeness: number;
  processing_errors: string[];
}

/** Statistics for early-warning incidents. */
export interface IncidentStatusCounts {
  pending: number;
  corroborated: number;
  officially_confirmed: number;
  dismissed: number;
  superseded: number;
}

/** Version information for early-warning incidents. */
export interface IncidentsVersion {
  count: number;
  fingerprint: string;
}

/**
 * Type guard for {@link IncidentType} string values.
 *
 * @param value - Candidate string from URL or API input.
 * @returns `true` if `value` is a known incident type.
 */
export function isIncidentType(
  value: string | null | undefined,
): value is IncidentType {
  return INCIDENT_TYPES.includes(value as IncidentType);
}

/**
 * Type guard for {@link IncidentStatus} string values.
 *
 * @param value - Candidate string from URL or API input.
 * @returns `true` if `value` is a known verification status.
 */
export function isIncidentStatus(
  value: string | null | undefined,
): value is IncidentStatus {
  return INCIDENT_STATUSES.includes(value as IncidentStatus);
}

/**
 * Type guard for {@link IncidentSourceKind} string values.
 *
 * @param value - Candidate string from URL or API input.
 * @returns `true` if `value` is a known source kind.
 */
export function isIncidentSourceKind(
  value: string | null | undefined,
): value is IncidentSourceKind {
  return INCIDENT_SOURCE_KINDS.includes(value as IncidentSourceKind);
}

/**
 * Type guard for {@link IncidentSortBy} string values.
 *
 * @param value - Candidate string from URL or API input.
 * @returns `true` if `value` is a known sort option.
 */
export function isIncidentSortBy(
  value: string | null | undefined,
): value is IncidentSortBy {
  return INCIDENT_SORT_OPTIONS.includes(value as IncidentSortBy);
}
