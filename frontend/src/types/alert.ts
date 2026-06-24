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
