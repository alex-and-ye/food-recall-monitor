"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import EarlyWarningIncidentCard from "@/components/EarlyWarningIncidentCard";
import IncidentSearchToolbar from "@/components/IncidentSearchToolbar";
import LoadingState from "@/components/LoadingState";
import Pagination from "@/components/Pagination";
import {
  hasActiveIncidentUrlFilters,
  incidentFetchParamsFromSearchParams,
  incidentFormStateFromSearchParams,
  incidentSearchParamsFromFormState,
  type IncidentSearchFormState,
} from "@/lib/incidentSearch";
import {
  bodySecondaryClassName,
  cardClassName,
  pageTitleClassName,
} from "@/lib/ui";
import { getIncidents } from "@/services/api/client";
import { useIncidentsChangeStream } from "@/hooks/useIncidentsChangeStream";
import type { EarlyWarningIncident } from "@/types/incident";

const ITEMS_PER_PAGE = 10;

type PageStatus = "pending" | "ready" | "error";

function EarlyWarningsPageContent() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const [status, setStatus] = useState<PageStatus>("pending");
  const [incidents, setIncidents] = useState<EarlyWarningIncident[]>([]);
  const [currentPage, setCurrentPage] = useState(1);

  const formState = incidentFormStateFromSearchParams(searchParams);

  const applyFilters = useCallback(
    (state: IncidentSearchFormState) => {
      const params = incidentSearchParamsFromFormState(state);
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, {
        scroll: false,
      });
      setCurrentPage(1);
    },
    [pathname, router],
  );

  useEffect(() => {
    let cancelled = false;

    getIncidents(incidentFetchParamsFromSearchParams(searchParams))
      .then((data) => {
        if (!cancelled) {
          setIncidents(data);
          setStatus("ready");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setIncidents([]);
          setStatus("error");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  useIncidentsChangeStream(() => {
    getIncidents(incidentFetchParamsFromSearchParams(searchParams))
      .then((data) => {
        setIncidents(data);
        setStatus("ready");
      })
      .catch(() => undefined);
  });

  const totalPages = Math.max(1, Math.ceil(incidents.length / ITEMS_PER_PAGE));
  const pageStart = (currentPage - 1) * ITEMS_PER_PAGE;
  const visibleIncidents = incidents.slice(
    pageStart,
    pageStart + ITEMS_PER_PAGE,
  );
  const hasFilters = hasActiveIncidentUrlFilters(searchParams);

  return (
    <div>
      <div className="mb-6">
        <h1 className={pageTitleClassName}>Early Warnings</h1>
        <p className={`mt-2 max-w-3xl ${bodySecondaryClassName}`}>
          Potential food safety incidents discovered from reported sources.
          These records are not official recalls unless they are explicitly
          marked as officially confirmed.
        </p>
      </div>

      <IncidentSearchToolbar
        key={searchParams.toString()}
        enabled={status === "ready"}
        formState={formState}
        onApplyFilters={applyFilters}
      />

      {status === "pending" ? <LoadingState /> : null}

      {status === "error" ? (
        <div className={`${cardClassName} p-6`}>
          <p className="font-medium text-slate-950">
            Unable to load early warnings.
          </p>
          <p className={`mt-1 ${bodySecondaryClassName}`}>
            Check that the incident API is available, then refresh this page.
          </p>
        </div>
      ) : null}

      {status === "ready" ? (
        <>
          <p className={`mb-4 font-medium ${bodySecondaryClassName}`}>
            {incidents.length === 1
              ? "Showing 1 incident"
              : `Showing ${incidents.length} incidents`}
          </p>

          {visibleIncidents.length ? (
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              onPrevious={() => setCurrentPage((page) => Math.max(1, page - 1))}
              onNext={() =>
                setCurrentPage((page) => Math.min(totalPages, page + 1))
              }
            >
              <div className="mb-8 space-y-4">
                {visibleIncidents.map((incident) => (
                  <EarlyWarningIncidentCard
                    key={incident.incident_id}
                    incident={incident}
                  />
                ))}
              </div>
            </Pagination>
          ) : (
            <div className={`${cardClassName} p-6 text-center`}>
              <p className="font-medium text-slate-950">
                {hasFilters
                  ? "No incidents match the current filters."
                  : "No early warning incidents have been reported."}
              </p>
              <p className={`mt-1 ${bodySecondaryClassName}`}>
                {hasFilters
                  ? "Clear or adjust the filters to broaden the results."
                  : "Official recalls remain available in Official Recalls."}
              </p>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

export default function EarlyWarningsPage() {
  return (
    <Suspense fallback={<LoadingState />}>
      <EarlyWarningsPageContent />
    </Suspense>
  );
}
