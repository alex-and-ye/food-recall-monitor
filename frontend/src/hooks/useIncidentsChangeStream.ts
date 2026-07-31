"use client";

import { useEffect, useRef } from "react";
import { getIncidentsEventsUrl } from "@/services/api/client";

const REFRESH_DEBOUNCE_MS = 300;
const INITIAL_RETRY_MS = 1_000;
const MAX_RETRY_MS = 30_000;

export function useIncidentsChangeStream(
  onIncidentsChanged: () => void,
  enabled = true,
): void {
  const callbackRef = useRef(onIncidentsChanged);

  useEffect(() => {
    callbackRef.current = onIncidentsChanged;
  }, [onIncidentsChanged]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    let cancelled = false;
    let eventSource: EventSource | null = null;
    let retryTimer: number | null = null;
    let debounceTimer: number | null = null;
    let retryDelay = INITIAL_RETRY_MS;

    const connect = () => {
      if (cancelled) {
        return;
      }
      eventSource = new EventSource(getIncidentsEventsUrl());
      eventSource.addEventListener("incidents-changed", () => {
        if (debounceTimer !== null) {
          window.clearTimeout(debounceTimer);
        }
        debounceTimer = window.setTimeout(
          () => callbackRef.current(),
          REFRESH_DEBOUNCE_MS,
        );
      });
      eventSource.onopen = () => {
        retryDelay = INITIAL_RETRY_MS;
      };
      eventSource.onerror = () => {
        eventSource?.close();
        eventSource = null;
        if (!cancelled) {
          retryTimer = window.setTimeout(() => {
            retryDelay = Math.min(retryDelay * 2, MAX_RETRY_MS);
            connect();
          }, retryDelay);
        }
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
