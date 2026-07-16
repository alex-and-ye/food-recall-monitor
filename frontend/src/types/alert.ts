export type RiskLevel = "High" | "Medium" | "Low";

export type CountrySource = "UK" | "Germany" | "France";

export const RISK_LEVELS = ["High", "Medium", "Low"] as const satisfies readonly RiskLevel[];

export const COUNTRY_SOURCES = ["UK", "Germany", "France"] as const satisfies readonly CountrySource[];

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
