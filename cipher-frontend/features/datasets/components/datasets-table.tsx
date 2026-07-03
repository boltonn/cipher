import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Dataset, DatasetSortFieldType } from "@/features/datasets/types";
import { cn } from "@/lib/utils";
import { ArrowDown, ArrowUp, Database, Loader2 } from "lucide-react";
import React from "react";

interface DatasetsTableProps {
  datasets: Dataset[];
  totalResults: number;
  isLoadingMore?: boolean;
  hasMore?: boolean;
  observerRef: React.RefObject<HTMLDivElement | null>;
  sortBy?: DatasetSortFieldType;
  sortOrder?: "asc" | "desc";
  onSort?: (field: DatasetSortFieldType) => void;
}

interface SortButtonProps {
  field: DatasetSortFieldType;
  children: React.ReactNode;
  align?: "left" | "right";
  sortBy?: DatasetSortFieldType;
  sortOrder?: "asc" | "desc";
  onSort?: (field: DatasetSortFieldType) => void;
}

const SortButton = ({
  field,
  children,
  align = "left",
  sortBy,
  sortOrder,
  onSort,
}: SortButtonProps) => {
  const isActive = sortBy === field;

  return (
    <button
      type="button"
      onClick={() => onSort?.(field)}
      className={cn(
        "flex items-center gap-2 group transition-colors",
        align === "right" && "ml-auto",
        isActive ? "text-indigo-400" : "text-slate-500 hover:text-slate-300"
      )}
    >
      <span className="text-[10px] font-bold uppercase tracking-widest">
        {children}
      </span>
      <div className="relative w-3 h-3">
        {isActive ? (
          sortOrder === "asc" ? (
            <ArrowUp size={12} className="text-indigo-400" />
          ) : (
            <ArrowDown size={12} className="text-indigo-400" />
          )
        ) : (
          <ArrowDown
            size={12}
            className="text-slate-600 group-hover:text-slate-400 transition-colors"
          />
        )}
      </div>
    </button>
  );
};

const formatDate = (dateString: string) =>
  new Date(dateString).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

export function DatasetsTable({
  datasets,
  totalResults,
  isLoadingMore = false,
  hasMore = false,
  observerRef,
  sortBy = "dateCreated",
  sortOrder = "desc",
  onSort,
}: DatasetsTableProps) {

  if (datasets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-slate-500">
        <Database className="h-12 w-12 text-slate-700 mb-4" />
        <p className="text-xs text-slate-600">No datasets found</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Desktop Table View */}
      <div className="hidden md:block rounded-lg border border-white/5 overflow-hidden">
        <Table>
          <TableHeader className="bg-slate-900/40">
            <TableRow className="border-white/5 hover:bg-transparent">
              <TableHead className="py-3">
                <SortButton
                  field="name"
                  sortBy={sortBy}
                  sortOrder={sortOrder}
                  onSort={onSort}
                >
                  Name
                </SortButton>
              </TableHead>
              <TableHead className="py-3">
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
                  Description
                </span>
              </TableHead>
              <TableHead className="py-3">
                <SortButton
                  field="dateCreated"
                  sortBy={sortBy}
                  sortOrder={sortOrder}
                  onSort={onSort}
                >
                  Date Created
                </SortButton>
              </TableHead>
              <TableHead className="py-3 text-right">
                <SortButton
                  field="dateLastUpdated"
                  align="right"
                  sortBy={sortBy}
                  sortOrder={sortOrder}
                  onSort={onSort}
                >
                  Date Updated
                </SortButton>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {datasets.map((dataset, index) => (
              <TableRow
                key={`${dataset.id}-${index}`}
                className="border-white/5 hover:bg-white/2 transition-colors"
              >
                <TableCell className="font-mono text-sm text-slate-200 py-3">
                  {dataset.name}
                </TableCell>
                <TableCell className="max-w-md truncate text-sm text-slate-400 py-3">
                  {dataset.description}
                </TableCell>
                <TableCell className="text-xs text-slate-500 py-3">
                  {formatDate(dataset.dateCreated)}
                </TableCell>
                <TableCell className="text-xs text-slate-500 text-right py-3">
                  {formatDate(dataset.dateLastUpdated)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Mobile Card View */}
      <div className="md:hidden space-y-3">
        {datasets.map((dataset, index) => (
          <div
            key={`${dataset.id}-${index}`}
            className="p-4 rounded-lg bg-slate-900/40 border border-white/5"
          >
            <h3 className="font-mono text-sm text-slate-200 mb-2">
              {dataset.name}
            </h3>
            <p className="text-xs text-slate-400 mb-3 line-clamp-2">
              {dataset.description}
            </p>
            <div className="flex justify-between items-center pt-3 border-t border-white/5 text-[10px] text-slate-500">
              <span>Date Created {formatDate(dataset.dateCreated)}</span>
              <span>Date Updated {formatDate(dataset.dateLastUpdated)}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Infinite Scroll Trigger */}
      <div ref={observerRef} className="py-8">
        {isLoadingMore ? (
          <div className="flex items-center justify-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
            <span className="text-xs text-slate-500">Loading more...</span>
          </div>
        ) : hasMore ? (
          <div className="h-px bg-linear-to-r from-transparent via-white/5 to-transparent" />
        ) : datasets.length > 0 ? (
          <div className="text-center">
            <span className="text-xs text-slate-600">
              {totalResults} {totalResults === 1 ? "dataset" : "datasets"} total
            </span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
