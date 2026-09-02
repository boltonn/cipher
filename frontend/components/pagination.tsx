"use client";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { IconComponent } from "@/types/common";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";

const DEFAULT_PAGE_SIZES = [10, 20, 25, 50, 100];

interface PaginationProps {
  currentPage: number;
  totalItems: number;
  itemsPerPage: number;
  onPageChange: (page: number) => void;
  isLoading?: boolean;
  siblingCount?: number;
  className?: string;
  /**
   * `"pager"` (default) -- numbered page buttons, for card grids and result
   * lists. `"compact"` -- a single-row footer (rows-per-page, range, arrows)
   * for dense tables.
   */
  variant?: "pager" | "compact";
  /** compact only: show the "x-y of N" range label. */
  showRange?: boolean;
  /** compact only: current page size. Renders a "Rows per page" select when `onPageSizeChange` is also passed. */
  pageSize?: number;
  pageSizeOptions?: number[];
  onPageSizeChange?: (size: number) => void;
}

const DOTS = "...";

const range = (start: number, end: number) => {
  const length = end - start + 1;
  return Array.from({ length }, (_, idx) => idx + start);
};

const getPaginationRange = ({
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

function NavButton({
  icon: Icon,
  label,
  onClick,
  disabled,
}: {
  icon: IconComponent;
  label: string;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-7 w-7 text-muted-foreground hover:bg-muted/60 hover:text-primary disabled:opacity-30 disabled:hover:text-muted-foreground"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
    >
      <Icon className="size-3.5" />
    </Button>
  );
}

/** Dense one-line footer: rows-per-page, range, and prev/next arrows. */
function CompactPagination({
  currentPage,
  totalItems,
  itemsPerPage,
  onPageChange,
  isLoading = false,
  className,
  showRange,
  pageSize,
  pageSizeOptions,
  onPageSizeChange,
}: PaginationProps) {
  if (totalItems === 0) return null;

  const totalPages = Math.max(1, Math.ceil(totalItems / itemsPerPage));
  const rangeStart = (currentPage - 1) * itemsPerPage + 1;
  const rangeEnd = Math.min(currentPage * itemsPerPage, totalItems);
  const canPrev = currentPage > 1;
  const canNext = currentPage < totalPages;

  return (
    <nav
      aria-label="Pagination"
      className={cn(
        "flex items-center justify-between gap-4 border-t border-border/50 py-3",
        className
      )}
    >
      {onPageSizeChange && pageSize !== undefined ? (
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            Rows per page
          </span>
          <Select
            value={String(pageSize)}
            onValueChange={(v) => onPageSizeChange(Number(v))}
          >
            <SelectTrigger className="h-7 w-16 border-border bg-muted/40 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(pageSizeOptions ?? DEFAULT_PAGE_SIZES).map((size) => (
                <SelectItem key={size} value={String(size)}>
                  {size}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : (
        <span />
      )}

      {showRange && (
        <span className="font-mono text-[10px] text-muted-foreground">
          {rangeStart}&ndash;{rangeEnd} of {totalItems.toLocaleString()}
        </span>
      )}

      <div className="flex items-center gap-1">
        <NavButton
          icon={ChevronsLeft}
          label="Go to first page"
          onClick={() => onPageChange(1)}
          disabled={!canPrev || isLoading}
        />
        <NavButton
          icon={ChevronLeft}
          label="Go to previous page"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={!canPrev || isLoading}
        />
        <span className="px-2 font-mono text-[10px] text-muted-foreground">
          {currentPage} / {totalPages}
        </span>
        <NavButton
          icon={ChevronRight}
          label="Go to next page"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={!canNext || isLoading}
        />
        <NavButton
          icon={ChevronsRight}
          label="Go to last page"
          onClick={() => onPageChange(totalPages)}
          disabled={!canNext || isLoading}
        />
      </div>
    </nav>
  );
}

/**
 * The app's one pagination control. `variant="pager"` (default) renders
 * numbered page buttons for card grids and result lists; `variant="compact"`
 * renders a dense table footer with an optional rows-per-page select.
 */
export const Pagination = (props: PaginationProps) => {
  const {
    currentPage,
    totalItems,
    itemsPerPage,
    onPageChange,
    isLoading = false,
    siblingCount = 1,
    className,
    variant = "pager",
  } = props;

  if (variant === "compact") {
    return <CompactPagination {...props} />;
  }

  const totalPages = Math.ceil(totalItems / itemsPerPage);
  const paginationRange = getPaginationRange({
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
    <nav
      aria-label="Pagination"
      className={cn(
        "flex justify-center items-center gap-2 py-10 border-t border-border/50",
        className
      )}
    >
      {/* First Page */}
      <Button
        variant="ghost"
        size="icon"
        className={cn(
          "h-8 w-8 text-muted-foreground hover:text-primary hover:bg-muted/60",
          !canGoPrevious && "opacity-30 cursor-not-allowed hover:text-muted-foreground"
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
          "h-8 gap-1 px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground hover:text-primary hover:bg-muted/60",
          !canGoPrevious && "opacity-30 cursor-not-allowed hover:text-muted-foreground"
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
                className="h-8 w-8 flex items-center justify-center text-muted-foreground font-mono text-sm"
              >
                &#8943;
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
                  ? "bg-primary text-white hover:bg-primary shadow-[0_0_12px_rgba(99,102,241,0.4)]"
                  : "text-muted-foreground hover:text-primary hover:bg-muted/60"
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
          "h-8 gap-1 px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground hover:text-primary hover:bg-muted/60",
          !canGoNext && "opacity-30 cursor-not-allowed hover:text-muted-foreground"
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
          "h-8 w-8 text-muted-foreground hover:text-primary hover:bg-muted/60",
          !canGoNext && "opacity-30 cursor-not-allowed hover:text-muted-foreground"
        )}
        disabled={!canGoNext || isLoading}
        onClick={() => onPageChange(totalPages)}
        aria-label="Go to last page"
      >
        <ChevronsRight size={16} />
      </Button>
    </nav>
  );
};
