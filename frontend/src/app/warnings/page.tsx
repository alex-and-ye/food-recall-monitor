/**
 * Pipeline warnings page: list, acknowledge individually or in bulk, with
 * expandable long messages.
 */

"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import LoadingState from "@/components/LoadingState";
import {
  bodySecondaryClassName,
  bodyTextClassName,
  cardClassName,
  mutedTextClassName,
  pageTitleClassName,
  primaryButtonClassName,
  secondaryButtonClassName,
} from "@/lib/ui";
import {
  acknowledgeAllWarnings,
  acknowledgeWarning,
  getWarnings,
} from "@/services/api/client";
import {
  WARNING_CATEGORY_LABELS,
  type PipelineWarning,
} from "@/types/warning";

/** Status of the warnings page loading state. */
type WarningsStatus = "pending" | "ready" | "error";

/**
 * Formats a warning timestamp for display.
 *
 * @param value - ISO datetime string.
 * @returns Localized medium date and short time, or the raw value if invalid.
 */
function formatWarningTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

/**
 * Warning message that clamps to three lines and offers expand/collapse when truncated.
 *
 * @param props.message - Full warning message text.
 * @returns Expandable message block.
 */
function ExpandableWarningMessage({ message }: { message: string }) {
  const [expanded, setExpanded] = useState(false);
  const [canToggle, setCanToggle] = useState(false);
  const textRef = useRef<HTMLParagraphElement>(null);

  useLayoutEffect(() => {
    setExpanded(false);
    setCanToggle(false);
  }, [message]);

  useLayoutEffect(() => {
    const element = textRef.current;
    if (!element || expanded) {
      return;
    }

    const measure = () => {
      if (element.scrollHeight > element.clientHeight + 1) {
        setCanToggle(true);
      }
    };

    measure();
    if (typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, [message, expanded]);

  return (
    <div>
      <p
        ref={textRef}
        className={`${bodyTextClassName} break-words ${
          expanded ? "" : "line-clamp-3"
        }`}
      >
        {message}
      </p>
      {canToggle ? (
        <button
          type="button"
          className="mt-1 text-sm font-medium text-emerald-700 underline-offset-2 hover:underline"
          onClick={() => {
            setExpanded((current) => !current);
          }}
        >
          {expanded ? "Shrink" : "Extend"}
        </button>
      ) : null}
    </div>
  );
}

/**
 * Loads and displays pipeline warnings with acknowledge actions.
 *
 * @returns Warnings page UI.
 */
export default function WarningsPage() {
  const [status, setStatus] = useState<WarningsStatus>("pending");
  const [warnings, setWarnings] = useState<PipelineWarning[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [acknowledgingAll, setAcknowledgingAll] = useState(false);

  const loadWarnings = useCallback(async () => {
    setStatus("pending");
    try {
      const data = await getWarnings();
      setWarnings(data);
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void loadWarnings();
  }, [loadWarnings]);

  const handleAcknowledge = async (warningId: string) => {
    setBusyId(warningId);
    try {
      const updated = await acknowledgeWarning(warningId);
      setWarnings((current) =>
        current.map((item) =>
          item.warning_id === updated.warning_id ? updated : item,
        ),
      );
    } finally {
      setBusyId(null);
    }
  };

  const handleAcknowledgeAll = async () => {
    setAcknowledgingAll(true);
    try {
      await acknowledgeAllWarnings();
      setWarnings((current) =>
        current.map((item) => ({ ...item, acknowledged: true })),
      );
    } finally {
      setAcknowledgingAll(false);
    }
  };

  if (status === "pending") {
    return <LoadingState />;
  }

  if (status === "error") {
    return (
      <div>
        <h2 className={`mb-4 ${pageTitleClassName}`}>Warnings</h2>
        <p className={bodySecondaryClassName}>
          Unable to load pipeline warnings. Try refreshing the page.
        </p>
      </div>
    );
  }

  const unacknowledgedCount = warnings.filter((item) => !item.acknowledged).length;

  return (
    <div>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className={pageTitleClassName}>Warnings</h2>
          <p className={`mt-2 ${bodySecondaryClassName}`}>
            Pipeline issues that need attention. Report these to a developer for
            investigation in the run logs.
          </p>
        </div>
        <button
          type="button"
          className={secondaryButtonClassName}
          disabled={unacknowledgedCount === 0 || acknowledgingAll}
          onClick={() => {
            void handleAcknowledgeAll();
          }}
        >
          {acknowledgingAll ? "Acknowledging…" : "Acknowledge all"}
        </button>
      </div>

      {warnings.length === 0 ? (
        <div className={`${cardClassName} p-6`}>
          <p className={mutedTextClassName}>No warnings</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {warnings.map((warning) => (
            <li
              key={warning.warning_id}
              className={`${cardClassName} p-5 ${
                warning.acknowledged ? "opacity-70" : ""
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">
                      {WARNING_CATEGORY_LABELS[warning.category]}
                    </span>
                    {warning.source ? (
                      <span className={`text-sm font-medium ${bodyTextClassName}`}>
                        Source: {warning.source}
                      </span>
                    ) : null}
                    {warning.acknowledged ? (
                      <span className={mutedTextClassName}>Acknowledged</span>
                    ) : null}
                  </div>
                  <ExpandableWarningMessage message={warning.message} />
                  <p className={`mt-2 ${mutedTextClassName}`}>
                    {formatWarningTimestamp(warning.created_at)}
                  </p>
                </div>
                {!warning.acknowledged ? (
                  <button
                    type="button"
                    className={primaryButtonClassName}
                    disabled={busyId === warning.warning_id}
                    onClick={() => {
                      void handleAcknowledge(warning.warning_id);
                    }}
                  >
                    {busyId === warning.warning_id
                      ? "Acknowledging…"
                      : "Acknowledge"}
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
