"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import BackButton from "@/components/BackButton";
import EarlyWarningIncidentDetails from "@/components/EarlyWarningIncidentDetails";
import LoadingState from "@/components/LoadingState";
import { bodySecondaryClassName, panelClassName } from "@/lib/ui";
import { ApiError, getIncidentById } from "@/services/api/client";
import type { EarlyWarningIncident } from "@/types/incident";

type DetailStatus = "pending" | "ready" | "not_found" | "error";

export default function IncidentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const incidentId = params.id;
  const [status, setStatus] = useState<DetailStatus>("pending");
  const [incident, setIncident] = useState<EarlyWarningIncident | null>(null);

  useEffect(() => {
    let cancelled = false;

    getIncidentById(incidentId)
      .then((data) => {
        if (!cancelled) {
          setIncident(data);
          setStatus("ready");
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 404) {
          setStatus("not_found");
          return;
        }
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [incidentId]);

  if (status === "pending") {
    return <LoadingState />;
  }

  if (status === "not_found") {
    return (
      <div>
        <BackButton onClick={() => router.back()} />
        <p className={`text-center ${bodySecondaryClassName}`}>
          Incident not found.
        </p>
      </div>
    );
  }

  if (status === "error" || !incident) {
    return (
      <div>
        <BackButton onClick={() => router.back()} />
        <p className={`text-center ${bodySecondaryClassName}`}>
          Unable to load this incident. Please try again.
        </p>
      </div>
    );
  }

  return (
    <div>
      <BackButton onClick={() => router.back()} />
      <div className={panelClassName}>
        <EarlyWarningIncidentDetails incident={incident} />
      </div>
    </div>
  );
}
