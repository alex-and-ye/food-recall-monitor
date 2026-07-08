import { useEffect } from "react";
import type { ReactNode } from "react";
import { bodySecondaryClassName, secondaryButtonClassName } from "@/lib/ui";

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPrevious: () => void;
  onNext: () => void;
  children: ReactNode;
}

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
