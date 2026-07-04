"use client";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";

const PAGE_SIZE_OPTIONS = [10, 20, 25, 50, 100];

interface DataTablePaginationFooterProps {
  page: number;
  limit: number;
  total: number;
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
}

export function DataTablePaginationFooter({
  page,
  limit,
  total,
  onPageChange,
  onLimitChange,
}: DataTablePaginationFooterProps) {
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const rangeStart = total === 0 ? 0 : (page - 1) * limit + 1;
  const rangeEnd = Math.min(page * limit, total);

  return (
    <div className="flex items-center justify-between gap-4 px-1 py-3 border-t border-white/5">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
          Rows per page
        </span>
        <Select value={String(limit)} onValueChange={(v) => onLimitChange(Number(v))}>
          <SelectTrigger className="h-7 w-16 text-xs bg-slate-900/40 border-white/10">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZE_OPTIONS.map((size) => (
              <SelectItem key={size} value={String(size)}>
                {size}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <span className="text-[10px] font-mono text-slate-500">
        {rangeStart}–{rangeEnd} of {total.toLocaleString()}
      </span>

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-slate-400 hover:text-indigo-400 disabled:opacity-30"
          onClick={() => onPageChange(1)}
          disabled={page <= 1}
          aria-label="First page"
        >
          <ChevronsLeft size={14} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-slate-400 hover:text-indigo-400 disabled:opacity-30"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          <ChevronLeft size={14} />
        </Button>
        <span className="text-[10px] font-mono text-slate-400 px-2">
          {page} / {totalPages}
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-slate-400 hover:text-indigo-400 disabled:opacity-30"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          aria-label="Next page"
        >
          <ChevronRight size={14} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-slate-400 hover:text-indigo-400 disabled:opacity-30"
          onClick={() => onPageChange(totalPages)}
          disabled={page >= totalPages}
          aria-label="Last page"
        >
          <ChevronsRight size={14} />
        </Button>
      </div>
    </div>
  );
}
