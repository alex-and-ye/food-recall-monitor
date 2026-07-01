"use client";

import { useCallback, useEffect, useState } from "react";
import SearchToolbar from "@/components/SearchToolbar";
import EmptyState from "@/components/EmptyState";
import FoodRecallAlertCard from "@/components/FoodRecallAlertCard";
import LoadingState from "@/components/LoadingState";
import Pagination from "@/components/Pagination";
import {
  filterAlerts,
  formatResultsCount,
  type AlertSearchPayload,
} from "@/lib/alertSearch";
import { fetchMockAlerts } from "@/services/mockData";
import type { FoodRecallAlert } from "@/types/alert";

const ITEMS_PER_PAGE = 10;

type PageStatus = "pending" | "empty" | "ready";

export default function HomePage() {
  const [status, setStatus] = useState<PageStatus>("pending");
  const [alerts, setAlerts] = useState<FoodRecallAlert[]>([]);
  const [displayedAlerts, setDisplayedAlerts] = useState<FoodRecallAlert[]>([]);
  const [currentPage, setCurrentPage] = useState(1);

  const loadAlerts = useCallback(() => {
    setStatus("pending");
    setCurrentPage(1);

    fetchMockAlerts().then((data) => {
      if (data.length === 0) {
        setAlerts([]);
        setDisplayedAlerts([]);
        setStatus("empty");
      } else {
        setAlerts(data);
        setDisplayedAlerts(data);
        setStatus("ready");
      }
    });
  }, []);

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  const handleSearch = useCallback(
    (payload: AlertSearchPayload) => {
      setDisplayedAlerts(filterAlerts(alerts, payload));
      setCurrentPage(1);
    },
    [alerts],
  );

  const hasFeeds = alerts.length > 0;
  const hasResults = displayedAlerts.length > 0;
  const totalPages = Math.max(1, Math.ceil(displayedAlerts.length / ITEMS_PER_PAGE));
  const pageStart = (currentPage - 1) * ITEMS_PER_PAGE;
  const pageEnd = currentPage * ITEMS_PER_PAGE;
  const visibleAlerts = displayedAlerts.slice(pageStart, pageEnd);

  return (
    <>
      <SearchToolbar hasFeeds={hasFeeds} onSearch={handleSearch} />

      {status === "pending" && <LoadingState />}

      {status === "empty" && <EmptyState onCheckAgain={loadAlerts} />}

      {status === "ready" && (
        <>
          <p className="mb-4 text-sm font-medium text-slate-600">
            {formatResultsCount(displayedAlerts.length)}
          </p>

          {hasResults ? (
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              onPrevious={() => setCurrentPage((page) => Math.max(1, page - 1))}
              onNext={() =>
                setCurrentPage((page) => Math.min(totalPages, page + 1))
              }
            >
              <div className="mb-8 space-y-4">
                {visibleAlerts.map((alert) => (
                  <FoodRecallAlertCard key={alert.alert_id} alert={alert} />
                ))}
              </div>
            </Pagination>
          ) : (
            <p className="text-center text-sm text-slate-600">
              No alerts match your current search and filters.
            </p>
          )}
        </>
      )}
    </>
  );
}
