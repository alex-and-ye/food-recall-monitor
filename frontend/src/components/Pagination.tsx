import type { ReactNode } from "react";

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
  return (
    <div>
      {children}

      <div className="flex items-center justify-between border-t border-slate-200 pt-6">
      <button
        type="button"
        onClick={onPrevious}
        disabled={currentPage <= 1}
        className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Previous
      </button>

      <span className="text-sm font-medium text-slate-600">
        Page {currentPage} of {totalPages}
      </span>

      <button
        type="button"
        onClick={onNext}
        disabled={currentPage >= totalPages}
        className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Next
      </button>
      </div>
    </div>
  );
}
