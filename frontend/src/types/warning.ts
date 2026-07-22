export const WARNING_CATEGORIES = [
  "source_skipped",
  "record_skipped",
  "pipeline_failed",
  "early_warning_search_failed",
  "early_warning_fetch_failed",
  "early_warning_record_skipped",
  "early_warning_pipeline_failed",
] as const;

export type PipelineWarningCategory = (typeof WARNING_CATEGORIES)[number];

export interface PipelineWarning {
  warning_id: string;
  created_at: string;
  category: PipelineWarningCategory;
  message: string;
  source: string | null;
  acknowledged: boolean;
  run_id: string | null;
}

export interface PipelineWarningsSummary {
  unacknowledged_count: number;
}

export const WARNING_CATEGORY_LABELS: Record<PipelineWarningCategory, string> = {
  source_skipped: "Source skipped",
  record_skipped: "Product skipped",
  pipeline_failed: "Pipeline failed",
  early_warning_search_failed: "Discovery search failed",
  early_warning_fetch_failed: "Early-warning page fetch failed",
  early_warning_record_skipped: "Early-warning record skipped",
  early_warning_pipeline_failed: "Early-warning pipeline failed",
};
