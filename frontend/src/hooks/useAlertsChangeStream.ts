/**
 * React hook that listens for official-alert SSE change events and triggers
 * a debounced refresh callback, with exponential backoff on disconnect.
 */

"use client";

import { useEffect, useRef } from "react";
import { getAlertsEventsUrl } from "@/services/api/client";

/** Debounce window before invoking the refresh callback after an SSE event. */
const REFRESH_DEBOUNCE_MS = 300;

/** Initial reconnect delay after an EventSource error. */
const INITIAL_RETRY_MS = 1_000;

/** Upper bound for exponential reconnect backoff. */
const MAX_RETRY_MS = 30_000;

/**
 * Subscribes to the alerts change stream and calls `onAlertsChanged` when data updates.
 *
 * @param onAlertsChanged - Callback invoked (debounced) when alerts change.
 * @param enabled - When `false`, the stream is not connected.
 */
export function useAlertsChangeStream(
  onAlertsChanged: () => void,
  enabled = true,
): void {
  const onAlertsChangedRef = useRef(onAlertsChanged);

  useEffect(() => {
    onAlertsChangedRef.current = onAlertsChanged;
  }, [onAlertsChanged]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    let cancelled = false;
    let eventSource: EventSource | null = null;
    let retryTimer: number | null = null;
    let debounceTimer: number | null = null;
    let retryDelay = INITIAL_RETRY_MS;

    const scheduleRefresh = () => {
      if (debounceTimer !== null) {
        window.clearTimeout(debounceTimer);
      }

      debounceTimer = window.setTimeout(() => {
        onAlertsChangedRef.current();
      }, REFRESH_DEBOUNCE_MS);
    };

    const connect = () => {
      if (cancelled) {
        return;
      }

      eventSource = new EventSource(getAlertsEventsUrl());

      eventSource.addEventListener("alerts-changed", () => {
        scheduleRefresh();
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

      if (debounceTimer !== null) {
        window.clearTimeout(debounceTimer);
      }
    };
  }, [enabled]);
}
