"use client";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp, ListFilter, Settings2, X } from "lucide-react";
import { useRef, useState } from "react";
import { DataTableColumnHeader, isFilterActive } from "./column-header";
import { DataTablePaginationFooter } from "./pagination-footer";
import type {
  DataTableColumn,
  DataTableFilters,
  DataTableSortOrder,
} from "./types";

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  getRowId: (row: T) => string;
  total: number;
  page: number;
  limit: number;
  sortBy?: string;
  sortOrder?: DataTableSortOrder;
  /** Sort state to restore when "Clear filters" also resets sort -- omit to leave sort alone when clearing. */
  defaultSortBy?: string;
  defaultSortOrder?: DataTableSortOrder;
  filters: DataTableFilters;
  isLoading?: boolean;
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
  onSortChange: (sortBy: string, sortOrder: DataTableSortOrder) => void;
  onFilterChange: (key: string, value: DataTableFilters[string]) => void;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
  rowHeight?: number;
  maxBodyHeight?: number;
  className?: string;
}

/**
 * Schema-agnostic data table: fully driven by a `DataTableColumn<T>[]` config
 * (see types.ts). Sorting, filtering, and pagination are "manual" -- state
 * changes call back to the parent, which is expected to refetch from the
 * backend, rather than the table sorting/filtering an already-fetched array
 * client-side. Rows are virtualized so a full page (up to 100 rows) never
 * costs more render work than what's actually on screen.
 */
export function DataTable<T>({
  columns,
  data,
  getRowId,
  total,
  page,
  limit,
  sortBy,
  sortOrder,
  defaultSortBy,
  defaultSortOrder,
  filters,
  isLoading,
  onPageChange,
  onLimitChange,
  onSortChange,
  onFilterChange,
  onRowClick,
  emptyMessage = "No results",
  rowHeight = 44,
  maxBodyHeight = 580,
  className,
}: DataTableProps<T>) {
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set());
  const visibleColumns = columns.filter((c) => !hiddenColumns.has(c.key));

  const activeFilterKeys = Object.entries(filters)
    .filter(([, value]) => isFilterActive(value))
    .map(([key]) => key);
  const isSortedAwayFromDefault =
    !!defaultSortBy &&
    (sortBy !== defaultSortBy || sortOrder !== defaultSortOrder);
  const hasActiveCustomization =
    activeFilterKeys.length > 0 || isSortedAwayFromDefault;

  const clearAll = () => {
    for (const key of activeFilterKeys) onFilterChange(key, undefined);
    if (defaultSortBy && defaultSortOrder)
      onSortChange(defaultSortBy, defaultSortOrder);
  };

  const scrollRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
  });

  const toggleColumn = (key: string) => {
    setHiddenColumns((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const gridTemplateColumns = visibleColumns
    .map((c) => c.width ?? "1fr")
    .join(" ");

  return (
    <div
      className={cn(
        "flex flex-col rounded-lg border border-white/5 overflow-hidden",
        className
      )}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-900/40 border-b border-white/5">
        <div className="flex items-center gap-3">
          {hasActiveCustomization && (
            <>
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-indigo-400">
                <ListFilter size={12} />
                {activeFilterKeys.length > 0
                  ? `${activeFilterKeys.length} filter${activeFilterKeys.length > 1 ? "s" : ""} active`
                  : "Sorted"}
              </div>
              <Button
                type="button"
                variant="ghost"
                onClick={clearAll}
                className="h-6 gap-1 px-2 text-[10px] font-bold uppercase tracking-widest text-slate-400 hover:text-rose-400"
              >
                <X size={11} />
                Clear filters
              </Button>
            </>
          )}
          {sortBy && (
            <div className="flex items-center gap-1 text-[10px] uppercase tracking-widest text-slate-600">
              {sortOrder === "asc" ? (
                <ArrowUp size={10} />
              ) : (
                <ArrowDown size={10} />
              )}
              Sorted by{" "}
              {columns.find((c) => c.key === sortBy)?.header ?? sortBy}
            </div>
          )}
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-400 hover:text-indigo-400 transition-colors"
            >
              <Settings2 size={12} /> Columns
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            className="bg-popover border border-white/10"
          >
            {columns.map((column) => (
              <DropdownMenuCheckboxItem
                key={column.key}
                checked={!hiddenColumns.has(column.key)}
                onCheckedChange={() => toggleColumn(column.key)}
                className="text-xs"
                onSelect={(e) => e.preventDefault()}
              >
                {column.header}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Header row */}
      <div
        className="grid gap-3 px-4 py-3 bg-slate-900/40 border-b border-white/5"
        style={{ gridTemplateColumns }}
      >
        {visibleColumns.map((column) => (
          <DataTableColumnHeader
            key={column.key}
            column={column}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSort={onSortChange}
            filterValue={filters[column.key]}
            onFilterChange={onFilterChange}
          />
        ))}
      </div>

      {/* Body */}
      {data.length === 0 && !isLoading ? (
        <div className="flex items-center justify-center py-16 text-xs text-slate-600">
          {emptyMessage}
        </div>
      ) : (
        <div
          ref={scrollRef}
          className="overflow-y-auto"
          style={{ maxHeight: maxBodyHeight }}
        >
          <div
            style={{
              height: rowVirtualizer.getTotalSize(),
              position: "relative",
            }}
          >
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const row = data[virtualRow.index];
              return (
                <div
                  key={getRowId(row)}
                  role={onRowClick ? "button" : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                  onClick={() => onRowClick?.(row)}
                  onKeyDown={(e) => {
                    if (onRowClick && (e.key === "Enter" || e.key === " ")) {
                      e.preventDefault();
                      onRowClick(row);
                    }
                  }}
                  className={cn(
                    "grid gap-3 px-4 items-center border-b border-white/5 absolute top-0 left-0 w-full",
                    onRowClick && "cursor-pointer hover:bg-white/2"
                  )}
                  style={{
                    gridTemplateColumns,
                    height: virtualRow.size,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  {visibleColumns.map((column) => (
                    <div
                      key={column.key}
                      className={cn(
                        "text-sm text-slate-300 truncate",
                        column.align === "right" && "text-right"
                      )}
                    >
                      {column.render
                        ? column.render(row)
                        : String(
                            (row as Record<string, unknown>)[column.key] ?? ""
                          )}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="px-3">
        <DataTablePaginationFooter
          page={page}
          limit={limit}
          total={total}
          onPageChange={onPageChange}
          onLimitChange={onLimitChange}
        />
      </div>
    </div>
  );
}
