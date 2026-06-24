"use client";

import { useEffect, useState } from "react";
import LoadingState from "@/components/LoadingState";
import { fetchMockStats } from "@/services/mockData";
import type { FoodRecallAlertStats } from "@/types/alert";

type StatsStatus = "pending" | "ready";

export default function StatsPage() {
  const [status, setStatus] = useState<StatsStatus>("pending");
  const [stats, setStats] = useState<FoodRecallAlertStats | null>(null);

  useEffect(() => {
    fetchMockStats().then((data) => {
      setStats(data);
      setStatus("ready");
    });
  }, []);

  if (status === "pending") {
    return <LoadingState />;
  }

  if (!stats) {
    return null;
  }

  return (
    <div>
      <h2 className="mb-8 text-2xl font-bold tracking-tight text-slate-900">
        Food Recall Alert Statistics
      </h2>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <div className="rounded-xl bg-white p-8 shadow-md ring-1 ring-slate-200/60">
          <p className="mb-3 text-sm font-medium tracking-wide text-slate-500 uppercase">
            Total Active Alerts
          </p>
          <p className="text-5xl font-extrabold text-slate-900">
            {stats.total_alerts}
          </p>
        </div>

        <div className="rounded-xl bg-white p-8 shadow-md ring-1 ring-slate-200/60">
          <p className="mb-3 text-sm font-medium tracking-wide text-slate-500 uppercase">
            Top Hazard Type
          </p>
          <p className="text-2xl font-bold text-rose-600">
            {stats.top_hazard_type}
          </p>
        </div>

        <div className="rounded-xl bg-white p-8 shadow-md ring-1 ring-slate-200/60">
          <p className="mb-3 text-sm font-medium tracking-wide text-slate-500 uppercase">
            Active Affected Regions
          </p>
          <p className="text-5xl font-extrabold text-slate-900">
            {stats.active_regions}
          </p>
        </div>
      </div>
    </div>
  );
}
