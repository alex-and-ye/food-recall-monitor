/**
 * Detail page for a single official food recall alert by ID.
 */

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import BackButton from "@/components/BackButton";
import FoodRecallAlertDetails from "@/components/FoodRecallAlertDetails";
import LoadingState from "@/components/LoadingState";
import { bodySecondaryClassName, panelClassName } from "@/lib/ui";
import { ApiError, getAlertById } from "@/services/api/client";
import type { FoodRecallAlert } from "@/types/alert";

/** Status of the alert detail page loading state. */
type DetailStatus = "pending" | "ready" | "not_found" | "error";

/**
 * Loads and displays one official recall alert, or an error/not-found state.
 *
 * @returns Alert detail page UI.
 */
export default function AlertDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const alertId = params.id;

  const [status, setStatus] = useState<DetailStatus>("pending");
  const [alert, setAlert] = useState<FoodRecallAlert | null>(null);

  useEffect(() => {
    let cancelled = false;

    setStatus("pending");
    setAlert(null);

    getAlertById(alertId)
      .then((data) => {
        if (cancelled) {
          return;
        }
        setAlert(data);
        setStatus("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }

        if (error instanceof ApiError && error.status === 404) {
          setStatus("not_found");
          return;
        }

        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [alertId]);

  if (status === "pending") {
    return <LoadingState />;
  }

  if (status === "not_found") {
    return (
      <div>
        <BackButton onClick={() => router.back()} />
        <p className={`text-center ${bodySecondaryClassName}`}>Alert not found.</p>
      </div>
    );
  }

  if (status === "error" || !alert) {
    return (
      <div>
        <BackButton onClick={() => router.back()} />
        <p className={`text-center ${bodySecondaryClassName}`}>
          Unable to load this alert. Please try again.
        </p>
      </div>
    );
  }

  return (
    <div>
      <BackButton onClick={() => router.back()} />

      <div className={panelClassName}>
        <FoodRecallAlertDetails alert={alert} />
      </div>
    </div>
  );
}
