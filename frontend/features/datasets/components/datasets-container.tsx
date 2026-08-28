"use client";

import type { DataTableFilters, DataTableSortOrder } from "@/components/data-table/types";
import { DataTablePaginationFooter } from "@/components/data-table/pagination-footer";
import { DatasetCard } from "@/features/datasets/components/dataset-card";
import { DatasetsTable } from "@/features/datasets/components/datasets-table";
import type { DatasetSummary } from "@/features/datasets/types";
import { Database, Loader2 } from "lucide-react";

export type DatasetsViewMode = "table" | "card";

interface DatasetsContainerProps {
  viewMode: DatasetsViewMode;
  datasets: DatasetSummary[];
  total: number;
  page: number;
  limit: number;
  isLoading?: boolean;
  sortBy?: string;
  sortOrder?: DataTableSortOrder;
  filters: DataTableFilters;
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
  onSortChange: (sortBy: string, sortOrder: DataTableSortOrder) => void;
  onFilterChange: (key: string, value: DataTableFilters[string]) => void;
}

export function DatasetsContainer({
  viewMode,
  datasets,
  total,
  page,
  limit,
  isLoading,
  sortBy,
  sortOrder,
  filters,
  onPageChange,
  onLimitChange,
  onSortChange,
  onFilterChange,
}: DatasetsContainerProps) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 text-muted-foreground py-16">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
        <span className="text-xs font-mono">Searching datasets...</span>
      </div>
    );
  }

  if (viewMode === "table") {
    return (
      <DatasetsTable
        datasets={datasets}
        total={total}
        page={page}
        limit={limit}
        sortBy={sortBy}
        sortOrder={sortOrder}
        filters={filters}
        onPageChange={onPageChange}
        onLimitChange={onLimitChange}
        onSortChange={onSortChange}
        onFilterChange={onFilterChange}
      />
    );
  }

  if (datasets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-muted-foreground">
        <Database className="h-12 w-12 text-muted-foreground mb-4" />
        <p className="text-xs text-muted-foreground">No datasets found</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {datasets.map((dataset) => (
          <DatasetCard key={dataset.id} dataset={dataset} />
        ))}
      </div>
      <DataTablePaginationFooter
        page={page}
        limit={limit}
        total={total}
        onPageChange={onPageChange}
        onLimitChange={onLimitChange}
      />
    </div>
  );
}
