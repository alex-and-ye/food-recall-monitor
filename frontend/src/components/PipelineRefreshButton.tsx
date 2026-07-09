"use client";

import { useMemo } from "react";
import { usePipelineProgress } from "@/hooks/usePipelineProgress";

function RefreshIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
      <path d="M21 3v6h-6" />
    </svg>
  );
}

function stageLabel(stage: string, message: string): string {
  const normalizedStage = stage.toLowerCase();
  if (normalizedStage === "fetch" || normalizedStage === "source") {
    return "Fetching sources";
  }
  if (normalizedStage === "record" || normalizedStage === "agent") {
    return "Processing recalls";
  }
  if (normalizedStage === "db") {
    return "Saving alerts";
  }
  if (message.toLowerCase().includes("start")) {
    return "Starting refresh";
  }
  if (message.toLowerCase().includes("completed")) {
    return "Refresh complete";
  }
  if (message.toLowerCase().includes("failed")) {
    return "Refresh failed";
  }
  return "Refreshing";
}

export default function PipelineRefreshButton() {
  const {
    progress,
    displayPercent,
    isBusy,
    error,
    startRefresh,
  } = usePipelineProgress();

  const label = useMemo(() => {
    if (progress.status === "failed") {
      return "Failed";
    }
    if (isBusy || progress.status === "completed") {
      return `${displayPercent}%`;
    }
    return "Refresh";
  }, [displayPercent, isBusy, progress.status]);

  const helperText = useMemo(() => {
    if (error) {
      return error;
    }
    if (progress.status === "completed") {
      const count = progress.new_alerts_count ?? 0;
      return count > 0
        ? `Added ${count} new alert${count === 1 ? "" : "s"}`
        : "No new alerts this run";
    }
    if (isBusy) {
      return stageLabel(progress.stage, progress.message);
    }
    return "Run pipeline to fetch latest recalls";
  }, [
    error,
    isBusy,
    progress.message,
    progress.new_alerts_count,
    progress.stage,
    progress.status,
  ]);

  const fillPercent =
    progress.status === "idle" && !isBusy
      ? 0
      : Math.min(100, Math.max(0, displayPercent));

  const isFailed = progress.status === "failed";
  const isComplete = progress.status === "completed";
  const showProgressFill = isBusy || isComplete || isFailed;

  return (
    <div className="flex w-full max-w-xs flex-col items-stretch gap-1.5 sm:max-w-sm">
      <button
        type="button"
        onClick={() => {
          void startRefresh();
        }}
        disabled={isBusy}
        aria-busy={isBusy}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={displayPercent}
        aria-label={
          isBusy
            ? `Pipeline refresh in progress, ${displayPercent} percent`
            : "Refresh food recall alerts"
        }
        className={`group relative h-11 overflow-hidden rounded-xl border text-sm font-semibold tracking-wide shadow-sm transition-[background-color,border-color,box-shadow] duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 focus-visible:ring-offset-2 focus-visible:ring-offset-emerald-600 disabled:cursor-wait ${
          isFailed
            ? "border-rose-200/70 bg-white/10"
            : isComplete
              ? "border-emerald-100/80 bg-white/10"
              : isBusy
                ? "border-white/25 bg-white/10 backdrop-blur-sm"
                : "border-white/25 bg-white/10 backdrop-blur-sm hover:bg-white/15"
        }`}
      >
        {showProgressFill && (
          <>
            <span
              className={`absolute inset-y-0 left-0 transition-[width] duration-200 ease-out ${
                isFailed
                  ? "bg-gradient-to-r from-rose-700 via-rose-600 to-rose-500"
                  : isComplete
                    ? "bg-gradient-to-r from-emerald-800 via-emerald-700 to-teal-600"
                    : "bg-gradient-to-r from-emerald-900 via-emerald-800 to-teal-700"
              }`}
              style={{ width: `${fillPercent}%` }}
            />
            {isBusy && !isComplete && !isFailed && (
              <span
                className="absolute inset-y-0 left-0 animate-pulse bg-gradient-to-r from-transparent via-white/15 to-transparent"
                style={{ width: `${fillPercent}%` }}
              />
            )}
          </>
        )}

        <span className="relative z-10 flex h-full items-center justify-center gap-2 px-4 text-white">
          {!showProgressFill && (
            <RefreshIcon className="h-4 w-4 transition-transform duration-300 group-hover:rotate-45" />
          )}
          <span>{label}</span>
        </span>
      </button>

      <p
        className={`truncate text-center text-xs font-medium ${
          isFailed ? "text-rose-100" : "text-emerald-50/90"
        }`}
        title={helperText}
      >
        {helperText}
      </p>
    </div>
  );
}
