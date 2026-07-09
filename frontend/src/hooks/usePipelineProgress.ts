"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getPipelineEventsUrl,
  getPipelineProgress,
  isMockDataMode,
  startPipelineRun,
} from "@/services/api/client";
import {
  IDLE_PIPELINE_PROGRESS,
  type PipelineProgress,
} from "@/types/pipeline";

const INITIAL_RETRY_MS = 1_000;
const MAX_RETRY_MS = 30_000;
const SMOOTH_TICK_MS = 50;
const SMOOTH_CATCHUP_FACTOR = 0.18;
const TERMINAL_RESET_MS = 2_800;

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(100, Math.max(0, value));
}

export function usePipelineProgress() {
  const [progress, setProgress] = useState<PipelineProgress>(IDLE_PIPELINE_PROGRESS);
  const [displayPercent, setDisplayPercent] = useState(0);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const targetPercentRef = useRef(0);
  const displayPercentRef = useRef(0);
  const statusRef = useRef<PipelineProgress["status"]>("idle");
  const activeRunIdRef = useRef<string | null>(null);
  const seenTerminalRunIdRef = useRef<string | null>(null);

  const applyProgress = useCallback((next: PipelineProgress) => {
    // Ignore stale terminal snapshots after the UI has already reset.
    if (
      (next.status === "completed" || next.status === "failed") &&
      next.run_id !== null &&
      seenTerminalRunIdRef.current === next.run_id &&
      statusRef.current === "idle"
    ) {
      return;
    }

    const isNewRun =
      next.status === "running" &&
      next.run_id !== null &&
      next.run_id !== activeRunIdRef.current;

    if (isNewRun) {
      activeRunIdRef.current = next.run_id;
      targetPercentRef.current = 0;
      displayPercentRef.current = 0;
      setDisplayPercent(0);
    }

    statusRef.current = next.status;
    setProgress(next);
    setError(next.error);

    if (next.status === "idle") {
      activeRunIdRef.current = null;
      targetPercentRef.current = 0;
      displayPercentRef.current = 0;
      setDisplayPercent(0);
      return;
    }

    const nextTarget = clampPercent(next.percent);
    targetPercentRef.current = Math.max(targetPercentRef.current, nextTarget);

    if (next.status === "completed") {
      targetPercentRef.current = 100;
      if (next.run_id) {
        seenTerminalRunIdRef.current = next.run_id;
      }
    }

    if (next.status === "failed") {
      targetPercentRef.current = clampPercent(next.percent);
      if (next.run_id) {
        seenTerminalRunIdRef.current = next.run_id;
      }
    }
  }, []);

  useEffect(() => {
    if (isMockDataMode()) {
      return;
    }

    let cancelled = false;

    getPipelineProgress()
      .then((snapshot) => {
        if (!cancelled) {
          applyProgress(snapshot);
        }
      })
      .catch(() => {
        // Ignore bootstrap errors; SSE will reconnect.
      });

    return () => {
      cancelled = true;
    };
  }, [applyProgress]);

  useEffect(() => {
    if (isMockDataMode()) {
      return;
    }

    let cancelled = false;
    let eventSource: EventSource | null = null;
    let retryTimer: number | null = null;
    let retryDelay = INITIAL_RETRY_MS;

    const connect = () => {
      if (cancelled) {
        return;
      }

      eventSource = new EventSource(getPipelineEventsUrl());

      eventSource.addEventListener("pipeline-progress", (event) => {
        try {
          const payload = JSON.parse(event.data) as PipelineProgress;
          applyProgress(payload);
        } catch {
          // Ignore malformed events.
        }
      });

      eventSource.onopen = () => {
        retryDelay = INITIAL_RETRY_MS;
      };

      eventSource.onerror = () => {
        eventSource?.close();
        eventSource = null;

        if (cancelled) {
          return;
        }

        retryTimer = window.setTimeout(() => {
          retryDelay = Math.min(retryDelay * 2, MAX_RETRY_MS);
          connect();
        }, retryDelay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      eventSource?.close();
      if (retryTimer !== null) {
        window.clearTimeout(retryTimer);
      }
    };
  }, [applyProgress]);

  useEffect(() => {
    if (progress.status !== "completed" && progress.status !== "failed") {
      return;
    }

    const timer = window.setTimeout(() => {
      applyProgress(IDLE_PIPELINE_PROGRESS);
    }, TERMINAL_RESET_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [applyProgress, progress.status]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      const target = targetPercentRef.current;
      const current = displayPercentRef.current;
      const status = statusRef.current;

      if (status === "idle") {
        if (current !== 0) {
          displayPercentRef.current = 0;
          setDisplayPercent(0);
        }
        return;
      }

      if (status === "completed") {
        if (current < 100) {
          const next = Math.min(100, current + Math.max(1.5, (100 - current) * 0.35));
          displayPercentRef.current = next;
          setDisplayPercent(next);
        }
        return;
      }

      if (Math.abs(target - current) < 0.15) {
        if (current !== target) {
          displayPercentRef.current = target;
          setDisplayPercent(target);
        }
        return;
      }

      const next = current + (target - current) * SMOOTH_CATCHUP_FACTOR;
      displayPercentRef.current = next;
      setDisplayPercent(next);
    }, SMOOTH_TICK_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, []);

  const startRefresh = useCallback(async () => {
    if (isMockDataMode()) {
      setError("Pipeline refresh is unavailable in mock data mode.");
      return;
    }

    if (isStarting || progress.status === "running") {
      return;
    }

    setIsStarting(true);
    setError(null);
    targetPercentRef.current = 1;
    displayPercentRef.current = Math.max(displayPercentRef.current, 1);
    setDisplayPercent(displayPercentRef.current);
    applyProgress({
      ...IDLE_PIPELINE_PROGRESS,
      status: "running",
      percent: 1,
      stage: "pipeline",
      message: "Starting pipeline run",
    });

    try {
      await startPipelineRun();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Unable to start pipeline refresh";
      setError(message);
      applyProgress(IDLE_PIPELINE_PROGRESS);
    } finally {
      setIsStarting(false);
    }
  }, [applyProgress, isStarting, progress.status]);

  // Keep the button locked for any non-idle pipeline state, including
  // scheduled/cron runs that arrive over the progress SSE stream.
  const isBusy =
    isStarting ||
    progress.status === "running" ||
    progress.status === "completed" ||
    progress.status === "failed";

  return {
    progress,
    displayPercent: Math.round(displayPercent),
    isBusy,
    isStarting,
    error,
    startRefresh,
  };
}
