/**
 * Globe map page: desktop 3D globe of official recall pins with a side panel
 * for alert details and pin-placement disclaimer; mobile shows a fallback notice.
 */

"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import EmptyState from "@/components/EmptyState";
import FoodRecallAlertDetails from "@/components/FoodRecallAlertDetails";
import LoadingState from "@/components/LoadingState";
import { useAlertsChangeStream } from "@/hooks/useAlertsChangeStream";
import {
  bodySecondaryClassName,
  bodyTextClassName,
  cardClassName,
  panelClassName,
} from "@/lib/ui";
import { getAlerts } from "@/services/api/client";
import type { FoodRecallAlert } from "@/types/alert";

/** Client-only globe (WebGL); disabled SSR to avoid hydration issues. */
const GlobeComponent = dynamic(() => import("@/components/GlobeComponent"), {
  ssr: false,
  loading: () => <LoadingState />,
});

/** Disclaimer bullet points explaining approximate pin placement rules. */
const GLOBE_PIN_DISCLAIMER_POINTS = [
  "Each pin represents one food recall alert, not every affected region listed for that alert.",
  "If an alert has no affected regions, the pin is placed using the alert country source.",
  "If an alert has exactly one affected region, the pin is placed using that region within the alert country source.",
  "If an alert has two or more affected regions, the pin is placed at the average location of those regions within the alert country source.",
  "Affected regions are assumed to belong to the same country as the alert country source.",
  "Pin positions may include a small random offset so alerts from similar locations do not stack on top of each other.",
  "Pin locations are approximate and intended for exploratory visualization in this proof of concept, not for precise geographic or regulatory mapping.",
] as const;

/** Status of the globe map page loading state. */
type PageStatus = "pending" | "empty" | "ready" | "error";

/** Type for the side panel view. */
type SidePanelView = "alert" | "disclaimer" | null;

/**
 * Loads alerts onto the interactive globe and manages the detail/disclaimer side panel.
 *
 * @returns Globe map page UI.
 */
export default function MapPage() {
  const [status, setStatus] = useState<PageStatus>("pending");
  const [alerts, setAlerts] = useState<FoodRecallAlert[]>([]);
  const [selectedAlert, setSelectedAlert] = useState<FoodRecallAlert | null>(null);
  const [sidePanelView, setSidePanelView] = useState<SidePanelView>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadAlerts = useCallback((options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setStatus("pending");
      setErrorMessage(null);
    }

    void getAlerts()
      .then((nextAlerts) => {
        setAlerts(nextAlerts);
        setStatus(nextAlerts.length === 0 ? "empty" : "ready");
      })
      .catch((error: unknown) => {
        const message =
          error instanceof Error ? error.message : "Failed to load alerts.";
        setErrorMessage(message);
        setStatus("error");
      });
  }, []);

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  useAlertsChangeStream(() => {
    loadAlerts({ silent: true });
  });

  const closeSidePanel = () => {
    setSidePanelView(null);
    setSelectedAlert(null);
  };

  const openAlertPanel = (alert: FoodRecallAlert) => {
    setSelectedAlert(alert);
    setSidePanelView("alert");
  };

  const openDisclaimerPanel = () => {
    setSelectedAlert(null);
    setSidePanelView("disclaimer");
  };

  const isSidePanelOpen = sidePanelView !== null;

  return (
    <div className="relative flex h-full min-h-0 flex-col bg-slate-950">
      <div className="block flex-1 p-4 md:hidden sm:p-6">
        <div className="rounded-xl border border-slate-700 bg-slate-900 p-6">
          <h2 className="text-lg font-semibold text-slate-100">Globe Map</h2>
          <p className={`mt-2 ${bodySecondaryClassName} text-slate-300`}>
            The 3D interactive globe is optimized for desktop viewing. Please use a
            larger screen or return to the{" "}
            <Link
              href="/"
              className="font-medium text-emerald-400 underline-offset-2 hover:underline"
            >
              Feed
            </Link>
            .
          </p>
        </div>
      </div>

      <div className="relative hidden min-h-0 flex-1 md:flex md:flex-col">
        <div className="pointer-events-none absolute left-4 top-4 z-10 max-w-sm rounded-lg border border-slate-700/80 bg-slate-950/75 px-4 py-3 backdrop-blur-sm">
          <h2 className="text-sm font-semibold tracking-wide text-emerald-300">
            Globe Map
          </h2>
          <p className="mt-1 text-sm text-slate-300">
            Explore food recall alerts pinned to affected regions.
          </p>
          <button
            type="button"
            onClick={openDisclaimerPanel}
            className="pointer-events-auto mt-2 text-sm text-slate-300 underline underline-offset-2 transition-colors hover:text-slate-100"
          >
            Disclaimer
          </button>
        </div>

        {status === "pending" ? (
          <div className="flex flex-1 items-center justify-center bg-slate-950">
            <LoadingState />
          </div>
        ) : null}
        {status === "empty" ? (
          <div className="flex flex-1 items-center justify-center bg-slate-950 p-6">
            <EmptyState />
          </div>
        ) : null}
        {status === "error" ? (
          <div className="flex flex-1 items-center justify-center bg-slate-950 p-6">
            <div className={`${cardClassName} px-6 py-12 text-center`}>
              <p className={`font-medium ${bodySecondaryClassName}`}>
                {errorMessage ?? "Failed to load alerts."}
              </p>
            </div>
          </div>
        ) : null}
        {status === "ready" ? (
          <div className="min-h-0 flex-1">
            <GlobeComponent
              alerts={alerts}
              selectedAlertId={selectedAlert?.alert_id ?? null}
              onPointClick={openAlertPanel}
            />
          </div>
        ) : null}

        <aside
          className={`absolute inset-y-0 right-0 z-20 flex w-full max-w-md transform flex-col bg-white p-4 shadow-xl transition-transform duration-300 ease-in-out ${
            isSidePanelOpen ? "translate-x-0" : "translate-x-full"
          }`}
          aria-hidden={!isSidePanelOpen}
        >
          <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
            <h3 className="text-base font-semibold text-slate-950">
              {sidePanelView === "disclaimer" ? "Disclaimer" : "Alert details"}
            </h3>
            <button
              type="button"
              onClick={closeSidePanel}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
              aria-label="Close side panel"
            >
              X
            </button>
          </div>
          {sidePanelView === "alert" && selectedAlert !== null ? (
            <div className={`${panelClassName} min-h-0 flex-1 overflow-y-auto`}>
              <FoodRecallAlertDetails alert={selectedAlert} />
            </div>
          ) : null}
          {sidePanelView === "disclaimer" ? (
            <div className={`${panelClassName} min-h-0 flex-1 overflow-y-auto`}>
              <p className={`mb-4 ${bodyTextClassName}`}>
                Please keep the following in mind when interpreting pins on the globe
                map:
              </p>
              <ul className={`list-disc space-y-3 pl-5 ${bodySecondaryClassName}`}>
                {GLOBE_PIN_DISCLAIMER_POINTS.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
