"use client";

import { type SubmitEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  buildAlertSearchPayload,
  DEFAULT_ALERT_SEARCH_FORM_STATE,
  hasActiveFilters,
  type AlertSearchFormState,
  type AlertSearchPayload,
} from "@/lib/alertSearch";
import { COUNTRY_SOURCES, RISK_LEVELS } from "@/types/alert";

const disabledClassName = "disabled:cursor-not-allowed disabled:opacity-40";

const inputClassName = `w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition-colors placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 ${disabledClassName}`;

const selectClassName = `w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition-colors focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 ${disabledClassName}`;

const secondaryButtonClassName = `rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 ${disabledClassName}`;

const primaryButtonClassName = `rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 ${disabledClassName}`;

interface AlertSearchToolbarProps {
  hasFeeds: boolean;
  onSearch?: (payload: AlertSearchPayload) => void;
}

export default function AlertSearchToolbar({
  hasFeeds,
  onSearch,
}: AlertSearchToolbarProps) {
  const [formState, setFormState] = useState<AlertSearchFormState>(
    DEFAULT_ALERT_SEARCH_FORM_STATE,
  );
  const hasSearchedRef = useRef(false);

  const filtersActive = hasActiveFilters(formState);

  const resetFeedResults = useCallback(() => {
    if (!hasFeeds || !onSearch) {
      return;
    }

    onSearch(buildAlertSearchPayload(DEFAULT_ALERT_SEARCH_FORM_STATE));
    hasSearchedRef.current = false;
  }, [hasFeeds, onSearch]);

  const performSearch = useCallback(() => {
    const payload = buildAlertSearchPayload(formState);

    if (onSearch) {
      hasSearchedRef.current = true;
      onSearch(payload);
      return;
    }

    alert(JSON.stringify(payload, null, 2));
  }, [formState, onSearch]);

  useEffect(() => {
    if (!hasActiveFilters(formState) && hasSearchedRef.current) {
      resetFeedResults();
    }
  }, [formState, resetFeedResults]);

  const handleSubmit = (event: SubmitEvent) => {
    event.preventDefault();
    if (!hasFeeds) {
      return;
    }

    performSearch();
  };

  const handleClearFilters = () => {
    setFormState(DEFAULT_ALERT_SEARCH_FORM_STATE);
    resetFeedResults();
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="mb-6 rounded-xl border border-slate-300 bg-white p-4 shadow-sm sm:p-5"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:flex-wrap lg:items-end">
        <div className="min-w-0 flex-1 lg:min-w-[12rem]">
          <label
            htmlFor="alert-search"
            className="mb-1.5 block text-sm font-medium text-slate-700"
          >
            Search
          </label>
          <input
            id="alert-search"
            type="search"
            value={formState.search}
            onChange={(event) =>
              setFormState((current) => ({
                ...current,
                search: event.target.value,
              }))
            }
            placeholder="Search food recall alerts..."
            disabled={!hasFeeds}
            className={inputClassName}
          />
        </div>

        <div className="min-w-0 sm:min-w-[10rem]">
          <label
            htmlFor="alert-risk-level"
            className="mb-1.5 block text-sm font-medium text-slate-700"
          >
            Risk Level
          </label>
          <select
            id="alert-risk-level"
            value={formState.riskLevel}
            onChange={(event) =>
              setFormState((current) => ({
                ...current,
                riskLevel: event.target.value as AlertSearchFormState["riskLevel"],
              }))
            }
            disabled={!hasFeeds}
            className={selectClassName}
          >
            <option value="All">All</option>
            {RISK_LEVELS.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </div>

        <div className="min-w-0 sm:min-w-[10rem]">
          <label
            htmlFor="alert-country-source"
            className="mb-1.5 block text-sm font-medium text-slate-700"
          >
            Country Source
          </label>
          <select
            id="alert-country-source"
            value={formState.countrySource}
            onChange={(event) =>
              setFormState((current) => ({
                ...current,
                countrySource: event.target.value as AlertSearchFormState["countrySource"],
              }))
            }
            disabled={!hasFeeds}
            className={selectClassName}
          >
            <option value="All">All</option>
            {COUNTRY_SOURCES.map((country) => (
              <option key={country} value={country}>
                {country}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap gap-2 lg:pb-0.5">
          <button
            type="button"
            onClick={handleClearFilters}
            disabled={!hasFeeds || !filtersActive}
            className={secondaryButtonClassName}
          >
            Clear Filters
          </button>
          <button
            type="submit"
            disabled={!hasFeeds}
            className={primaryButtonClassName}
          >
            Search
          </button>
        </div>
      </div>
    </form>
  );
}
