/**
 * Previous/next page controls that wrap a paginated list of child content.
 */

import { useEffect } from "react";
import type { ReactNode } from "react";
import { bodySecondaryClassName, secondaryButtonClassName } from "@/lib/ui";

/** Props for the pagination component. */
interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPrevious: () => void;
  onNext: () => void;
  children: ReactNode;
}

/**
 * Renders paginated children and scrolls to the top when the page changes.
 *
 * @param props.currentPage - 1-based current page index.
 * @param props.totalPages - Total number of pages.
 * @param props.onPrevious - Called when Previous is clicked.
 * @param props.onNext - Called when Next is clicked.
 * @param props.children - List content for the current page.
 * @returns Paginated layout with navigation controls.
 */
export default function Pagination({
  currentPage,
  totalPages,
  onPrevious,
  onNext,
  children,
}: PaginationProps) {
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [currentPage]);

  return (
    <div>
      {children}

      <div className="flex items-center justify-between border-t border-slate-200 pt-6">
      <button
        type="button"
        onClick={onPrevious}
        disabled={currentPage <= 1}
        className={secondaryButtonClassName}
      >
        Previous
      </button>

      <span className={`font-medium ${bodySecondaryClassName}`}>
        Page {currentPage} of {totalPages}
      </span>

      <button
        type="button"
        onClick={onNext}
        disabled={currentPage >= totalPages}
        className={secondaryButtonClassName}
      >
        Next
      </button>
      </div>
    </div>
  );
}
