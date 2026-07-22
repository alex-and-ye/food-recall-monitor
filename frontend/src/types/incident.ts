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

export const INCIDENT_STATUSES = [
  "pending",
  "corroborated",
  "officially_confirmed",
  "dismissed",
  "superseded",
] as const;

export type IncidentStatus = (typeof INCIDENT_STATUSES)[number];

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

export type IncidentSourceKind = (typeof INCIDENT_SOURCE_KINDS)[number];

export type IncidentSortBy =
  | "latest"
  | "oldest"
  | "confidence_high"
  | "confidence_low";

export const INCIDENT_SORT_OPTIONS = [
  "latest",
  "oldest",
  "confidence_high",
  "confidence_low",
] as const satisfies readonly IncidentSortBy[];

export const INCIDENT_TYPE_LABELS: Record<IncidentType, string> = {
  official_recall: "Official recall report",
  potential_recall: "Potential recall",
  foodborne_outbreak: "Foodborne outbreak",
  investigation: "Investigation",
  company_withdrawal: "Company withdrawal",
  public_health_warning: "Public health warning",
  food_safety_advisory: "Food safety advisory",
};

export const INCIDENT_STATUS_LABELS: Record<IncidentStatus, string> = {
  pending: "Pending verification",
  corroborated: "Corroborated",
  officially_confirmed: "Officially confirmed",
  dismissed: "Dismissed",
  superseded: "Superseded",
};

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

export interface IncidentStatusCounts {
  pending: number;
  corroborated: number;
  officially_confirmed: number;
  dismissed: number;
  superseded: number;
}

export interface IncidentsVersion {
  count: number;
  fingerprint: string;
}

export function isIncidentType(
  value: string | null | undefined,
): value is IncidentType {
  return INCIDENT_TYPES.includes(value as IncidentType);
}

export function isIncidentStatus(
  value: string | null | undefined,
): value is IncidentStatus {
  return INCIDENT_STATUSES.includes(value as IncidentStatus);
}

export function isIncidentSourceKind(
  value: string | null | undefined,
): value is IncidentSourceKind {
  return INCIDENT_SOURCE_KINDS.includes(value as IncidentSourceKind);
}

export function isIncidentSortBy(
  value: string | null | undefined,
): value is IncidentSortBy {
  return INCIDENT_SORT_OPTIONS.includes(value as IncidentSortBy);
}
