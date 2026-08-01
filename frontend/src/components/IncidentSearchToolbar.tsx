/**
 * Search and filter toolbar for the early-warning incidents list.
 */

"use client";

import { type SubmitEvent, useState } from "react";
import {
  DEFAULT_INCIDENT_SEARCH_FORM_STATE,
  hasActiveIncidentFilters,
  type IncidentSearchFormState,
} from "@/lib/incidentSearch";
import {
  cardClassName,
  formLabelClassName,
  inputClassName,
  primaryButtonClassName,
  secondaryButtonClassName,
  selectClassName,
} from "@/lib/ui";
import {
  INCIDENT_SOURCE_KINDS,
  INCIDENT_SOURCE_KIND_LABELS,
  INCIDENT_STATUSES,
  INCIDENT_STATUS_LABELS,
  INCIDENT_TYPES,
  INCIDENT_TYPE_LABELS,
} from "@/types/incident";

/**
 * Controlled search form for incident text, status, type, confidence, and more.
 *
 * Most select/date changes apply immediately when enabled; free-text fields
 * apply on submit (confidence also applies on blur).
 *
 * @param props.enabled - Whether filter controls should be interactive.
 * @param props.formState - Form state derived from the current URL.
 * @param props.onApplyFilters - Called when filters should be written to the URL.
 * @returns Search toolbar form element.
 */
export default function IncidentSearchToolbar({
  enabled,
  formState: urlFormState,
  onApplyFilters,
}: {
  enabled: boolean;
  formState: IncidentSearchFormState;
  onApplyFilters: (state: IncidentSearchFormState) => void;
}) {
  const [formState, setFormState] =
    useState<IncidentSearchFormState>(urlFormState);

  const applyChange = <K extends keyof IncidentSearchFormState>(
    key: K,
    value: IncidentSearchFormState[K],
  ) => {
    const nextState = { ...formState, [key]: value };
    setFormState(nextState);
    if (enabled) onApplyFilters(nextState);
  };

  const handleSubmit = (event: SubmitEvent) => {
    event.preventDefault();
    if (enabled) onApplyFilters(formState);
  };

  const clearFilters = () => {
    setFormState(DEFAULT_INCIDENT_SEARCH_FORM_STATE);
    onApplyFilters(DEFAULT_INCIDENT_SEARCH_FORM_STATE);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className={`mb-6 ${cardClassName} p-4 sm:p-5`}
    >
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="sm:col-span-2">
          <label htmlFor="incident-search" className={formLabelClassName}>
            Search
          </label>
          <input
            id="incident-search"
            type="search"
            value={formState.search}
            onChange={(event) =>
              setFormState((current) => ({
                ...current,
                search: event.target.value,
              }))
            }
            placeholder="Search products, companies, hazards..."
            disabled={!enabled}
            className={inputClassName}
          />
        </div>

        <div>
          <label htmlFor="incident-status" className={formLabelClassName}>
            Verification status
          </label>
          <select
            id="incident-status"
            value={formState.status}
            onChange={(event) =>
              applyChange(
                "status",
                event.target.value as IncidentSearchFormState["status"],
              )
            }
            disabled={!enabled}
            className={selectClassName}
          >
            <option value="All">All statuses</option>
            {INCIDENT_STATUSES.map((status) => (
              <option key={status} value={status}>
                {INCIDENT_STATUS_LABELS[status]}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="incident-type" className={formLabelClassName}>
            Incident type
          </label>
          <select
            id="incident-type"
            value={formState.incidentType}
            onChange={(event) =>
              applyChange(
                "incidentType",
                event.target.value as IncidentSearchFormState["incidentType"],
              )
            }
            disabled={!enabled}
            className={selectClassName}
          >
            <option value="All">All types</option>
            {INCIDENT_TYPES.map((type) => (
              <option key={type} value={type}>
                {INCIDENT_TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="incident-confidence" className={formLabelClassName}>
            Minimum confidence
          </label>
          <input
            id="incident-confidence"
            type="number"
            min={0}
            max={100}
            step={1}
            value={formState.confidenceMin}
            onChange={(event) =>
              setFormState((current) => ({
                ...current,
                confidenceMin: event.target.value,
              }))
            }
            onBlur={(event) => applyChange("confidenceMin", event.target.value)}
            placeholder="0–100"
            disabled={!enabled}
            className={inputClassName}
          />
        </div>

        <div>
          <label htmlFor="incident-country" className={formLabelClassName}>
            Country
          </label>
          <input
            id="incident-country"
            type="text"
            value={formState.country}
            onChange={(event) =>
              setFormState((current) => ({
                ...current,
                country: event.target.value,
              }))
            }
            placeholder="Any country"
            disabled={!enabled}
            className={inputClassName}
          />
        </div>

        <div>
          <label htmlFor="incident-source-kind" className={formLabelClassName}>
            Source kind
          </label>
          <select
            id="incident-source-kind"
            value={formState.sourceKind}
            onChange={(event) =>
              applyChange(
                "sourceKind",
                event.target.value as IncidentSearchFormState["sourceKind"],
              )
            }
            disabled={!enabled}
            className={selectClassName}
          >
            <option value="All">All sources</option>
            {INCIDENT_SOURCE_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {INCIDENT_SOURCE_KIND_LABELS[kind]}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="incident-date" className={formLabelClassName}>
            Publication date
          </label>
          <input
            id="incident-date"
            type="date"
            value={formState.date}
            onChange={(event) => applyChange("date", event.target.value)}
            disabled={!enabled}
            className={inputClassName}
          />
        </div>

        <div>
          <label htmlFor="incident-sort" className={formLabelClassName}>
            Sort by
          </label>
          <select
            id="incident-sort"
            value={formState.sortBy}
            onChange={(event) =>
              applyChange(
                "sortBy",
                event.target.value as IncidentSearchFormState["sortBy"],
              )
            }
            disabled={!enabled}
            className={selectClassName}
          >
            <option value="">Default</option>
            <option value="latest">Latest</option>
            <option value="oldest">Oldest</option>
            <option value="confidence_high">Highest confidence</option>
            <option value="confidence_low">Lowest confidence</option>
          </select>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <button
          type="button"
          onClick={clearFilters}
          disabled={!enabled || !hasActiveIncidentFilters(formState)}
          className={secondaryButtonClassName}
        >
          Clear filters
        </button>
        <button
          type="submit"
          disabled={!enabled}
          className={primaryButtonClassName}
        >
          Search
        </button>
      </div>
    </form>
  );
}
