/**
 * Tailwind class mappings for food-recall risk level badges.
 */

import type { RiskLevel } from "@/types/alert";

/** Background/text classes keyed by risk level. */
export const RISK_BADGE_STYLES: Record<RiskLevel, string> = {
  High: "bg-red-700 text-white",
  Medium: "bg-amber-500 text-black",
  Low: "bg-emerald-700 text-white",
  Unknown: "bg-slate-200 text-slate-800",
};

/** Fallback badge classes when a risk level is missing from the map. */
export const DEFAULT_RISK_BADGE_STYLE = "bg-slate-200 text-slate-800";

/**
 * Resolves the Tailwind class string for a risk level badge.
 *
 * @param riskLevel - Alert risk level.
 * @returns Tailwind utility classes for the badge.
 */
export function getRiskBadgeClassName(riskLevel: RiskLevel): string {
  return RISK_BADGE_STYLES[riskLevel] ?? DEFAULT_RISK_BADGE_STYLE;
}
