"use client";

import { type SubmitEvent, useCallback, useEffect, useState } from "react";
import {
  DEFAULT_ALERT_SEARCH_FORM_STATE,
  hasActiveFilters,
  type AlertSearchFormState,
} from "@/lib/alertSearch";
import {
  cardClassName,
  formLabelClassName,
  inputClassName,
  primaryButtonClassName,
  secondaryButtonClassName,
  selectClassName,
} from "@/lib/ui";
import { COUNTRY_SOURCES, RISK_LEVELS } from "@/types/alert";

interface AlertSearchToolbarProps {
  hasFeeds: boolean;
  formState: AlertSearchFormState;
  onApplyFilters: (state: AlertSearchFormState) => void;
}

export default function AlertSearchToolbar({
  hasFeeds,
  formState: urlFormState,
  onApplyFilters,
}: AlertSearchToolbarProps) {
  const [formState, setFormState] = useState<AlertSearchFormState>(urlFormState);

  useEffect(() => {
    setFormState(urlFormState);
  }, [urlFormState]);

  const filtersActive = hasActiveFilters(formState);

  const handleSubmit = (event: SubmitEvent) => {
    event.preventDefault();
    if (!hasFeeds) {
      return;
    }

    onApplyFilters(formState);
  };

  const handleClearFilters = () => {
    setFormState(DEFAULT_ALERT_SEARCH_FORM_STATE);
    onApplyFilters(DEFAULT_ALERT_SEARCH_FORM_STATE);
  };

  const handleRiskLevelChange = useCallback(
    (riskLevel: AlertSearchFormState["riskLevel"]) => {
      const nextState = { ...formState, riskLevel };
      setFormState(nextState);
      if (hasFeeds) {
        onApplyFilters(nextState);
      }
    },
    [formState, hasFeeds, onApplyFilters],
  );

  const handleCountrySourceChange = useCallback(
    (countrySource: AlertSearchFormState["countrySource"]) => {
      const nextState = { ...formState, countrySource };
      setFormState(nextState);
      if (hasFeeds) {
        onApplyFilters(nextState);
      }
    },
    [formState, hasFeeds, onApplyFilters],
  );

  return (
    <form
      onSubmit={handleSubmit}
      className={`mb-6 ${cardClassName} p-4 sm:p-5`}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:flex-wrap lg:items-end">
        <div className="min-w-0 flex-1 lg:min-w-[12rem]">
          <label htmlFor="alert-search" className={formLabelClassName}>
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
          <label htmlFor="alert-risk-level" className={formLabelClassName}>
            Risk Level
          </label>
          <select
            id="alert-risk-level"
            value={formState.riskLevel}
            onChange={(event) =>
              handleRiskLevelChange(
                event.target.value as AlertSearchFormState["riskLevel"],
              )
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
          <label htmlFor="alert-country-source" className={formLabelClassName}>
            Country Source
          </label>
          <select
            id="alert-country-source"
            value={formState.countrySource}
            onChange={(event) =>
              handleCountrySourceChange(
                event.target.value as AlertSearchFormState["countrySource"],
              )
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
