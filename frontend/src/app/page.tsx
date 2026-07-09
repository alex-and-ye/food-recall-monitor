"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import SearchToolbar from "@/components/SearchToolbar";
import EmptyState from "@/components/EmptyState";
import FoodRecallAlertCard from "@/components/FoodRecallAlertCard";
import LoadingState from "@/components/LoadingState";
import Pagination from "@/components/Pagination";
import {
  alertFetchParamsFromSearchParams,
  formatResultsCount,
  formStateFromSearchParams,
  hasActiveUrlFilters,
  searchParamsFromFormState,
  type AlertSearchFormState,
} from "@/lib/alertSearch";
import { bodySecondaryClassName } from "@/lib/ui";
import { getAlerts } from "@/services/api/client";
import { useAlertsChangeStream } from "@/hooks/useAlertsChangeStream";
import type { FoodRecallAlert } from "@/types/alert";

const ITEMS_PER_PAGE = 10;

type PageStatus = "pending" | "empty" | "ready";

function HomePageContent() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const [status, setStatus] = useState<PageStatus>("pending");
  const [alerts, setAlerts] = useState<FoodRecallAlert[]>([]);
  const [currentPage, setCurrentPage] = useState(1);

  const urlFormState = formStateFromSearchParams(searchParams);

  const applyFilters = useCallback(
    (state: AlertSearchFormState) => {
      const params = searchParamsFromFormState(state);
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
      setCurrentPage(1);
    },
    [pathname, router],
  );

  const loadAlerts = useCallback((options?: { silent?: boolean }) => {
    const params = alertFetchParamsFromSearchParams(searchParams);
    if (!options?.silent) {
      setStatus("pending");
    }

    getAlerts(params)
      .then((data) => {
        const filtersActive = hasActiveUrlFilters(searchParams);

        if (data.length === 0 && !filtersActive) {
          setAlerts([]);
          setStatus("empty");
          return;
        }

        setAlerts(data);
        setStatus("ready");
      })
      .catch(() => {
        if (!options?.silent) {
          setAlerts([]);
          setStatus("empty");
        }
      });
  }, [searchParams]);

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  useAlertsChangeStream(() => {
    loadAlerts({ silent: true });
  }, status !== "pending");

  useEffect(() => {
    setCurrentPage(1);
  }, [searchParams]);

  const hasFeeds = status === "ready" || hasActiveUrlFilters(searchParams);
  const hasResults = alerts.length > 0;
  const totalPages = Math.max(1, Math.ceil(alerts.length / ITEMS_PER_PAGE));
  const pageStart = (currentPage - 1) * ITEMS_PER_PAGE;
  const pageEnd = currentPage * ITEMS_PER_PAGE;
  const visibleAlerts = alerts.slice(pageStart, pageEnd);

  return (
    <>
      <SearchToolbar
        hasFeeds={hasFeeds}
        formState={urlFormState}
        onApplyFilters={applyFilters}
      />

      {status === "pending" && <LoadingState />}

      {status === "empty" && <EmptyState />}

      {status === "ready" && (
        <>
          <p className={`mb-4 font-medium ${bodySecondaryClassName}`}>
            {formatResultsCount(alerts.length)}
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
            <p className={`text-center ${bodySecondaryClassName}`}>
              No food recall alerts match your current search and filters.
            </p>
          )}
        </>
      )}
    </>
  );
}

export default function HomePage() {
  return (
    <Suspense fallback={<LoadingState />}>
      <HomePageContent />
    </Suspense>
  );
}
