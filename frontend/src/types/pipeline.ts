export type PipelineRunStatus = "idle" | "running" | "completed" | "failed";

export interface PipelineProgress {
  run_id: string | null;
  status: PipelineRunStatus;
  percent: number;
  stage: string;
  message: string;
  sources_total: number;
  sources_completed: number;
  records_total: number | null;
  records_processed: number;
  new_alerts_count: number | null;
  error: string | null;
}

export interface PipelineRunStartResponse {
  run_id: string;
  status: "started" | "already_running";
  message: string;
}

export const IDLE_PIPELINE_PROGRESS: PipelineProgress = {
  run_id: null,
  status: "idle",
  percent: 0,
  stage: "idle",
  message: "Ready",
  sources_total: 0,
  sources_completed: 0,
  records_total: null,
  records_processed: 0,
  new_alerts_count: null,
  error: null,
};
