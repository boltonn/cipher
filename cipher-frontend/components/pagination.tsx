"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";

interface PaginationProps {
  currentPage: number;
  totalItems: number;
  itemsPerPage: number;
  onPageChange: (page: number) => void;
  isLoading?: boolean;
  siblingCount?: number;
  className?: string;
}

const DOTS = "...";

const range = (start: number, end: number) => {
  const length = end - start + 1;
  return Array.from({ length }, (_, idx) => idx + start);
};

const usePaginationRange = ({
  currentPage,
  totalPages,
  siblingCount = 1,
}: {
  currentPage: number;
  totalPages: number;
  siblingCount?: number;
}) => {
  if (totalPages <= 5 + siblingCount * 2) {
    return range(1, totalPages);
  }

  const leftSiblingIndex = Math.max(currentPage - siblingCount, 1);
  const rightSiblingIndex = Math.min(currentPage + siblingCount, totalPages);

  const shouldShowLeftDots = leftSiblingIndex > 2;
  const shouldShowRightDots = rightSiblingIndex < totalPages - 1;

  // Case 1: No dots on either side
  if (!shouldShowLeftDots && !shouldShowRightDots) {
    return range(1, totalPages);
  }

  // Case 2: Dots on right only
  if (!shouldShowLeftDots && shouldShowRightDots) {
    const leftRange = range(1, 3 + siblingCount * 2);
    return [...leftRange, DOTS, totalPages];
  }

  // Case 3: Dots on left only
  if (shouldShowLeftDots && !shouldShowRightDots) {
    const rightRange = range(totalPages - (2 + siblingCount * 2), totalPages);
    return [1, DOTS, ...rightRange];
  }

  // Case 4: Dots on both sides
  const middleRange = range(leftSiblingIndex, rightSiblingIndex);
  return [1, DOTS, ...middleRange, DOTS, totalPages];
};

export const Pagination = ({
  currentPage,
  totalItems,
  itemsPerPage,
  onPageChange,
  isLoading = false,
  siblingCount = 1,
  className,
}: PaginationProps) => {
  const totalPages = Math.ceil(totalItems / itemsPerPage);
  const paginationRange = usePaginationRange({
    currentPage,
    totalPages,
    siblingCount,
  });

  // Don't render if there's only one page or no items
  if (totalPages <= 1) {
    return null;
  }

  const canGoPrevious = currentPage > 1;
  const canGoNext = currentPage < totalPages;

  return (
    <div
      className={cn(
        "flex justify-center items-center gap-2 py-10 border-t border-white/5",
        className
      )}
    >
      {/* First Page */}
      <Button
        variant="ghost"
        size="icon"
        className={cn(
          "h-8 w-8 text-slate-500 hover:text-indigo-400 hover:bg-slate-900/60",
          !canGoPrevious && "opacity-30 cursor-not-allowed hover:text-slate-500"
        )}
        disabled={!canGoPrevious || isLoading}
        onClick={() => onPageChange(1)}
        aria-label="Go to first page"
      >
        <ChevronsLeft size={16} />
      </Button>

      {/* Previous Page */}
      <Button
        variant="ghost"
        className={cn(
          "h-8 gap-1 px-3 text-[10px] font-bold uppercase tracking-widest text-slate-500 hover:text-indigo-400 hover:bg-slate-900/60",
          !canGoPrevious && "opacity-30 cursor-not-allowed hover:text-slate-500"
        )}
        disabled={!canGoPrevious || isLoading}
        onClick={() => onPageChange(currentPage - 1)}
      >
        <ChevronLeft size={14} />
        Prev
      </Button>

      {/* Page Numbers */}
      <div className="flex items-center gap-1">
        {paginationRange.map((pageNumber, index) => {
          // Render dots
          if (pageNumber === DOTS) {
            return (
              <div
                key={`dots-${index}`}
                className="h-8 w-8 flex items-center justify-center text-slate-600 font-mono text-sm"
              >
                ⋯
              </div>
            );
          }

          // Render page number
          const isCurrentPage = pageNumber === currentPage;
          return (
            <Button
              key={pageNumber}
              variant={isCurrentPage ? "default" : "ghost"}
              size="icon"
              className={cn(
                "h-8 w-8 font-mono text-xs transition-all",
                isCurrentPage
                  ? "bg-indigo-600 text-white hover:bg-indigo-500 shadow-[0_0_12px_rgba(99,102,241,0.4)]"
                  : "text-slate-400 hover:text-indigo-400 hover:bg-slate-900/60"
              )}
              onClick={() => onPageChange(pageNumber as number)}
              disabled={isLoading}
            >
              {pageNumber}
            </Button>
          );
        })}
      </div>

      {/* Next Page */}
      <Button
        variant="ghost"
        className={cn(
          "h-8 gap-1 px-3 text-[10px] font-bold uppercase tracking-widest text-slate-500 hover:text-indigo-400 hover:bg-slate-900/60",
          !canGoNext && "opacity-30 cursor-not-allowed hover:text-slate-500"
        )}
        disabled={!canGoNext || isLoading}
        onClick={() => onPageChange(currentPage + 1)}
      >
        Next
        <ChevronRight size={14} />
      </Button>

      {/* Last Page */}
      <Button
        variant="ghost"
        size="icon"
        className={cn(
          "h-8 w-8 text-slate-500 hover:text-indigo-400 hover:bg-slate-900/60",
          !canGoNext && "opacity-30 cursor-not-allowed hover:text-slate-500"
        )}
        disabled={!canGoNext || isLoading}
        onClick={() => onPageChange(totalPages)}
        aria-label="Go to last page"
      >
        <ChevronsRight size={16} />
      </Button>
    </div>
  );
};
