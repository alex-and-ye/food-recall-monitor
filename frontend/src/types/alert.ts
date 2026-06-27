export type RiskLevel = "High" | "Medium" | "Low";

export interface FoodRecallAlert {
  alert_id: string;
  product_name: string;
  product_category: string;
  risk_level: RiskLevel;
  recall_reason: string;
  hazard_type: string;
  summary: string;
  consumer_action: string;
  affected_regions: string[];
  recall_date: string;
  source_url: string;
}

export interface FoodRecallAlertStats {
  total_alerts: number;
  top_5_hazard_types: [string, number][];
  top_5_product_categories: [string, number][];
  top_5_affected_regions: [string, number][];
  alerts_last_7_days: number;
  alerts_last_30_days: number;
}
