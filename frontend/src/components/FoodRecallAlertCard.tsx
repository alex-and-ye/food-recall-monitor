"use client";

import { useCallback, useEffect, useState } from "react";
import type { FoodRecallAlert, RiskLevel } from "@/types/alert";

interface FoodRecallAlertCardProps {
  alert: FoodRecallAlert;
}

const RISK_STYLES: Record<RiskLevel, { badge: string }> = {
  High: {
    badge: "bg-red-700 text-white",
  },
  Medium: {
    badge: "bg-amber-500 text-black",
  },
  Low: {
    badge: "bg-emerald-700 text-white",
  },
};

const formatText = (value?: string | null) =>
  value && value.trim() ? value : "Not available";

const formatTextArray = (value?: string[] | null) =>
  value && value.length > 0 ? value.join(", ") : "Not available";

function CloseIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-6 w-6"
      aria-hidden="true"
    >
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

function FoodRecallAlertDetails({ alert }: { alert: FoodRecallAlert }) {
  const styles = RISK_STYLES[alert.risk_level] ?? {
    badge: "bg-slate-200 text-slate-800",
  };
  const hasSourceUrl = Boolean(alert.source_url && alert.source_url.trim());

  return (
    <div className="space-y-3">
      <div className="pr-8">
        <h2 className="text-2xl font-semibold text-slate-950">
          {formatText(alert.product_name)}
        </h2>
        <time
          className="mt-1 block text-sm font-medium text-slate-700"
          dateTime={formatText(alert.recall_date)}
        >
          {formatText(alert.recall_date)}
        </time>
      </div>

      <div>
        <span className="text-base font-medium text-slate-900">Batch ID:</span>
        <p className="mt-1 text-base text-slate-900">{formatText(alert.batch_id)}</p>
      </div>

      <div>
        <span className="text-base font-medium text-slate-900">Country Source:</span>
        <p className="mt-1 text-base text-slate-900">
          {formatText(alert.country_source)}
        </p>
      </div>

      <div>
        <span className="text-base font-medium text-slate-900">Product Category:</span>
        <p className="mt-1 text-base text-slate-900">{formatText(alert.product_category)}</p>
      </div>

      <div>
        <span className="block text-base font-medium text-slate-900">Risk Level:</span>
        <span
          className={`mt-1 inline-block rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${styles.badge}`}
        >
          {formatText(alert.risk_level)}
        </span>
      </div>

      <div>
        <span className="text-base font-medium text-slate-900">Recall Reason:</span>
        <p className="mt-1 text-base text-slate-900">{formatText(alert.recall_reason)}</p>
      </div>

      <div>
        <span className="text-base font-medium text-slate-900">Hazard Type:</span>
        <p className="mt-1 text-base text-slate-900">{formatText(alert.hazard_type)}</p>
      </div>

      <div>
        <span className="text-base font-medium text-slate-900">Description:</span>
        <p className="mt-1 text-base text-slate-900">{formatText(alert.summary)}</p>
      </div>

      <div>
        <span className="text-base font-medium text-slate-900">Consumer Action:</span>
        <p className="mt-1 text-base text-slate-900">{formatText(alert.consumer_action)}</p>
      </div>

      <div>
        <span className="text-base font-medium text-slate-900">Affected Regions:</span>
        <p className="mt-1 text-base text-slate-900">
          {formatTextArray(alert.affected_regions)}
        </p>
      </div>

      {hasSourceUrl ? (
        <a
          href={alert.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block rounded-lg border border-slate-900 bg-white px-4 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-900 hover:text-white"
        >
          View Official Source
        </a>
      ) : (
        <p className="mt-2 text-sm text-slate-500">Official source not provided.</p>
      )}
    </div>
  );
}

export default function FoodRecallAlertCard({ alert }: FoodRecallAlertCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const styles = RISK_STYLES[alert.risk_level] ?? {
    badge: "bg-slate-200 text-slate-800",
  };

  const closeModal = useCallback(() => setIsOpen(false), []);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeModal();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, closeModal]);

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="w-full rounded-xl border border-slate-300 bg-white p-5 text-left shadow-sm transition-colors hover:border-slate-400 hover:bg-slate-50"
      >
        <div className="flex items-start justify-between gap-4">
          <h2 className="text-lg font-semibold text-slate-950">
            {formatText(alert.product_name)}
          </h2>
          <time
            className="shrink-0 text-sm font-medium text-slate-700"
            dateTime={formatText(alert.recall_date)}
          >
            {formatText(alert.recall_date)}
          </time>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <span
            className={`inline-block rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${styles.badge}`}
          >
            {formatText(alert.risk_level)}
          </span>
          <span className="text-sm font-medium text-slate-700">
            {formatText(alert.country_source)}
          </span>
        </div>
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/40"
            onClick={closeModal}
            aria-label="Close alert details"
          />

          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={`alert-title-${alert.alert_id}`}
            className="relative z-10 max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-slate-300 bg-white p-6 shadow-xl"
          >
            <button
              type="button"
              onClick={closeModal}
              className="absolute right-4 top-4 rounded-md p-1 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
              aria-label="Close alert details"
            >
              <CloseIcon />
            </button>

            <div id={`alert-title-${alert.alert_id}`}>
              <FoodRecallAlertDetails alert={alert} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
