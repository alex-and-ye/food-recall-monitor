"use client";

import { useCallback, useEffect, useState } from "react";
import EmptyState from "@/components/EmptyState";
import FoodRecallAlertCard from "@/components/FoodRecallAlertCard";
import LoadingState from "@/components/LoadingState";
import Pagination from "@/components/Pagination";
import { fetchMockAlerts } from "@/services/mockData";
import type { FoodRecallAlert } from "@/types/alert";

const ITEMS_PER_PAGE = 10;

type PageStatus = "pending" | "empty" | "ready";

export default function HomePage() {
  const [status, setStatus] = useState<PageStatus>("pending");
  const [alerts, setAlerts] = useState<FoodRecallAlert[]>([]);
  const [currentPage, setCurrentPage] = useState(1);

  const loadAlerts = useCallback(() => {
    setStatus("pending");
    setCurrentPage(1);

    fetchMockAlerts().then((data) => {
      if (data.length === 0) {
        setAlerts([]);
        setStatus("empty");
      } else {
        setAlerts(data);
        setStatus("ready");
      }
    });
  }, []);

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  const totalPages = Math.ceil(alerts.length / ITEMS_PER_PAGE);
  const pageStart = (currentPage - 1) * ITEMS_PER_PAGE;
  const pageEnd = currentPage * ITEMS_PER_PAGE;
  const visibleAlerts = alerts.slice(pageStart, pageEnd);

  return (
    <>
      {status === "pending" && <LoadingState />}

      {status === "empty" && <EmptyState onCheckAgain={loadAlerts} />}

      {status === "ready" && (
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
      )}
    </>
  );
}
