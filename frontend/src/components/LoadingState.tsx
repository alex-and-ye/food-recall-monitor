/**
 * Loading spinner and message shown while page or panel data is fetching.
 */

import { bodySecondaryClassName } from "@/lib/ui";

/**
 * Renders a centered spinner with a "Loading data..." label.
 *
 * @returns Loading-state UI element.
 */
export default function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24">
      <div
        className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-slate-700"
        role="status"
        aria-label="Loading"
      />
      <p className={`font-medium ${bodySecondaryClassName}`}>Loading data...</p>
    </div>
  );
}
