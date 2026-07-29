"use client";

import { useCallback, useEffect, useState } from "react";
import LoadingState from "@/components/LoadingState";
import {
  bodyTextClassName,
  cardClassName,
  mutedTextClassName,
  pageTitleClassName,
  sectionLabelClassName,
} from "@/lib/ui";
import { getAlertStats } from "@/services/api/client";
import { useAlertsChangeStream } from "@/hooks/useAlertsChangeStream";
import type { FoodRecallAlertStats } from "@/types/alert";

type StatsStatus = "pending" | "ready";

interface RankedListProps {
  title: string;
  items: [string, number][];
  accentClassName?: string;
}

function RankedList({
  title,
  items,
  accentClassName = "text-slate-900",
}: RankedListProps) {
  const maxCount = items[0]?.[1] ?? 0;

  return (
    <div className={`${cardClassName} p-6`}>
      <h3 className={`mb-4 ${sectionLabelClassName}`}>{title}</h3>

      {items.length === 0 ? (
        <p className={mutedTextClassName}>No data available.</p>
      ) : (
        <ol className="space-y-3">
          {items.map(([name, count], index) => (
            <li key={`${name}-${index}`}>
              <div className="mb-1 flex items-baseline justify-between gap-3">
                <span className={`truncate font-medium ${bodyTextClassName}`}>
                  <span className="mr-2 text-sm font-semibold text-slate-400">
                    {index + 1}.
                  </span>
                  {name}
                </span>
                <span className={`shrink-0 text-base font-bold ${accentClassName}`}>
                  {count}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-slate-300"
                  style={{
                    width: maxCount > 0 ? `${(count / maxCount) * 100}%` : "0%",
                  }}
                />
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

interface SummaryCardProps {
  label: string;
  value: number;
}

function SummaryCard({ label, value }: SummaryCardProps) {
  return (
    <div className={`${cardClassName} p-6`}>
      <p className={`mb-3 ${sectionLabelClassName}`}>{label}</p>
      <p className="text-5xl font-extrabold text-slate-900">{value}</p>
    </div>
  );
}

export default function StatsPage() {
  const [status, setStatus] = useState<StatsStatus>("pending");
  const [stats, setStats] = useState<FoodRecallAlertStats | null>(null);

  const loadStats = useCallback((options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setStatus("pending");
    }

    getAlertStats().then((data) => {
      setStats(data);
      setStatus("ready");
    });
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useAlertsChangeStream(() => {
    loadStats({ silent: true });
  });

  if (status === "pending") {
    return <LoadingState />;
  }

  if (!stats) {
    return null;
  }

  return (
    <div>
      <h2 className={`mb-8 ${pageTitleClassName}`}>
        Food Recall Alert Statistics
      </h2>

      <div className="mb-6 grid grid-cols-1 gap-6 sm:grid-cols-3">
        <SummaryCard label="Total Active Alerts" value={stats.total_alerts} />
        <SummaryCard
          label="Alerts (Last 7 Days)"
          value={stats.alerts_last_7_days}
        />
        <SummaryCard
          label="Alerts (Last 30 Days)"
          value={stats.alerts_last_30_days}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <RankedList
          title="Top Hazard Types"
          items={stats.top_5_hazard_types}
          accentClassName="text-rose-600"
        />
        <RankedList
          title="Top Product Categories"
          items={stats.top_5_product_categories}
          accentClassName="text-emerald-600"
        />
        <RankedList
          title="Top Affected Regions"
          items={stats.top_5_affected_regions}
          accentClassName="text-indigo-600"
        />
      </div>
    </div>
  );
}
