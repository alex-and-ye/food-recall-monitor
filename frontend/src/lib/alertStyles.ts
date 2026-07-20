import type { RiskLevel } from "@/types/alert";

export const RISK_BADGE_STYLES: Record<RiskLevel, string> = {
  High: "bg-red-700 text-white",
  Medium: "bg-amber-500 text-black",
  Low: "bg-emerald-700 text-white",
  Unknown: "bg-slate-200 text-slate-800",
};

export const DEFAULT_RISK_BADGE_STYLE = "bg-slate-200 text-slate-800";

export function getRiskBadgeClassName(riskLevel: RiskLevel): string {
  return RISK_BADGE_STYLES[riskLevel] ?? DEFAULT_RISK_BADGE_STYLE;
}
