"use client";

import Link from "next/link";
import { getRiskBadgeClassName } from "@/lib/alertStyles";
import { bodySecondaryClassName, cardClassName } from "@/lib/ui";
import type { FoodRecallAlert } from "@/types/alert";

interface FoodRecallAlertCardProps {
  alert: FoodRecallAlert;
}

const formatText = (value?: string | null) =>
  value && value.trim() ? value : "Not available";

export default function FoodRecallAlertCard({ alert }: FoodRecallAlertCardProps) {
  return (
    <Link
      href={`/alerts/${encodeURIComponent(alert.alert_id)}`}
      className={`block w-full ${cardClassName} p-5 text-left transition-colors hover:border-slate-400 hover:bg-slate-50`}
    >
      <div className="flex items-start justify-between gap-4">
        <h2 className="text-lg font-semibold text-slate-950">
          {formatText(alert.product_name)}
        </h2>
        <time
          className={`shrink-0 ${bodySecondaryClassName} text-sm`}
          dateTime={formatText(alert.recall_date)}
        >
          {formatText(alert.recall_date)}
        </time>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <span
          className={`inline-block rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${getRiskBadgeClassName(alert.risk_level)}`}
        >
          {formatText(alert.risk_level)}
        </span>
        <span className={bodySecondaryClassName}>
          {formatText(alert.country_source)}
        </span>
      </div>
    </Link>
  );
}
